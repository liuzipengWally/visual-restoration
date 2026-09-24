"""Contract tests: the skill stays portable, and the templates stay in sync.

Two things drift silently and are expensive when they do:

1. A specific tool name creeping into the skill's own instructions, which turns
   "runs in any repository" into "runs in this one".
2. A template heading or column drifting away from what `uir.py` looks for, so a
   correctly filled template fails validation.

Both are cheap to pin down mechanically, so they are pinned down here.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

import fixtures as fx  # noqa: E402
import uir  # noqa: E402

ROOT = fx.ROOT
SKILL_MD = ROOT / "SKILL.md"
REFERENCES = sorted((ROOT / "references").glob("*.md"))

# Names too generic to match as substrings without false positives.
GENERIC_SKILL_NAMES = {"base"}


def skill_docs() -> dict:
    docs = {SKILL_MD.name: SKILL_MD.read_text(encoding="utf-8")}
    for ref in REFERENCES:
        docs[f"references/{ref.name}"] = ref.read_text(encoding="utf-8")
    return docs


def sibling_skill_names(root: Path = ROOT) -> list:
    skills_dir = root.parent
    if not skills_dir.is_dir():
        return []
    names = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir() or child.name == root.name:
            continue
        if not (child / "SKILL.md").is_file():
            continue
        if child.name in GENERIC_SKILL_NAMES:
            continue
        names.append(child.name)
    return names


def named_skill_references(docs: dict, names: list) -> list:
    return [f"{doc} mentions `{name}`" for doc, text in docs.items()
            for name in names if name in text]


class PortabilityTests(unittest.TestCase):
    def test_no_sibling_skill_is_named_in_instructions_or_templates(self) -> None:
        names = sibling_skill_names()
        offenders = named_skill_references(skill_docs(), names)
        self.assertEqual(
            [],
            offenders,
            "skill instructions and artifact templates must not hardcode any concrete "
            "skill name -- project-specific facts belong in evidence-ladder.md",
        )

    def test_standalone_package_needs_no_sibling_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'isolated-skill'
            root.mkdir()
            self.assertEqual([], sibling_skill_names(root))
            self.assertEqual([], named_skill_references({'SKILL.md': 'Portable instructions'}, []))

    def test_synthetic_sibling_reference_is_still_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'isolated-skill'
            for name in (root.name, 'fixture-provider', 'base'):
                (Path(tmp) / name).mkdir()
            (Path(tmp) / 'fixture-provider' / 'SKILL.md').write_text('---\nname: fixture-provider\n---\n')
            names = sibling_skill_names(root)
            self.assertEqual(['fixture-provider'], names)
            self.assertEqual(['SKILL.md mentions `fixture-provider`'],
                             named_skill_references({'SKILL.md': 'Must use fixture-provider'}, names))

    def test_no_dependency_on_a_retired_workflow(self) -> None:
        for doc, text in skill_docs().items():
            self.assertNotIn("aether", text.lower(), f"{doc} must not depend on a retired workflow")

    def test_no_dependency_on_a_specific_orchestrator_artifact(self) -> None:
        for doc, text in skill_docs().items():
            self.assertNotRegex(
                text,
                r"\.agents/goals|goal\.md|task-bundles|task-manifest",
                f"{doc} must not depend on some orchestrator's state file",
            )

    def test_scripts_use_only_the_standard_library(self) -> None:
        source = (ROOT / "scripts" / "uir.py").read_text(encoding="utf-8")
        imports = set(re.findall(r"^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)", source, re.M))
        allowed = {
            "__future__",
            "argparse",
            "dataclasses",
            "json",
            "pathlib",
            "re",
            "sys",
            "evidence",  # bundled standard-library-only verifier
            "mapping",  # shared v3 mapping validation
            "cli_output",  # bundled standard-library-only CLI encoding policy
        }
        self.assertEqual(set(), imports - allowed, "uir.py may use the standard library only")


class TemplateSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec_tpl = (ROOT / "references" / "design-spec-template.md").read_text(
            encoding="utf-8"
        )
        cls.log_tpl = (ROOT / "references" / "restoration-template.md").read_text(
            encoding="utf-8"
        )
        cls.ladder_tpl = (ROOT / "references" / "evidence-ladder-template.md").read_text(
            encoding="utf-8"
        )
        cls.skill = SKILL_MD.read_text(encoding="utf-8")

    def test_spec_template_carries_every_required_section(self) -> None:
        headings = set(re.findall(r"^##\s+(.+?)\s*$", self.spec_tpl, re.M))
        missing = [s for s in uir.REQUIRED_SECTIONS if s not in headings]
        self.assertEqual([], missing, "the template is missing a section check-spec requires")

    def test_spec_template_sections_are_in_the_checked_order(self) -> None:
        order = [
            h
            for h in re.findall(r"^##\s+(.+?)\s*$", self.spec_tpl, re.M)
            if h in uir.REQUIRED_SECTIONS
        ]
        self.assertEqual(uir.REQUIRED_SECTIONS, order)

    def test_checklist_columns_match_the_checker(self) -> None:
        for col in ["ID", "State", "Element", "Dimension", "Expected", "Source"]:
            self.assertIn(f"| {col} |", self.spec_tpl.replace("|\n", "|"))

    def test_verdict_columns_match_the_checker(self) -> None:
        self.assertIn("| ID | State | Verdict | Measured | Evidence | Action/Reason |", self.log_tpl)

    def test_sweep_columns_match_the_checker(self) -> None:
        """The sweep is the backstop; the template and the gate must not drift.

        `parse_rounds` finds the sweep by the `Difference` column and
        `_gate_sweep` requires `Disposition` and `Ref`, so a template that
        renamed one would produce logs the gate silently ignores -- the worst
        possible failure for a backstop.
        """
        self.assertIn("| Difference | State | Evidence | Disposition | Ref |", self.log_tpl)

    def test_every_disposition_is_documented(self) -> None:
        for disposition in uir.SWEEP_DISPOSITIONS:
            self.assertIn(f"`{disposition}`", self.log_tpl)

    def test_the_sweep_template_parses_with_the_real_parser(self) -> None:
        """The fenced example must be a working sweep, not decorative markdown."""
        rounds = uir.parse_rounds(self.log_tpl)
        self.assertTrue(rounds, "the template has no parseable round")
        sweep = rounds[0].get("sweep")
        self.assertIsNotNone(sweep, "the template's sweep table is not discoverable")
        for col in ("Difference", "State", "Evidence", "Disposition", "Ref"):
            self.assertIn(col, sweep.header)

    def test_dimension_vocabulary_is_identical_everywhere(self) -> None:
        for name, text in (
            ("design-spec-template.md", self.spec_tpl),
            ("evidence-ladder-template.md", self.ladder_tpl),
        ):
            for dim in uir.DIMENSIONS:
                self.assertIn(f"`{dim}`", text, f"{name} is missing dimension `{dim}`")

    def test_resource_marks_are_documented(self) -> None:
        for mark in uir.RESOURCE_MARKS:
            self.assertIn(mark, self.spec_tpl)

    def test_do_not_build_categories_are_documented(self) -> None:
        for category in uir.DO_NOT_BUILD_CATEGORIES:
            self.assertIn(category, self.spec_tpl)

    def test_ladder_template_documents_the_fields_status_parses(self) -> None:
        for field in ["observes-dimensions", "blind-dimensions", "available"]:
            self.assertIn(field, self.ladder_tpl)
        for tier in ["T0", "T1", "T2", "T3"]:
            self.assertRegex(self.ladder_tpl, rf"##\s+{tier}\b")

    def test_ladder_template_parses_with_the_real_parser(self) -> None:
        """The fenced example must be a working ladder, not decorative markdown."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence-ladder.md"
            path.write_text(self.ladder_tpl, encoding="utf-8")
            tiers = uir.parse_ladder(path)
        self.assertEqual(["T0", "T1", "T2", "T3"], sorted(tiers))
        self.assertIn("token", tiers["T0"]["observes"])
        self.assertIn("token", tiers["T1"]["blind"])
        self.assertIn("token", tiers["T2"]["blind"])
        self.assertFalse(tiers["T3"]["available"])

    def test_unfilled_template_cannot_pass_as_a_spec(self) -> None:
        """Shipping the template as a spec must be impossible, not merely rude."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = fx.make_repo(Path(tmp))
            screen = fx.make_screen(repo, spec=self.spec_tpl)
            findings, _ = uir.check_spec(fx.spec_path(screen))
        self.assertTrue([f for f in findings if f.level == "fail"])


class SkillDocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_MD.read_text(encoding="utf-8")

    def test_front_matter_declares_name_and_description(self) -> None:
        fm, _, _ = uir.split_front_matter(self.skill)
        self.assertEqual("visual-restoration", fm.get("name"))
        self.assertGreater(len(str(fm.get("description", ""))), 200)

    def test_description_mentions_both_phases_and_the_requirement_gate(self) -> None:
        fm, _, _ = uir.split_front_matter(self.skill)
        description = str(fm.get("description", ""))
        for needle in ["specifications", "verif", "evidence", "platforms"]:
            self.assertIn(needle, description)

    def test_both_subcommands_are_documented(self) -> None:
        self.assertIn("check-spec", self.skill)
        self.assertIn("status", self.skill)

    def test_references_are_all_linked_from_the_skill(self) -> None:
        for ref in REFERENCES:
            self.assertIn(ref.name, self.skill, f"SKILL.md does not reference {ref.name}")

    def test_documented_commands_exist_in_parser(self) -> None:
        for cmd in ('check-map', 'verify', 'status', 'check-spec'):
            self.assertIn(cmd, self.skill)
            self.assertTrue(callable(uir.build_parser().parse_args([cmd, 'fixture']).func))

    def test_scroll_axis_rule_states_both_sides(self) -> None:
        self.assertIn("the height of each section and element", self.skill)
        self.assertIn("whole frame's absolute height", self.skill)


if __name__ == "__main__":
    unittest.main()
