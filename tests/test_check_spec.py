"""check-spec gates. Every negative test mutates exactly one thing."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fixtures as fx  # noqa: E402  (sys.path set up in fixtures)
import uir  # noqa: E402


class CheckSpecBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = fx.make_repo(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_spec(self, spec: str = fx.BASE_SPEC, **kwargs):
        screen = fx.make_screen(self.repo, spec=spec, **kwargs)
        findings, tbd = uir.check_spec(fx.spec_path(screen))
        return findings, tbd, screen

    def assertFails(self, spec: str, needle: str) -> None:
        findings, _, _ = self.run_spec(spec)
        fails = [f for f in findings if f.level == "fail"]
        self.assertTrue(fails, "expected a failure, got none")
        self.assertIn(needle, fx.messages(fails))

    def assertClean(self, spec: str = fx.BASE_SPEC) -> None:
        findings, _, _ = self.run_spec(spec)
        self.assertEqual([], [f.render() for f in findings if f.level == "fail"])


class BaselineTests(CheckSpecBase):
    def test_screenshot_only_source_needs_no_fabricated_figma_fields(self) -> None:
        spec = fx.BASE_SPEC.replace('figma_file_key: DEMOFILE\n', '').replace(
            '    node_id: "100:200"\n    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200\n',
            '    source_ref: screenshot ./assets/default.png crop(0,0,393,852)\n')
        self.assertClean(spec)

    def test_base_fixture_passes(self) -> None:
        self.assertClean()

    def test_base_fixture_exits_zero(self) -> None:
        screen = fx.make_screen(self.repo)
        code = uir.main(["check-spec", str(fx.spec_path(screen))])
        self.assertEqual(0, code)


class StructureTests(CheckSpecBase):
    def test_missing_required_section(self) -> None:
        spec = fx.BASE_SPEC.replace("## Do Not Build", "## Things Not To Build")
        self.assertFails(spec, "missing required section `## Do Not Build`")

    def test_missing_requirement_ref_blocks(self) -> None:
        spec = fx.BASE_SPEC.replace("requirement_ref: REQ-0001", "requirement_ref:")
        self.assertFails(spec, "requirement_ref")

    def test_missing_front_matter_key(self) -> None:
        spec = fx.BASE_SPEC.replace("impl_target: compose\n", "")
        self.assertFails(spec, "`impl_target`")

    def test_states_must_be_non_empty(self) -> None:
        spec = fx.BASE_SPEC.replace(
            """states:
  - name: default
    node_id: "100:200"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200
    baseline: ./assets/default.png
