"""Bulk-waiver replay.

An earlier fidelity run produced, on one screen:

    41 design elements · 11 observed · 5 matched
    49 findings (42 proposed fail + 7 warn)
    0 failures · 49 waived · verdict PASS

All 49 waivers carried one of two boilerplate reasons, looped. The sibling
screen waived 136. Both were reported as PASS.

These tests replay that failure shape through `uir.py` and assert it cannot pass.
They protect the rule that repeated generic waivers cannot hide unverified work.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fixtures as fx  # noqa: E402
import uir  # noqa: E402


ADAPTATION_REASON = (
    "The source reference uses a platform-specific decorative representation. "
    "The target platform intentionally represents the same app-owned behavior "
    "with an ExampleUI Block/StandardTextField and typed dynamic rows; the "
    "target capture is the observed fact for this authorized adaptation."
)

GENERIC_ELEMENTS = [
    "Frame",
    "Grouped List",
    "Divider",
    "_Separator",
    "Status + App Shell",
    "Platform Header",
    "App Bar",
    "Surface Effect",
    "End Slot",
    "Center Root",
    "Button Group 3",
    "BG",
    "Text Area",
    "Trailing Icon",
    "Add Icon",
]

LOG_HEAD = """---
screen: choice-dialog
spec: ./design-spec.md
round: 1
---

## Round 1 — 2026-01-15T07:10:00Z

