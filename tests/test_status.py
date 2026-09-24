"""status gates: evidence, blind spots, adapted reasons, and the ratchet."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fixtures as fx  # noqa: E402
import uir  # noqa: E402


LOG_HEAD = """---
screen: choice-dialog
spec: ./design-spec.md
round: 1
---

## Round 1 — 2026-09-03T11:00Z

Evidence tiers used: T0 source + T1 static render

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
"""


DEFAULT_SWEEP = """
### Sweep

| Difference | State | Evidence | Disposition | Ref |
|---|---|---|---|---|
| none observed | default | T1 default.png vs ./assets/default.png | — | — |
"""


def log_with(rows: str, head: str = LOG_HEAD, sweep: str = DEFAULT_SWEEP) -> str:
    """A log needs a sweep to be reportable as done, so one is appended by
    default; a test about the sweep itself passes its own or none."""
    return head + rows + sweep


class StatusBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = fx.make_repo(Path(self._tmp.name))
        fx.make_ladder(self.repo)
        self.screen = fx.make_screen(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def status(self, log_text: str = fx.BASE_LOG):
        path = fx.make_log(self.screen, log_text)
        return uir.status_one(path, self.repo), path

    def assertGateFails(self, log_text: str, needle: str):
        st, path = self.status(log_text)
        fails = [f for f in st.findings if f.level == "fail"]
        self.assertTrue(fails, f"expected a gate failure, got: {uir.render_status(st)}")
        self.assertIn(needle, fx.messages(fails))
        self.assertEqual(2, uir.exit_code_for(st))
        return st


class BaselineTests(StatusBase):
    def test_clean_round_is_done(self) -> None:
        st, path = self.status()
        self.assertEqual([], [f.render() for f in st.findings])
        self.assertEqual(5, st.counts["restored"])
        self.assertEqual(0, uir.exit_code_for(st))
        self.assertEqual(1, uir.main(["status", str(path)]))  # legacy prose cannot establish acceptance

    def test_cost_ladder_is_respected_in_the_baseline(self) -> None:
        """token judged by free T0, geometry by T1 -- the ladder working."""
        st, _ = self.status()
        self.assertEqual(0, uir.exit_code_for(st))

    def test_render_lists_remaining_items(self) -> None:
        rows = (
            "| R-001 | * | restored | Category | T1 default.png crop(24,24,64,24) | |\n"
            "| R-002 | * | unrestored | 20sp/700 | T1 default.png | used header2, should be header3 |\n"
        )
        st, _ = self.status(log_with(rows))
        text = uir.render_status(st)
        self.assertIn("R-002", text)
        self.assertIn("Title typography", text)
        self.assertEqual(1, uir.exit_code_for(st))


class EvidenceGateTests(StatusBase):
    def test_restored_without_evidence_fails(self) -> None:
        rows = "| R-001 | * | restored | Category | | |\n"
        self.assertGateFails(log_with(rows), "its evidence is empty")

    def test_restored_with_dash_evidence_fails(self) -> None:
        rows = "| R-001 | * | restored | Category | — | |\n"
        self.assertGateFails(log_with(rows), "its evidence is empty")

    def test_evidence_without_tier_prefix_fails(self) -> None:
        rows = "| R-001 | * | restored | Category | default.png crop(24,24,64,24) | |\n"
        self.assertGateFails(log_with(rows), "does not name its tier")

    def test_unknown_tier_fails(self) -> None:
        rows = "| R-001 | * | restored | Category | T9 somewhere | |\n"
        self.assertGateFails(log_with(rows), "is not defined in the evidence ladder")

    def test_blind_tier_cannot_support_restored(self) -> None:
        """T1 cannot see token identity, so it cannot mark a `token` row restored."""
        rows = "| R-004 | * | restored | ExampleColor.neutral_0 | T1 default.png crop(24,24,64,24) | |\n"
        st = self.assertGateFails(log_with(rows), "which tier `T1` cannot observe")
        self.assertIn("treating a blind spot as a match", fx.messages(st.findings))

    def test_correct_tier_supports_restored(self) -> None:
        rows = "| R-004 | * | restored | ExampleColor.neutral_0 | T0 ChoiceDialogScreen.kt:88 | |\n"
        st, _ = self.status(log_with(rows))
        self.assertEqual([], [f.render() for f in st.findings])

    def test_geometry_cannot_be_judged_by_source_alone(self) -> None:
        rows = "| R-003 | * | restored | 16dp | T0 ChoiceDialogScreen.kt:120 | |\n"
        self.assertGateFails(log_with(rows), "which tier `T0` cannot observe")

    def test_the_documented_capture_citation_format_is_accepted(self) -> None:
        """A run exports many captures, so a capture citation has to say which one.

        `references/restoration-template.md` documents `T1 <case>/<variant>` for
        exactly that reason; this pins the documented form to the gate so the two
        cannot drift apart.
        """
        rows = (
            "| R-001 | * | restored | Category | "
            "T1 RUN-01/portrait_light crop(24,24,64,24) | |\n"
        )
        st, _ = self.status(log_with(rows))
        self.assertEqual([], [f.render() for f in st.findings])
        self.assertEqual(1, st.counts["restored"])

    def test_missing_ladder_blocks(self) -> None:
        (self.repo / ".agents" / "visual-restoration" / "evidence-ladder.md").unlink()
        self.assertGateFails(fx.BASE_LOG, "cannot find evidence-ladder.md")

    def test_requirement_level_ladder_overrides_project_level(self) -> None:
        override = fx.BASE_LADDER.replace(
            "## T1 static render\n\n- means: <this project's preview/snapshot capability>\n"
            "- trigger: <command>\n- output: <directory>\n"
            "- observes-dimensions: geometry, spacing, shape, typography, color, visibility, copy, asset\n"
            "- blind-dimensions: token, interaction",
            "## T1 static render\n\n- means: requirement-level override\n"
            "- trigger: <command>\n- output: <directory>\n"
            "- observes-dimensions: geometry\n"
            "- blind-dimensions: token, interaction, copy, typography, shape, color, visibility, asset",
        )
        (self.screen.parent / "evidence-ladder.md").write_text(override, encoding="utf-8")
        # R-001 is copy, which the override says T1 cannot see.
        self.assertGateFails(fx.BASE_LOG, "which tier `T1` cannot observe")


ALL_RESTORED = (
    "| R-020 | * | restored | ExampleIcons.Check | T0 Screen.kt:140 | |\n"
    "| R-001 | * | restored | Category | T1 default.png crop(0,0,1,1) | |\n"
    "| R-002 | * | restored | 17sp/700/20sp/-0.2 | T1 default.png crop(0,0,1,1) | |\n"
    "| R-003 | * | restored | 16dp | T1 default.png crop(0,0,1,1) | |\n"
    "| R-004 | * | restored | ExampleColor.neutral_0 | T0 Screen.kt:88 | |\n"
)


class SweepTests(StatusBase):
    """The backstop for what nobody enumerated.

    The checklist only compares what it lists, so Phase 1 enumeration was a
    single point of failure with no backstop: a real run reported 43 restored /
    0 unrestored while the card padding and the top-bar font size were still
    wrong, because no row ever asked about them. The sweep asks.
    """

    def test_a_round_without_a_sweep_cannot_be_done(self) -> None:
        st, _ = self.status(log_with(ALL_RESTORED, sweep=""))
        self.assertTrue(st.sweep_missing)
        self.assertEqual(1, uir.exit_code_for(st), "an unswept round is not done")
        self.assertIn("no sweep", uir.render_status(st))

    def test_a_swept_round_with_nothing_found_is_done(self) -> None:
        st, _ = self.status()
        self.assertFalse(st.sweep_missing)
        self.assertEqual(0, uir.exit_code_for(st))

    def test_a_difference_needs_a_disposition(self) -> None:
        sweep = DEFAULT_SWEEP.replace(
            "| none observed | default | T1 default.png vs ./assets/default.png | — | — |",
            "| card padding looks wider | default | T1 default.png | | |",
        )
        self.assertGateFails(log_with(ALL_RESTORED, sweep=sweep),
                             "expected one of covered/new-row/do-not-build/adapted")

    def test_a_disposition_needs_a_reference(self) -> None:
        sweep = DEFAULT_SWEEP.replace(
            "| none observed | default | T1 default.png vs ./assets/default.png | — | — |",
            "| card padding looks wider | default | T1 default.png | covered | |",
        )
        self.assertGateFails(log_with(ALL_RESTORED, sweep=sweep),
                             "disposition without a reference disposes of nothing")

    def test_a_reference_must_be_a_real_checklist_row(self) -> None:
        sweep = DEFAULT_SWEEP.replace(
            "| none observed | default | T1 default.png vs ./assets/default.png | — | — |",
            "| card padding looks wider | default | T1 default.png | new-row | R-999 |",
        )
        self.assertGateFails(log_with(ALL_RESTORED, sweep=sweep),
                             "which is not a checklist row")

    def test_a_visible_difference_cannot_hide_behind_a_restored_row(self) -> None:
        """This is the exact shape of the reported bug: the row said restored
        while the screen visibly differed."""
        sweep = DEFAULT_SWEEP.replace(
            "| none observed | default | T1 default.png vs ./assets/default.png | — | — |",
            "| dialog corner looks softer | default | T1 default.png | covered | R-003 |",
        )
        self.assertGateFails(log_with(ALL_RESTORED, sweep=sweep),
                             "cannot sit behind a restored row")

    def test_every_state_must_be_swept(self) -> None:
        """Sweeping only the state that was easiest to capture is not sweeping.

        A pressed or error state is exactly where an unenumerated difference
        hides, so covering `default` alone would report the screen as swept.
        """
        two_states = fx.BASE_SPEC.replace(
            """  - name: default
    node_id: "100:200"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200
    baseline: ./assets/default.png""",
            """  - name: default
    node_id: "100:200"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200
    baseline: ./assets/default.png
  - name: pressed
    node_id: "100:231"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-231
    baseline: ./assets/pressed.png""",
        )
        self.screen = fx.make_screen(
            self.repo, spec=two_states, states=("default", "pressed")
        )
        self.assertGateFails(log_with(ALL_RESTORED), "never covers state(s) `pressed`")

    def test_a_star_sweep_row_covers_every_state(self) -> None:
        sweep = DEFAULT_SWEEP.replace("| none observed | default |", "| none observed | * |")
        st, _ = self.status(log_with(ALL_RESTORED, sweep=sweep))
        self.assertEqual([], [f.render() for f in st.findings if f.level == "fail"])

    def test_a_difference_covered_by_an_unrestored_row_passes(self) -> None:
        st, _ = self.status(fx.SWEPT_LOG)
        self.assertEqual([], [f.render() for f in st.findings if f.level == "fail"])
        self.assertEqual(1, st.counts["unrestored"])
        self.assertEqual(1, uir.exit_code_for(st))


class EvidenceMixTests(StatusBase):
    """How much a clean round is worth depends on what carried the verdicts.

    A real round reported 43 restored / 0 unrestored with 28 of the 43 judged
    from source, which cannot see a rendered size -- and the screen still did
    not match the design. The ratio was invisible in the report.
    """

    def test_the_tier_mix_is_reported(self) -> None:
        st, _ = self.status()
        self.assertEqual({"T0": 2, "T1": 3}, st.tier_counts)
        self.assertIn("evidence: T0 2 / T1 3", uir.render_status(st))

    def test_a_source_heavy_round_says_so(self) -> None:
        rows = (
            "| R-001 | * | restored | Category | T0 Screen.kt:10 | |\n"
            "| R-002 | * | restored | 17sp/700/20sp/-0.2 | T1 default.png crop(0,0,1,1) | |\n"
            "| R-003 | * | restored | 16dp | T1 default.png crop(0,0,1,1) | |\n"
            "| R-004 | * | restored | ExampleColor.neutral_0 | T0 Screen.kt:88 | |\n"
        )
        text = uir.render_status(self.status(log_with(rows))[0])
        self.assertNotIn("judged from source alone", text)

        heavy = (
            "| R-001 | * | restored | Category | T0 Screen.kt:10 | |\n"
            "| R-002 | * | restored | 17sp/700/20sp/-0.2 | T0 Screen.kt:20 | |\n"
            "| R-003 | * | restored | 16dp | T0 Screen.kt:30 | |\n"
            "| R-004 | * | restored | ExampleColor.neutral_0 | T0 Screen.kt:88 | |\n"
        )
        st, _ = self.status(log_with(heavy))
        # Those T0 geometry rows are also gated as blind spots; the point here
        # is that the mix is stated either way.
        self.assertIn("4/4 judged from source alone", uir.render_status(st))


class VerdictGateTests(StatusBase):
    def test_invalid_verdict_fails(self) -> None:
        rows = "| R-001 | * | ok | Category | T1 default.png | |\n"
        self.assertGateFails(log_with(rows), "invalid verdict `ok`")

    def test_id_absent_from_spec_fails(self) -> None:
        rows = "| R-999 | * | restored | Category | T1 default.png | |\n"
        self.assertGateFails(log_with(rows), "does not exist in the spec checklist")

    def test_unrestored_needs_a_measured_value(self) -> None:
        rows = "| R-002 | * | unrestored | | T1 default.png | wrong |\n"
        self.assertGateFails(log_with(rows), "states no measured value")

    def test_unverified_needs_a_reason(self) -> None:
        rows = "| R-002 | * | unverified | — | — | |\n"
        self.assertGateFails(log_with(rows), "does not say why evidence could not be obtained")

    def test_unverified_is_never_a_pass(self) -> None:
        rows = (
            "| R-001 | * | restored | Category | T1 default.png | |\n"
            "| R-002 | * | unverified | — | — | the T1 tier cannot capture this state |\n"
        )
        st, _ = self.status(log_with(rows))
        self.assertEqual([], [f.render() for f in st.findings])
        self.assertEqual(1, uir.exit_code_for(st), "unverified must block completion")


class AdaptedGateTests(StatusBase):
    def test_adapted_without_reason_fails(self) -> None:
        rows = "| R-003 | * | adapted | ExampleUI Divider | T0 Screen.kt:142 | |\n"
        self.assertGateFails(log_with(rows), "states no reason")

    def test_three_identical_reasons_are_allowed(self) -> None:
        reason = "the platform grouped-list separator is an ExampleUI Divider here; the color token carries, geometry does not"
        rows = "".join(
            f"| R-00{n} | * | adapted | ExampleUI Divider | T0 Screen.kt:14{n} | {reason} |\n"
            for n in (1, 2, 3)
        )
        st, _ = self.status(log_with(rows))
        self.assertEqual([], [f.render() for f in st.findings])

    def test_fourth_identical_reason_fails(self) -> None:
        reason = "the platform grouped-list separator is an ExampleUI Divider here; the color token carries, geometry does not"
        rows = "".join(
            f"| R-00{n} | * | adapted | ExampleUI Divider | T0 Screen.kt:14{n} | {reason} |\n"
            for n in (1, 2, 3, 4)
        )
        self.assertGateFails(log_with(rows), "one adapted reason covers 4 rows")

    def test_whitespace_does_not_launder_a_repeated_reason(self) -> None:
        base = "the same reason"
        variants = [base, f"  {base}  ", f"{base}", f"{base} "]
        rows = "".join(
            f"| R-00{n + 1} | * | adapted | x | T0 Screen.kt:1 | {variants[n]} |\n"
            for n in range(4)
        )
        self.assertGateFails(log_with(rows), "covers 4 rows")


TWO_ROUND_HEAD = """---
screen: choice-dialog
spec: ./design-spec.md
round: 2
---