""",
            "states:\n",
        )
        self.assertFails(spec, "`states` must be a non-empty list")


class AssetTests(CheckSpecBase):
    def test_missing_baseline_screenshot(self) -> None:
        findings, _, _ = self.run_spec(states=())
        self.assertIn("baseline screenshot for state", fx.messages(findings))

    def test_missing_source_meta(self) -> None:
        findings, _, _ = self.run_spec(write_meta=False)
        self.assertIn("source-meta.json", fx.messages(findings))

    def test_source_meta_retrieved_at_mismatch(self) -> None:
        findings, _, _ = self.run_spec(
            meta={
                "retrieved_at": "2026-01-01T00:00:00Z",
                "states": {"default": {"node_id": "100:200"}},
            }
        )
        self.assertIn("did not come from the same retrieval", fx.messages(findings))

    def test_source_meta_missing_state_fingerprint(self) -> None:
        findings, _, _ = self.run_spec(
            meta={"retrieved_at": fx.RETRIEVED_AT, "states": {}}
        )
        self.assertIn("missing the design-source fingerprint for state `default`", fx.messages(findings))


class ChecklistTests(CheckSpecBase):
    # The cases below keep Chinese values on purpose: the checker matches
    # author-written cells, specs here are authored in either language, and
    # dropping the non-English vocabulary would silently stop catching a vague
    # value written in Chinese. English equivalents are covered further down.
    def test_vague_expectation_is_rejected_with_line_number(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | shape/corner-radius | 大约 16dp | design 100:211 |",
        )
        findings, _, _ = self.run_spec(spec)
        fails = [f for f in findings if "hedges with" in f.message]
        self.assertEqual(1, len(fails), fx.messages(findings))
        self.assertRegex(fails[0].where, r"design-spec\.md:\d+")

    def test_an_alignment_word_replacing_a_metric_is_rejected(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | geometry/position | 居中 | design 100:211 |",
        )
        self.assertFails(spec, "in place of a measurable fact")

    def test_an_alignment_word_is_exact_on_an_alignment_row(self) -> None:
        """A centering word is the value for an alignment dimension; there is no number
        to give. Found by running the checker on a real spec."""
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |\n"
            "| R-011 | * | Title | geometry/horizontal-alignment | 相对 AppBar 水平居中 | design 100:211 |",
        )
        self.assertClean(spec)

    def test_left_and_right_sides_are_not_an_approximation(self) -> None:
        """`左右各 16dp` means "16dp on each side", not "about 16dp". Same real spec."""
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |\n"
            "| R-011 | * | Card | spacing/margin | 左右各 16dp，上 20dp | design 100:211 |",
        )
        self.assertClean(spec)

    def test_a_measurement_followed_by_approximately_is_rejected(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | shape/corner-radius | 16dp 左右 | design 100:211 |",
        )
        self.assertFails(spec, "expected value is approximate")

    def test_english_vague_word_is_rejected(self) -> None:
        spec = fx.BASE_SPEC.replace("| 16dp | design 100:211 |", "| roughly 16dp | design 100:211 |")
        self.assertFails(spec, "hedges with")

    def test_an_english_alignment_word_replacing_a_metric_is_rejected(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | geometry/position | centered | design 100:211 |",
        )
        self.assertFails(spec, "in place of a measurable fact")

    def test_an_english_alignment_word_is_exact_on_an_alignment_row(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |\n"
            "| R-011 | * | Title | geometry/horizontal-alignment | centered on the AppBar | design 100:211 |",
        )
        self.assertClean(spec)

    def test_an_english_trailing_hedge_is_rejected(self) -> None:
        for value in ("16dp or so", "16dp ish"):
            with self.subTest(value=value):
                spec = fx.BASE_SPEC.replace(
                    "| 16dp | design 100:211 |", f"| {value} | design 100:211 |"
                )
                self.assertFails(spec, "expected value is approximate")

    def test_a_hyphenated_frame_metric_is_still_caught(self) -> None:
        """An English author writes `full-frame-height`; the matcher normalizes
        separators so the phrasing does not decide whether the gate fires."""
        for dimension in ("geometry/full-frame-height", "geometry/frame_height", "geometry/frame height"):
            with self.subTest(dimension=dimension):
                spec = fx.BASE_SPEC.replace("scroll_axis: none", "scroll_axis: vertical").replace(
                    "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |",
                    f"| R-004 | * | Screen | {dimension} | 1005dp | design 100:200 |",
                )
                self.assertFails(spec, "compares a whole-frame size")

    def test_empty_expectation_is_rejected(self) -> None:
        spec = fx.BASE_SPEC.replace("| 16dp | design 100:211 |", "|  | design 100:211 |")
        self.assertFails(spec, "has an empty expected value")

    def test_template_placeholder_is_rejected(self) -> None:
        spec = fx.BASE_SPEC.replace("| 16dp | design 100:211 |", "| [value]dp | design 100:211 |")
        self.assertFails(spec, "template placeholder")

    def test_duplicate_checklist_id(self) -> None:
        spec = fx.BASE_SPEC.replace("| R-004 | *", "| R-003 | *")
        self.assertFails(spec, "duplicate checklist ID")

    def test_bad_id_format(self) -> None:
        spec = fx.BASE_SPEC.replace("| R-004 |", "| 4 |")
        self.assertFails(spec, "checklist ID must look like")

    def test_dimension_outside_vocabulary(self) -> None:
        spec = fx.BASE_SPEC.replace("| Dialog | shape/corner-radius |", "| Dialog | corner-radius |")
        self.assertFails(spec, "not in the vocabulary")

    def test_design_state_not_declared(self) -> None:
        spec = fx.BASE_SPEC.replace("| R-004 | * |", "| R-004 | pressed |")
        self.assertFails(spec, "not among the frontmatter states")

    def test_missing_source_column_value(self) -> None:
        spec = fx.BASE_SPEC.replace("| 16dp | design 100:211 |", "| 16dp |  |")
        self.assertFails(spec, "has no source")

    def test_tbd_needs_a_reason(self) -> None:
        spec = fx.BASE_SPEC.replace("| 16dp | design 100:211 |", "| TBD | design 100:211 |")
        self.assertFails(spec, "must spell its TBD as `TBD: reason`")

    def test_tbd_count_mismatch(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| 16dp | design 100:211 |", "| TBD: not marked in the design | design 100:211 |"
        )
        self.assertFails(spec, "disagrees with the")

    def test_open_tbd_blocks_phase_two_with_exit_one(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| 16dp | design 100:211 |", "| TBD: not marked in the design | design 100:211 |"
        ).replace("tbd_count: 0", "tbd_count: 1")
        findings, tbd, screen = self.run_spec(spec)
        self.assertEqual(1, tbd)
        self.assertEqual([], [f.render() for f in findings if f.level == "fail"])
        self.assertEqual(1, uir.main(["check-spec", str(fx.spec_path(screen))]))


class ElementNamespaceTests(CheckSpecBase):
    """One element namespace, or nothing can be cross-checked.

    Found by reading a source example: `Visible Elements` declared `AppBar`, the
    checklist asserted `AppBarTitle`, and `Exact Metrics` measured
    `AppBarActions` -- three names for one region and no key to join them on. A
    measured padding then never reached the checklist, and neither a script nor
    a reader could see that it had not.
    """

    def test_a_checklist_element_must_be_declared(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-001 | * | Title | copy |", "| R-001 | * | Caption | copy |"
        )
        self.assertFails(spec, "`Caption` is used by Restoration Checklist")

    def test_a_measured_element_must_be_declared(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Dialog | corner-radius | 16dp |",
            "| Dialog | corner-radius | 16dp |\n| DialogInner | padding | 12dp |",
        )
        self.assertFails(spec, "`DialogInner` is used by Exact Metrics")

    def test_one_finding_per_undeclared_name_not_per_row(self) -> None:
        """A group name on many rows is one thing to declare."""
        spec = fx.BASE_SPEC.replace("| * | Title |", "| * | Headings |")
        findings, _, _ = self.run_spec(spec)
        namespace = [f for f in findings if "never declares it" in f.message]
        self.assertEqual(1, len(namespace), fx.messages(findings))
        self.assertIn("row(s)", namespace[0].message)

    def test_a_do_not_build_element_needs_no_declaration(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Dialog | shape | 16dp | single state, no variance |",
            "| Dialog | shape | 16dp | single state, no variance |\n"
            "| Container | visibility | absent | scaffold, already excluded |",
        )
        self.assertClean(spec)

    def test_coverage_is_not_reported_while_the_namespace_is_broken(self) -> None:
        """A coverage report needs a join key; without one it would be noise."""
        spec = fx.BASE_SPEC.replace(
            "| R-003 | * | Dialog | shape/corner-radius |", "| R-003 | * | Modal | shape/corner-radius |"
        )
        findings, _, _ = self.run_spec(spec)
        messages = fx.messages(findings)
        self.assertIn("metric coverage was not checked", messages)
        self.assertNotIn("no checklist row covers", messages)


class MetricCoverageTests(CheckSpecBase):
    """A metric written down and never compared is not verified.

    This is the defect behind "the screenshots all passed but the padding is
    still wrong": `Exact Metrics` carried the number, the checklist had no row
    for it, and `check-spec` only ever validated the checklist against itself.
    """

    def test_an_uncovered_metric_fails(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Dialog | corner-radius | 16dp |",
            "| Dialog | corner-radius | 16dp |\n| Dialog | padding-start | 12dp |",
        )
        self.assertFails(spec, "no checklist row covers `Dialog` x `spacing`")

    def test_covering_the_metric_passes(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Dialog | corner-radius | 16dp |",
            "| Dialog | corner-radius | 16dp |\n| Dialog | padding-start | 12dp |",
        ).replace(
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |",
            "| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |\n"
            "| R-011 | * | Dialog | spacing/padding-start | 12dp | design 100:211 |",
        )
        self.assertClean(spec)

    def test_property_words_map_to_dimensions_in_either_language(self) -> None:
        for prop, dimension in [
            ("padding-start", "spacing"),
            ("左右内边距", "spacing"),
            ("corner-radius", "shape"),
            ("圆角", "shape"),
            ("height", "geometry"),
            ("高度", "geometry"),
            ("font-size", "typography"),
            ("字号", "typography"),
        ]:
            with self.subTest(prop=prop):
                self.assertEqual(dimension, uir.metric_dimension(prop))

    def test_an_unmappable_property_is_rejected(self) -> None:
        """A property nobody can join is worse than no property."""
        spec = fx.BASE_SPEC.replace(
            "| Dialog | corner-radius | 16dp |",
            "| Dialog | corner-radius | 16dp |\n| Dialog | vibe | calm |",
        )
        self.assertFails(spec, "does not map to a checklist dimension")


class DeclaredFactCoverageTests(CheckSpecBase):
    """`Exact Metrics` is not the only table that declares facts.

    A token, an asset or a copy string the spec lists and the checklist never
    asserts is in exactly the same position as an uncovered metric: written
    down, then never compared.
    """

    def test_an_unasserted_token_fails(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| title color | color | ExampleColor.neutral_0 | #000000 | reuse | example-ui/.../ExampleColor.kt |",
            "| title color | color | ExampleColor.neutral_0 | #000000 | reuse | example-ui/.../ExampleColor.kt |\n"
            "| row divider | color | ExampleColor.neutral_1 | #dddfe5 | reuse | example-ui/.../ExampleColor.kt |",
        )
        self.assertFails(spec, "declares `ExampleColor.neutral_1` but no checklist `token` row")

    def test_an_unasserted_asset_fails(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| check icon | icon | ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |",
            "| check icon | icon | ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |\n"
            "| close icon | icon | ExampleIcons.Close | reuse | example-ui/.../ExampleIcons.kt | vector |",
        )
        self.assertFails(spec, "declares `ExampleIcons.Close` but no checklist `asset` row")

    def test_an_unasserted_copy_string_fails(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Category | requirement §3.2 |",
            "| Category | requirement §3.2 |\n| Cancel | requirement §3.3 |",
        )
        self.assertFails(spec, "declares `Cancel` but no checklist `copy` row")

    def test_a_tbd_entry_owes_no_assertion_yet(self) -> None:
        """A TBD has nothing to compare; Pending Decisions and the tally own it."""
        spec = fx.BASE_SPEC.replace(
            "| check icon | icon | ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |",
            "| check icon | icon | ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |\n"
            "| close icon | icon | — | TBD | no matching icon here | vector |",
        ).replace("tbd_count: 0", "tbd_count: 1").replace(
            "## Pending Decisions\n\nNone.", "## Pending Decisions\n\nClose icon has no match."
        )
        findings, _, _ = self.run_spec(spec)
        self.assertEqual([], [f.render() for f in findings if f.level == "fail"])


class TokenRenderedPairTests(CheckSpecBase):
    """`token` is judged from source and proves identity, not the rendered value.

    A source example had `ToolbarTitle token ExampleTypography.heading` and no
    typography row, so the font size was never measured -- which is exactly the
    reported mismatch.
    """

    def test_a_token_row_without_the_stated_rendered_row_fails(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Dialog | corner-radius | 16dp |",
            "| Dialog | corner-radius | 16dp |\n| Title | font-size | 17sp |",
        ).replace(
            "| R-002 | * | Title | typography | 17sp / 700 / 20sp / -0.2 | design 100:210 |\n",
            "",
        ).replace(
            "| R-001 | * | Title | copy | `Category` | requirement §3.2 |",
            "| R-001 | * | Title | copy | `Category` | requirement §3.2 |\n"
            "| R-011 | * | Title | geometry/height | 20dp | design 100:210 |",
        )
        self.assertFails(spec, "has a `token` row but no `typography` row")

    def test_the_pair_passes(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Dialog | corner-radius | 16dp |",
            "| Dialog | corner-radius | 16dp |\n| Title | font-size | 17sp |",
        )
        self.assertClean(spec)

    def test_a_token_row_alone_is_fine_when_no_rendered_value_is_stated(self) -> None:
        """Only a stated rendered value creates the obligation."""
        self.assertClean()


class ScrollAxisTests(CheckSpecBase):
    def test_frame_height_row_rejected_on_scroll_axis(self) -> None:
        spec = fx.BASE_SPEC.replace("scroll_axis: none", "scroll_axis: vertical").replace(
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |",
            "| R-004 | * | Screen | geometry/full-frame-height | 1005dp | design 100:200 |",
        )
        self.assertFails(spec, "compares a whole-frame size")

    def test_section_height_row_allowed_on_scroll_axis(self) -> None:
        """A section's own height is a real defect surface and must stay checkable."""
        spec = fx.BASE_SPEC.replace("scroll_axis: none", "scroll_axis: vertical").replace(
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |",
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |\n"
            "| R-012 | * | RowItem | geometry/row-height | 40dp | design 100:212 |",
        )
        self.assertClean(spec)

    def test_frame_height_row_allowed_when_not_scrollable(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |",
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |\n"
            "| R-012 | * | Screen | geometry/full-frame-height | 852dp | design 100:200 |",
        )
        self.assertClean(spec)