Evidence tiers used: T1 static render

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
"""


def rid(n: int) -> str:
    return f"R-{n:03d}"


def build_spec(count: int) -> str:
    """BASE_SPEC rebuilt around `count` generated elements.

    Visible Elements, Exact Metrics and the checklist are generated together:
    the three tables share one element namespace, so a spec that changes one
    must change all three or it contradicts itself.
    """
    elements = [GENERIC_ELEMENTS[(n - 1) % len(GENERIC_ELEMENTS)] + f" {n}" for n in range(1, count + 1)]
    checklist = [
        f"| {rid(n)} | * | {element} | geometry/height | {40 + n}dp | design 100:{200 + n} |"
        for n, element in enumerate(elements, 1)
    ]
    visible = [
        f"| {element} | 100:{200 + n} | generated row {n} |"
        for n, element in enumerate(elements, 1)
    ] + [
        # State Variance still references Dialog, so it stays declared.
        "| Title | 100:210 | dialog title |",
        "| Dialog | 100:211 | dialog container |",
    ]
    metrics = [f"| {element} | height | {40 + n}dp |" for n, element in enumerate(elements, 1)]

    head, _, tail = fx.BASE_SPEC.partition("## Restoration Checklist")
    del tail
    head = _replace_table(
        head, "Visible Elements", "| Element | Figma node | Description |", visible
    )
    head = _replace_table(head, "Exact Metrics", "| Element | Property | Value |", metrics)
    # The checklist is regenerated, so the declared-fact tables must be too or
    # they would declare tokens and assets this checklist never asserts.
    head = _replace_table(
        head, "Visual Tokens",
        "| Usage | Type | Repository token | Design value | Mark | Reference |",
        ["| — | — | — | — | reuse | — |"],
    )
    head = _replace_table(
        head, "Asset Inventory",
        "| asset | Type | Repository name | Mark | Reference | Variant |",
        ["| — | — | — | reuse | — | — |"],
    )
    head = _replace_table(
        head, "Copy And Labels", "| copy | Authoritative source |", ["| — | — |"],
    )
    return (
        head
        + "## Restoration Checklist\n\n"
        + "| ID | State | Element | Dimension | Expected | Source |\n"
        + "|---|---|---|---|---|---|\n"
        + "\n".join(checklist)
        + "\n"
    )


def _replace_table(text: str, section: str, header: str, rows: list) -> str:
    before, marker, rest = text.partition(f"## {section}")
    assert marker, section
    _, _, after = rest.partition("\n## ")
    divider = "|" + "---|" * (header.count("|") - 1)
    body = "\n\n" + header + "\n" + divider + "\n" + "\n".join(rows) + "\n\n## "
    return before + marker + body + after


def build_log(count: int, verdict: str, reason: str) -> str:
    rows = []
    for n in range(1, count + 1):
        if verdict == "adapted":
            rows.append(
                f"| {rid(n)} | * | adapted | ExampleUI Block | T1 observed.png | {reason} |"
            )
        else:
            rows.append(f"| {rid(n)} | * | {verdict} | — | — | {reason} |")
    return LOG_HEAD + "\n".join(rows) + "\n"


class BulkWaiverReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = fx.make_repo(Path(self._tmp.name))
        fx.make_ladder(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def prepare(self, count: int, log_text: str):
        screen = fx.make_screen(self.repo, spec=build_spec(count))
        spec_findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertEqual(
            [],
            [f.render() for f in spec_findings if f.level == "fail"],
            "the replay spec itself must be valid, or the test proves nothing",
        )
        path = fx.make_log(screen, log_text)
        return uir.status_one(path, self.repo), path

    def test_49_waivers_on_one_reason_cannot_pass(self) -> None:
        st, path = self.prepare(49, build_log(49, "adapted", ADAPTATION_REASON))
        self.assertEqual(49, st.counts["adapted"])
        self.assertEqual(
            2, uir.exit_code_for(st), "a bulk waiver printed PASS here; this must be blocked"
        )
        self.assertIn("one adapted reason covers 49 rows", fx.messages(st.findings))
        self.assertEqual(2, uir.main(["status", str(path)]))

    def test_136_waivers_on_one_reason_cannot_pass(self) -> None:
        """The sibling screen's count, in case 49 were ever special-cased."""
        st, _ = self.prepare(136, build_log(136, "adapted", ADAPTATION_REASON))
        self.assertEqual(2, uir.exit_code_for(st))
        self.assertIn("one adapted reason covers 136 rows", fx.messages(st.findings))

    def test_no_counterpart_mass_becomes_unverified_and_never_passes(self) -> None:
        """A batch of elements with no observed counterpart must not pass.

        In this model they are `unverified`, which is honest and which blocks.
        """
        st, _ = self.prepare(
            31, build_log(31, "unverified", "T1 cannot observe this element, nothing to judge")
        )
        self.assertEqual(31, st.counts["unverified"])
        self.assertEqual(0, st.counts["restored"])
        self.assertEqual(1, uir.exit_code_for(st))
        self.assertNotEqual(0, uir.exit_code_for(st), "silence must not read as a pass")

    def test_a_repeated_unverified_reason_is_allowed(self) -> None:
        """`unverified` can never produce a pass, so it needs no repetition cap.

        "T1 cannot capture these" genuinely applies to many rows at once; capping it would
        push honest admissions toward dishonest waivers.
        """
        st, _ = self.prepare(31, build_log(31, "unverified", "T1 cannot observe this element"))
        self.assertEqual([], [f.render() for f in st.findings if f.level == "fail"])

    def test_scaffolding_cannot_enter_the_checklist_at_all(self) -> None:
        """Design-tool scaffolding must be excluded before comparison.

        Once an element is on the do-not-build list, measuring it is a spec
        error -- so those 26 never become findings in the first place.
        """
        spec = build_spec(3).replace(
            "| R-001 | * | Frame 1 | geometry/height | 41dp | design 100:201 |",
            "| R-001 | * | Container | geometry/height | 41dp | design 100:201 |",
        )
        screen = fx.make_screen(self.repo, spec=spec)
        findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertIn("must not be measured", fx.messages(findings))

    def test_five_matched_out_of_41_cannot_pass(self) -> None:
        """A handful of matches cannot hide a large adapted remainder."""
        rows = []
        for n in range(1, 42):
            if n <= 5:
                rows.append(
                    f"| {rid(n)} | * | restored | {40 + n}dp | T1 observed.png crop | |"
                )
            else:
                rows.append(
                    f"| {rid(n)} | * | adapted | ExampleUI Block | T1 observed.png | {ADAPTATION_REASON} |"
                )
        st, _ = self.prepare(41, LOG_HEAD + "\n".join(rows) + "\n")
        self.assertEqual(5, st.counts["restored"])
        self.assertEqual(36, st.counts["adapted"])
        self.assertEqual(2, uir.exit_code_for(st))


if __name__ == "__main__":
    unittest.main()