## Round 1 — 2026-09-03T11:00Z

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
| R-001 | * | unrestored | a | T1 p.png | off |
| R-002 | * | unrestored | b | T1 p.png | off |
| R-003 | * | unrestored | c | T1 p.png | off |
| R-020 | * | restored | ExampleIcons.Check | T0 Screen.kt:140 | |

## Round 2 — 2026-09-03T12:00Z

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
"""


class RatchetTests(StatusBase):
    def test_ratchet_ok_when_unrestored_drops(self) -> None:
        rows = (
            "| R-001 | * | restored | a | T1 p.png | |\n"
            "| R-002 | * | unrestored | b | T1 p.png | still off |\n"
            "| R-003 | * | unrestored | c | T1 p.png | still off |\n"
        )
        st, _ = self.status(log_with(rows, TWO_ROUND_HEAD))
        self.assertEqual(3, st.prev_unrestored)
        self.assertEqual(2, st.counts["unrestored"])
        self.assertFalse(st.stalled)
        self.assertIn("ratchet: 3 → 2  OK", uir.render_status(st))
        self.assertEqual(1, uir.exit_code_for(st))

    def test_stalled_when_unrestored_does_not_drop(self) -> None:
        rows = (
            "| R-001 | * | unrestored | a | T1 p.png | still off |\n"
            "| R-002 | * | unrestored | b | T1 p.png | still off |\n"
            "| R-003 | * | unrestored | c | T1 p.png | still off |\n"
        )
        st, _ = self.status(log_with(rows, TWO_ROUND_HEAD))
        self.assertTrue(st.stalled)
        text = uir.render_status(st)
        self.assertIn("STALLED", text)
        self.assertIn("stop the automatic loop", text)

    def test_all_clear_in_a_later_round_is_done(self) -> None:
        rows = (
            "| R-001 | * | restored | a | T1 p.png | |\n"
            "| R-002 | * | restored | b | T1 p.png | |\n"
            "| R-003 | * | restored | c | T1 p.png | |\n"
            "| R-004 | * | restored | d | T0 Screen.kt:88 | |\n"
        )
        st, _ = self.status(log_with(rows, TWO_ROUND_HEAD))
        self.assertFalse(st.stalled)
        self.assertEqual([], st.unjudged)
        self.assertEqual(0, uir.exit_code_for(st))


class UnjudgedCoverageTests(StatusBase):
    """A partial round is fine; reporting done with rows never judged is not.

    Found by running the real flow: a T0-only round judged 9 of 22 checklist
    rows, and without this check an all-green partial round exits 0.
    """

    def test_rows_never_judged_block_completion(self) -> None:
        rows = "| R-001 | * | restored | Label | T1 default.png crop(0,0,1,1) | |\n"
        st, _ = self.status(log_with(rows))
        self.assertEqual(0, st.counts["unrestored"])
        self.assertEqual(0, st.counts["unverified"])
        self.assertEqual(["R-002", "R-003", "R-004", "R-020"], sorted(st.unjudged))
        self.assertEqual(1, uir.exit_code_for(st), "silence must not read as a pass")

    def test_unjudged_rows_are_listed(self) -> None:
        rows = "| R-001 | * | restored | Label | T1 default.png crop(0,0,1,1) | |\n"
        st, _ = self.status(log_with(rows))
        text = uir.render_status(st)
        self.assertIn("unjudged (4)", text)
        self.assertIn("R-002", text)

    def test_rows_judged_in_an_earlier_round_still_count(self) -> None:
        """Later rounds only take the remainder, so coverage accumulates."""
        head = TWO_ROUND_HEAD.replace(
            "| R-003 | * | unrestored | c | T1 p.png | off |",
            "| R-003 | * | restored | c | T1 p.png | |\n"
            "| R-004 | * | restored | d | T0 Screen.kt:88 | |",
        )
        rows = (
            "| R-001 | * | restored | a | T1 p.png | |\n"
            "| R-002 | * | restored | b | T1 p.png | |\n"
        )
        st, _ = self.status(log_with(rows, head))
        self.assertEqual([], st.unjudged)
        self.assertEqual(0, uir.exit_code_for(st))


class CumulativeAccountingTests(StatusBase):
    """Rounds are partial by design, so the state of a screen is the latest
    verdict per id across all rounds -- not the last round's contents.

    Found by the real run: round 1 left 6 unrestored, round 2 judged only the
    other 13 rows, and round-local counting reported `unrestored 0` with a
    passing ratchet while those 6 were still open.
    """

    def _two_rounds(self, round_two_rows: str) -> str:
        head = """---