class TokenAndResourceTests(CheckSpecBase):
    def test_missing_mark(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| #000000 | reuse | example-ui/.../ExampleColor.kt |",
            "| #000000 |  | example-ui/.../ExampleColor.kt |",
        )
        self.assertFails(spec, "invalid mark")

    def test_new_resource_needs_reference_rule(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |",
            "| ExampleIcons.Check | new |  | vector |",
        )
        self.assertFails(spec, "must name the existing asset rule it follows")

    def test_reused_resource_needs_location(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |",
            "| ExampleIcons.Check | reuse |  | vector |",
        )
        self.assertFails(spec, "must name the existing item in this")

    def test_tbd_resource_counts_toward_tbd_total(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |",
            "| — | TBD | no matching icon here and no naming rule to follow | vector |",
        ).replace("tbd_count: 0", "tbd_count: 1")
        findings, tbd, _ = self.run_spec(spec)
        self.assertEqual(1, tbd)
        self.assertEqual([], [f.render() for f in findings if f.level == "fail"])


class BucketTests(CheckSpecBase):
    def test_element_cannot_be_visible_and_do_not_build(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Container | 100:215 | scaffold | design-tool structural container, absent at runtime |",
            "| Dialog | 100:211 | scaffold | authored by mistake |",
        )
        self.assertFails(spec, "cannot be both built and not built")

    def test_draft_element_must_reach_do_not_build_list(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| SystemOverlay | 100:213 | draft | device shell, not app content |\n", ""
        )
        self.assertFails(spec, "never reaches `Do Not Build`")

    def test_excluded_element_must_reach_do_not_build_list(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| OptionalRow | 100:214 | excluded | custom category is out of scope in this example |\n", ""
        )
        self.assertFails(spec, "never reaches `Do Not Build`")

    def test_draft_and_excluded_are_mutually_exclusive(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| OptionalRow | 100:214 | custom category is out of scope in this example | product owner | yes |",
            "| SystemOverlay | 100:213 | out of scope in this example | product owner | yes |",
        )
        self.assertFails(spec, "mutually exclusive")

    def test_invalid_do_not_build_category(self) -> None:
        spec = fx.BASE_SPEC.replace(
            "| Container | 100:215 | scaffold |", "| Container | 100:215 | decorative |"
        )
        self.assertFails(spec, "invalid category `decorative`")


MULTI_STATE_SPEC = (
    fx.BASE_SPEC.replace(
        """states:
  - name: default
    node_id: "100:200"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200
    baseline: ./assets/default.png
""",
        """states:
  - name: default
    node_id: "100:200"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200
    baseline: ./assets/default.png
  - name: pressed
    node_id: "100:230"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-230
    baseline: ./assets/pressed.png
""",
    )
    .replace(
        """| Element | Dimension | default | Note |
|---|---|---|---|
| Dialog | shape | 16dp | single state, no variance |""",
        """| Element | Dimension | default | pressed | Note |
|---|---|---|---|---|
| Dialog | shape | 16dp | 16dp | unchanged |
| RowItem | color | neutral_base | neutral_b5 | pressed feedback |""",
    )
    .replace(
        "| default | open the dialog | ./assets/default.png | — |",
        "| default | open the dialog | ./assets/default.png | — |\n"
        "| pressed | finger held on a row | ./assets/pressed.png | that row's background changes |",
    )
)


class MultiStateTests(CheckSpecBase):
    def test_declared_state_difference_needs_a_per_state_checklist_row(self) -> None:
        screen = fx.make_screen(
            self.repo, spec=MULTI_STATE_SPEC, states=("default", "pressed")
        )
        findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertIn("checklist has no matching `pressed` row", fx.messages(findings))

    def test_multi_state_passes_once_every_state_row_exists(self) -> None:
        """A varying dimension needs a row per state: the base value is a real
        check too, and `*` would assert one value for all states."""
        spec = MULTI_STATE_SPEC.replace(
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |",
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |\n"
            "| R-005 | default | RowItem | color | ExampleColor.base | design 100:212 |\n"
            "| R-006 | pressed | RowItem | color | ExampleColor.muted | design 100:231 |",
        )
        screen = fx.make_screen(self.repo, spec=spec, states=("default", "pressed"))
        findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertEqual([], [f.render() for f in findings if f.level == "fail"])

    def test_star_row_contradicts_a_declared_state_difference(self) -> None:
        spec = MULTI_STATE_SPEC.replace(
            "| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |",
            "| R-004 | * | RowItem | color | ExampleColor.base | design 100:212 |",
        )
        screen = fx.make_screen(self.repo, spec=spec, states=("default", "pressed"))
        findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertIn("asserts a single value with `*`", fx.messages(findings))

    def test_unvarying_row_needs_no_per_state_row(self) -> None:
        """`Dialog shape` is identical across states, so it stays a `*` row."""
        spec = MULTI_STATE_SPEC.replace(
            "| RowItem | color | neutral_base | neutral_b5 | pressed feedback |\n", ""
        )
        screen = fx.make_screen(self.repo, spec=spec, states=("default", "pressed"))
        findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertEqual([], [f.render() for f in findings if f.level == "fail"])


class FrontMatterParsingTests(unittest.TestCase):
    def test_url_with_scheme_survives_the_colon_split(self) -> None:
        fm, _, _ = uir.split_front_matter(fx.BASE_SPEC)
        self.assertEqual(
            "https://design.example.invalid/file/DEMOFILE?node-id=100-200",
            fm["states"][0]["url"],
        )

    def test_quoted_node_id_keeps_its_inner_colon(self) -> None:
        fm, _, _ = uir.split_front_matter(fx.BASE_SPEC)
        self.assertEqual("100:200", fm["states"][0]["node_id"])

    def test_integer_and_string_scalars(self) -> None:
        fm, _, _ = uir.split_front_matter(fx.BASE_SPEC)
        self.assertEqual(0, fm["tbd_count"])
        self.assertEqual("393x852", fm["frame_size"])

    def test_multiple_states_parse_as_separate_mappings(self) -> None:
        fm, _, _ = uir.split_front_matter(MULTI_STATE_SPEC)
        self.assertEqual(["default", "pressed"], [s["name"] for s in fm["states"]])


if __name__ == "__main__":
    unittest.main()