screen: choice-dialog
spec: ./design-spec.md
round: 2
---

## Round 1 — 2026-09-03T11:00Z

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
| R-001 | * | unrestored | a | T1 p.png | off |
| R-002 | * | unrestored | b | T1 p.png | off |
| R-020 | * | restored | ExampleIcons.Check | T0 Screen.kt:140 | |

## Round 2 — 2026-09-03T12:00Z

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
"""
        return head + round_two_rows + DEFAULT_SWEEP

    def test_an_earlier_rounds_unrestored_still_counts(self) -> None:
        rows = (
            "| R-003 | * | restored | c | T1 p.png | |\n"
            "| R-004 | * | restored | d | T0 Screen.kt:1 | |\n"
        )
        st, _ = self.status(self._two_rounds(rows))
        self.assertEqual(2, st.counts["unrestored"], "both round-1 rows are still unfixed")
        # R-020 was judged in round 1 and carries forward alongside round 2's two.
        self.assertEqual(3, st.counts["restored"])
        self.assertIn("R-001", " ".join(st.remaining))
        self.assertEqual(1, uir.exit_code_for(st))

    def test_a_later_round_can_clear_an_earlier_verdict(self) -> None:
        rows = (
            "| R-001 | * | restored | a | T1 p.png | |\n"
            "| R-002 | * | restored | b | T1 p.png | |\n"
            "| R-003 | * | restored | c | T1 p.png | |\n"
            "| R-004 | * | restored | d | T0 Screen.kt:1 | |\n"
        )
        st, _ = self.status(self._two_rounds(rows))
        self.assertEqual(0, st.counts["unrestored"])
        self.assertEqual(0, uir.exit_code_for(st))

    def test_ratchet_compares_cumulative_not_round_local(self) -> None:
        """A round that judges different rows must not read as progress."""
        rows = (
            "| R-003 | * | unverified | — | — | no T1 capture for this screen |\n"
            "| R-004 | * | unverified | — | — | no T1 capture for this screen |\n"
        )
        st, _ = self.status(self._two_rounds(rows))
        self.assertEqual(2, st.prev_unrestored)
        self.assertEqual(2, st.counts["unrestored"])
        self.assertTrue(st.stalled, "the same 2 rows are unfixed, which is not progress")


class AggregateTests(StatusBase):
    def test_directory_mode_reports_every_screen_and_the_worst_code(self) -> None:
        fx.make_log(self.screen, fx.BASE_LOG)
        other = fx.make_screen(self.repo, screen="editor")
        fx.make_log(
            other,
            log_with(
                "| R-001 | * | unrestored | Lab | T1 default.png | wrong copy |\n",
                LOG_HEAD.replace("screen: choice-dialog", "screen: editor"),
            ),
        )
        ui_implement = self.screen.parent
        code = uir.main(["status", str(ui_implement)])
        self.assertEqual(1, code)

    def test_directory_mode_without_logs_is_a_gate_failure(self) -> None:
        code = uir.main(["status", str(self.screen.parent)])
        self.assertEqual(2, code)


class DegenerateInputTests(StatusBase):
    def test_log_without_rounds(self) -> None:
        st, _ = self.status("---\nscreen: x\nspec: ./design-spec.md\n---\n\nNot run yet.\n")
        self.assertEqual(0, st.round_no)
        self.assertEqual(0, st.counts["restored"])

    def test_round_without_a_table_is_a_gate_failure(self) -> None:
        self.assertGateFails(
            "---\nscreen: x\nspec: ./design-spec.md\n---\n\n## Round 1 — now\n\nNo table.\n",
            "has no verdict table",
        )

    def test_invalid_spec_dimension_points_at_the_spec_not_the_ladder(self) -> None:
        """A bad dimension is a spec defect; blaming the tier sends the reader
        to the wrong file."""
        bad = fx.BASE_SPEC.replace("| R-003 | * | Dialog | shape/corner-radius |", "| R-003 | * | Dialog | corner-radius |")
        (self.screen / "design-spec.md").write_text(bad, encoding="utf-8")
        st = self.assertGateFails(fx.BASE_LOG, "not in the vocabulary")
        self.assertNotIn("treating a blind spot as a match", fx.messages(st.findings))

    def test_unreadable_spec_reference_blocks(self) -> None:
        self.assertGateFails(
            fx.BASE_LOG.replace("spec: ./design-spec.md", "spec: ./nope.md"),
            "cannot read the spec checklist",
        )


if __name__ == "__main__":
    unittest.main()
