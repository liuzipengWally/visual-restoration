#!/usr/bin/env python3
"""uir.py -- visual-restoration checks.

Commands (standard library only):

    uir.py check-spec <design-spec.md>
    uir.py check-map <evidence.json>
    uir.py verify <evidence.json>
    uir.py status <restoration.md | ui-implement-dir>

Standard library only, on purpose: this skill has to run in any repository
without first installing anything there.

Exit codes are the same shape for both commands:
    0  requested check passed (check-spec is documents only, check-map is mapping only)
    1  valid, but work remains (including legacy evidence awaiting migration)
    2  a gate failed -- the artifact cannot be trusted as-is
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from cli_output import configure_utf8_output

# --------------------------------------------------------------------------
# Vocabulary and policy. Everything project-specific lives in the repository's
# evidence-ladder.md, never here.
# --------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "Requirement Anchor",
    "Design Source",
    "Visual Baseline",
    "State Inventory",
    "State Variance",
    "Visible Elements",
    "Draft But Visible",
    "Explicitly Excluded",
    "Exact Metrics",
    "Visual Tokens",
    "Asset Inventory",
    "Copy And Labels",
    "Platform Adaptation",
    "Do Not Build",
    "Pending Decisions",
    "Not Derivable",
    "Restoration Checklist",
]

# The checklist's Dimension column must start with one of these, so that an evidence
# tier's declared blind spots can be matched against it mechanically.
DIMENSIONS = [
    "copy",
    "typography",
    "color",
    "geometry",
    "spacing",
    "shape",
    "asset",
    "visibility",
    "component",
    "interaction",
    "token",
]

# The word lists below are detection *inputs*, not user-facing text: they are
# matched against cells an author wrote. Specs in this repository are authored in
# either language, so both vocabularies stay listed. Dropping the non-English
# entries would not simplify anything -- it would silently stop catching a vague
# value written in Chinese, which is the exact failure this table exists to
# prevent.

# Prose approximations that defeat the whole point of an exact-metrics table.
VAGUE_WORDS = [
    "roughly",
    "approximately",
    "approx",
    "about",
    "around",
    "similar",
    "appropriate",
    "reasonable",
    "sensible",
    "some",
    "several",
    "larger",
    "smaller",
    "大约",
    "大概",
    "类似",
    "差不多",
    "合适",
    "适当",
    "若干",
    "一些",
    "较大",
    "较小",
    "偏大",
    "偏小",
]

# An alignment is a real, exact value for an alignment dimension -- there is no
# number to give. The same word standing in for a position that *does* have a
# measurement is the abstraction this table exists to prevent, so these are
# rejected everywhere except on an alignment row.
ALIGNMENT_WORDS = [
    "centered",
    "aligned",
    "leading",
    "trailing",
    "居中",
    "靠左",
    "靠右",
    "居左",
    "居右",
]
ALIGNMENT_DIMENSION = re.compile(r"alignment|align|对齐")

# A trailing hedge after a measurement turns an exact value into a range. In
# Chinese `左右` means "left and right" as often as it means "approximately";
# only the latter follows a number, which is why this is a regex and not a word.
APPROXIMATION_RE = re.compile(
    r"\d\s*(?:dp|sp|px|pt|%)?\s*(?:or so|ish|左右|上下|前后)"
)

# Whole-frame metrics are meaningless on a scroll axis: a design tool draws a
# scrollable page as one tall static frame, so the frame is taller than the
# viewport by construction.
FRAME_METRIC_WORDS = [
    "frame height",
    "frame width",
    "full frame",
    "whole frame",
    "total height",
    "整帧",
    "帧高",
    "帧宽",
    "全屏高",
    "总高度",
]

DO_NOT_BUILD_CATEGORIES = ["scaffold", "system-chrome", "draft", "excluded"]

RESOURCE_MARKS = ["reuse", "new", "TBD"]
VERDICTS = ["restored", "unrestored", "unverified", "adapted"]

# `Exact Metrics` states a property in prose; the checklist states a dimension
# from the vocabulary. Coverage can only be checked mechanically if the two can
# be joined, so a property word maps to the dimension that would carry it. Both
# vocabularies are listed for the same reason the vague-word lists are: a spec
# here is authored in either language.
# Order matters and the specific must come first: `geometry` claims the word
# `size`, so `font-size` has to be matched by `typography` before it is reached.
METRIC_PROPERTY_DIMENSIONS: list[tuple[tuple[str, ...], str]] = [
    (("font", "typeface", "line-height", "letter-spacing", "weight",
      "字号", "字体", "行高", "字重"), "typography"),
    (("padding", "margin", "inset", "gap", "spacing", "内边距", "外边距", "内缩", "间隔", "间距"), "spacing"),
    (("radius", "corner", "圆角"), "shape"),
    (("color", "opacity", "颜色", "透明"), "color"),
    (("height", "width", "size", "offset", "position", "align",
      "高度", "宽度", "尺寸", "容器", "偏移", "位置", "对齐"), "geometry"),
]

FM_REQUIRED = [
    "screen",
    "platform",
    "design_language",
    "impl_target",
    "scroll_axis",
    "frame_size",
    "requirement_ref",
    "retrieved_at",
    "tbd_count",
]
STATE_REQUIRED = ["name", "baseline"]

MAX_SAME_REASON = 3


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    level: str  # "fail" | "open"
    where: str  # "file:line" or "file"
    message: str

    def render(self) -> str:
        tag = "FAIL" if self.level == "fail" else "OPEN"
        return f"  [{tag}] {self.where}: {self.message}"


@dataclass
class Row:
    cells: dict
    line: int

    def get(self, key: str, default: str = "") -> str:
        return (self.cells.get(key) or default).strip()


@dataclass
class Table:
    header: list
    rows: list = field(default_factory=list)


# --------------------------------------------------------------------------
# Parsing. A deliberately small YAML subset: scalars plus one list-of-mappings
# (`states`). Our own template is the only input, so the subset is enough and
# the skill stays dependency-free.
# --------------------------------------------------------------------------


def split_front_matter(text: str) -> tuple:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text, 0
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            fm = parse_front_matter(lines[1:idx])
            return fm, "\n".join(lines[idx + 1 :]), idx + 1
    return {}, text, 0


def _scalar(raw: str):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if raw in ("true", "false"):
        return raw == "true"
    return raw


def parse_front_matter(lines: list) -> dict:
    data: dict = {}
    key_stack: list = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("- "):
            # A list item. Only list-of-mappings is supported, which is all the
            # template uses (`states`).
            parent = key_stack[-1][1] if key_stack else None
            if not isinstance(parent, list):
                i += 1
                continue
            item: dict = {}
            first = stripped[2:]
            if ":" in first:
                k, v = first.split(":", 1)
                item[k.strip()] = _scalar(v)
            item_indent = indent + 2
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent < item_indent or nxt.strip().startswith("- "):
                    break
                if ":" in nxt:
                    k, v = nxt.strip().split(":", 1)
                    item[k.strip()] = _scalar(v)
                i += 1
            parent.append(item)
            continue

        if ":" in stripped:
            key, raw = stripped.split(":", 1)
            key = key.strip()
            while key_stack and key_stack[-1][0] >= indent:
                key_stack.pop()
            container = data
            if raw.strip() == "":
                value: list = []
                container[key] = value
                key_stack.append((indent, value))
            else:
                container[key] = _scalar(raw)
        i += 1
    return data


def parse_sections(body: str, offset: int) -> dict:
    """Map `## Heading` -> (text, start_line). Deeper headings stay inside."""
    sections: dict = {}
    current = None
    buf: list = []
    start = 0
    for n, line in enumerate(body.splitlines(), start=offset + 1):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            if current is not None:
                sections[current] = ("\n".join(buf), start)
            current = m.group(1).strip()
            buf = []
            start = n
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = ("\n".join(buf), start)
    return sections


def parse_tables(block: str, start_line: int) -> list:
    """Every pipe table in a block, as Table objects with source line numbers."""
    tables: list = []
    current: Table | None = None
    for n, line in enumerate(block.splitlines(), start=start_line + 1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            current = None
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if current is None:
            current = Table(header=cells)
            tables.append(current)
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        if len(cells) < len(current.header):
            cells += [""] * (len(current.header) - len(cells))
        current.rows.append(Row(cells=dict(zip(current.header, cells)), line=n))
    return [t for t in tables if t.rows]


def first_table(sections: dict, name: str) -> Table | None:
    if name not in sections:
        return None
    body, start = sections[name]
    tables = parse_tables(body, start)
    return tables[0] if tables else None


def dimension_of(cell: str) -> str:
    """`color/background` -> `color`. The part before the slash must be canonical."""
    return cell.split("/", 1)[0].strip()


PLACEHOLDER_RE = re.compile(r"[\[<][^\[\]<>]*[\]>]")


def is_placeholder(value: str) -> bool:
    """Template leftovers like `[value]dp`, `[hex]` or `<key>` are not real values.

    Matches a bracketed *segment*, not the whole cell: `[value]dp` is exactly the
    shape a half-filled template leaves behind.
    """
    return bool(PLACEHOLDER_RE.search(value.strip()))


def is_blank(value) -> bool:
    """Empty for our purposes. `0` is a real value; an empty list is not.

    The front-matter subset parses a bare `key:` as an empty container, so a key
    written with no value arrives here as `[]` rather than `""`.
    """
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return not value
    return not str(value).strip()


# --------------------------------------------------------------------------
# check-spec
# --------------------------------------------------------------------------


@dataclass
class SpecDoc:
    """One spec under inspection, plus what each check hands to the next."""

    path: Path
    rel: str
    fm: dict
    sections: dict
    findings: list = field(default_factory=list)
    state_names: list = field(default_factory=list)
    checklist: Table | None = None
    checklist_keys: set = field(default_factory=set)
    tbd: int = 0
    # Coverage between tables can only be computed once they share element
    # names. While they do not, a coverage report would be noise.
    namespace_clean: bool = True

    def fail(self, where: str, msg: str) -> None:
        self.findings.append(Finding("fail", where, msg))

    def open_item(self, msg: str) -> None:
        self.findings.append(Finding("open", self.rel, msg))

    def at(self, line: int) -> str:
        return f"{self.rel}:{line}"

    def table(self, name: str) -> Table | None:
        return first_table(self.sections, name)

    def bucket(self, name: str) -> dict:
        """Element -> source line, skipping template rows and `none` markers."""
        table = self.table(name)
        if table is None:
            return {}
        col = "Element" if "Element" in table.header else table.header[0]
        out: dict = {}
        for row in table.rows:
            element = row.get(col)
            if (
                not element
                or element.lower() in ("none", "n/a", "-", "—", "无")  # sentinel, either language
                or is_placeholder(element)
            ):
                continue
            out.setdefault(element, row.line)
        return out


def _check_sections(doc: SpecDoc) -> None:
    for name in REQUIRED_SECTIONS:
        if name not in doc.sections:
            doc.fail(doc.rel, f"missing required section `## {name}`")


def _check_front_matter(doc: SpecDoc) -> None:
    """Also fills `doc.state_names`, which later checks key off."""
    if not doc.fm:
        doc.fail(doc.rel, "missing YAML frontmatter")
    for key in FM_REQUIRED:
        if key not in doc.fm or is_blank(doc.fm[key]):
            doc.fail(doc.rel, f"frontmatter key is missing or empty: `{key}`")
    if is_blank(doc.fm.get("requirement_ref")):
        doc.fail(doc.rel, "`requirement_ref` is missing or empty -- a spec without a requirement is "
            "blocked and must not reach implementation")

    states = doc.fm.get("states") or []
    if not isinstance(states, list) or not states:
        doc.fail(doc.rel, "frontmatter `states` must be a non-empty list with at least one state")
        return

    for idx, state in enumerate(states):
        if not isinstance(state, dict):
            doc.fail(doc.rel, f"`states[{idx}]` is malformed")
            continue
        for key in STATE_REQUIRED:
            if not str(state.get(key, "")).strip():
                doc.fail(doc.rel, f"`states[{idx}]` is missing `{key}`")
        if not state.get('source_ref') and not (state.get('node_id') and state.get('url')):
            doc.fail(doc.rel, f"`states[{idx}]` needs source_ref (node or screenshot region), or historical node_id and url")
        name = str(state.get("name", "")).strip()
        if name:
            if name in doc.state_names:
                doc.fail(doc.rel, f"duplicate state name: `{name}`")
            doc.state_names.append(name)

        baseline = str(state.get("baseline", "")).strip()
        if baseline and not (doc.path.parent / baseline).exists():
            doc.fail(doc.rel, f"baseline screenshot for state `{name}` does not exist: `{baseline}`")


def _check_assets(doc: SpecDoc) -> None:
    """The fingerprint and the spec must come from the same retrieval."""
    meta_path = doc.path.parent / "assets" / "source-meta.json"
    if not meta_path.exists():
        doc.fail(doc.rel, "missing `assets/source-meta.json` -- the design-source fingerprint used "
            "to detect drift")
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        doc.fail("assets/source-meta.json", f"is not valid JSON: {exc}")
        return
    if not isinstance(meta, dict):
        doc.fail("assets/source-meta.json", "top level must be an object")
        return
    if str(meta.get("retrieved_at", "")) != str(doc.fm.get("retrieved_at", "")):
        doc.fail(
            "assets/source-meta.json",
            "`retrieved_at` disagrees with the spec frontmatter -- the fingerprint and "
            "the spec did not come from the same retrieval",
        )
    for name in doc.state_names:
        if name not in (meta.get("states") or {}):
            doc.fail("assets/source-meta.json", f"missing the design-source fingerprint for state `{name}`")


def _check_checklist(doc: SpecDoc) -> None:
    """The table the whole skill rests on. Also fills `doc.checklist_keys`."""
    doc.checklist = doc.table("Restoration Checklist")
    if doc.checklist is None:
        if "Restoration Checklist" in doc.sections:
            doc.fail(doc.rel, "`Restoration Checklist` has no table")
        return

    for col in ["ID", "State", "Element", "Dimension", "Expected", "Source"]:
        if col not in doc.checklist.header:
            doc.fail(doc.rel, f"`Restoration Checklist` is missing column `{col}`")

    scroll_axis = str(doc.fm.get("scroll_axis", "none")).strip()
    seen_ids: dict = {}

    for row in doc.checklist.rows:
        where = doc.at(row.line)
        rid = row.get("ID")
        if not re.fullmatch(r"R-\d{3,}", rid):
            doc.fail(where, f"checklist ID must look like `R-001`: `{rid}`")
        elif rid in seen_ids:
            doc.fail(where, f"duplicate checklist ID `{rid}` (also on line {seen_ids[rid]})")
        else:
            seen_ids[rid] = row.line

        dim_cell = row.get("Dimension")
        dim = dimension_of(dim_cell)
        if dim not in DIMENSIONS:
            doc.fail(where, f"dimension `{dim_cell}` is not in the vocabulary; expected one of "
                f"{'/'.join(DIMENSIONS)}")

        state = row.get("State")
        if state != "*" and state not in doc.state_names:
            doc.fail(where, f"state `{state}` is not among the frontmatter states and is not `*`")
        doc.checklist_keys.add((state, row.get("Element"), dim))

        _check_expected_value(doc, row, rid, where)

        if scroll_axis != "none":
            # Normalize separators: `full-frame-height`, `frame_height` and
            # `frame height` are the same claim, and an author picks whichever
            # reads best in the cell.
            probe = re.sub(r"[-_/]+", " ", f"{dim_cell} {row.get('Element')}".lower())
            if any(re.sub(r"[-_/]+", " ", word.lower()) in probe for word in FRAME_METRIC_WORDS):
                doc.fail(
                    where,
                    f"`{rid}` compares a whole-frame size while `scroll_axis: {scroll_axis}` -- "
                    "on a scroll axis the frame is taller than the viewport by "
                    "construction, so this is not a defect and does not belong in the table",
                )

        if not row.get("Source"):
            doc.fail(where, f"`{rid}` has no source -- it must point at `requirement §x`, "
                f"`figma <node_id>`, or `user-specified`")


def _check_expected_value(doc: SpecDoc, row: Row, rid: str, where: str) -> None:
    """Anti-abstraction: a measurable value, or an owned TBD. Nothing else."""
    expected = row.get("Expected")
    if expected.startswith("TBD"):
        if not re.match(r"TBD\s*[:：]\s*\S", expected):
            doc.fail(where, f"`{rid}` must spell its TBD as `TBD: reason`")
        doc.tbd += 1
        return
    if not expected:
        doc.fail(where, f"`{rid}` has an empty expected value -- give a concrete value or `TBD: reason`")
        return
    if is_placeholder(expected):
        doc.fail(where, f"`{rid}` still holds the template placeholder `{expected}` -- give a "
                f"concrete value or `TBD: reason`")
        return

    low = expected.lower()
    for word in VAGUE_WORDS:
        if word.lower() in low:
            doc.fail(where, f"`{rid}` expected value hedges with `{word}` -- it must be a measurable "
                f"concrete value")
            return

    match = APPROXIMATION_RE.search(expected)
    if match is not None:
        doc.fail(
            where,
            f"`{rid}` expected value is approximate (`{match.group(0)}`) -- it must be "
            "an exact value, not a range",
        )
        return

    if not ALIGNMENT_DIMENSION.search(row.get("Dimension")):
        for word in ALIGNMENT_WORDS:
            if word.lower() in low:
                doc.fail(
                    where,
                    f"`{rid}` uses `{word}` in place of a measurable fact -- if this row really "
                    "is about alignment, write the dimension as `geometry/alignment`; "
                    "otherwise give the number",
                )
                return


def metric_dimension(prop: str) -> str:
    """The checklist dimension that would carry an `Exact Metrics` property."""
    probe = re.sub(r"[-_/]+", " ", prop.lower())
    for words, dimension in METRIC_PROPERTY_DIMENSIONS:
        if any(word in probe for word in words):
            return dimension
    return ""


def _check_element_namespace(doc: SpecDoc) -> None:
    """One element namespace across the spec, declared by `Visible Elements`.

    Without this, `Exact Metrics` can measure `AppBarActions`, the checklist can
    assert `AppBarTitle`, and `Visible Elements` can declare `AppBar` -- three
    names for one region, with no key to join them on. Coverage then cannot be
    checked mechanically, and a reader cannot check it either, which is how a
    measured padding silently never reaches the checklist.

    `Visible Elements` may declare a container or a group: a container's padding
    is a real measurable fact, so it needs a name here to be measurable at all.
    """
    declared = set(doc.bucket("Visible Elements"))
    if not declared:
        return
    do_not_build = set(doc.bucket("Do Not Build"))

    # One finding per undeclared name, not per row: a group name used on twelve
    # checklist rows is one thing to declare, and twelve copies of the same
    # message bury everything else.
    undeclared: dict = {}
    sources = [("Exact Metrics", doc.table("Exact Metrics")), ("State Variance", doc.table("State Variance"))]
    if doc.checklist is not None:
        sources.append(("Restoration Checklist", doc.checklist))
    for section, table in sources:
        if table is None or "Element" not in table.header:
            continue
        for row in table.rows:
            element = row.get("Element")
            if not element or is_placeholder(element) or element in do_not_build:
                continue
            if element not in declared:
                entry = undeclared.setdefault(element, {"line": row.line, "sections": set(), "rows": 0})
                entry["sections"].add(section)
                entry["rows"] += 1

    for element, entry in sorted(undeclared.items(), key=lambda kv: kv[1]["line"]):
        doc.namespace_clean = False
        where = ", ".join(sorted(entry["sections"]))
        doc.fail(
            doc.at(entry["line"]),
            f"`{element}` is used by {where} on {entry['rows']} row(s) but `Visible Elements` "
            f"never declares it. Declare every element there, including containers and "
            f"groups, so the tables share one namespace and coverage between them can be "
            f"checked at all",
        )


def _check_metric_coverage(doc: SpecDoc) -> None:
    """Every measured metric must reach the checklist.

    `Exact Metrics` is where Phase 1 records what it measured; the checklist is
    what Phase 2 actually compares. Nothing connected the two, so a spec could
    carry a rich metrics table and a thin checklist and pass -- the metric was
    written down and then never compared. This is the same cross-check that
    already guards `State Variance`, applied to the table that carries the
    numbers.
    """
    table = doc.table("Exact Metrics")
    if table is None or doc.checklist is None or "Element" not in table.header:
        return
    if not doc.namespace_clean:
        doc.fail(
            doc.rel,
            "metric coverage was not checked: the tables do not share one element namespace "
            "yet, so there is no key to join them on. Fix the undeclared elements above first",
        )
        return
    property_col = next(
        (c for c in table.header if c not in ("Element", "Value", "Note")), None
    )
    if property_col is None:
        return

    covered = {(element, dim) for _, element, dim in doc.checklist_keys}
    for row in table.rows:
        element = row.get("Element")
        prop = row.get(property_col)
        if not element or not prop or is_placeholder(element) or is_placeholder(prop):
            continue
        dimension = metric_dimension(prop)
        if not dimension:
            doc.fail(
                doc.at(row.line),
                f"`{element}` / `{prop}` does not map to a checklist dimension. Name the "
                f"property so it does, or move the row out of `Exact Metrics`",
            )
            continue
        if (element, dimension) not in covered:
            doc.fail(
                doc.at(row.line),
                f"`{element}` / `{prop}` is measured but no checklist row covers "
                f"`{element}` x `{dimension}` -- a metric written down and never compared "
                f"is not verified",
            )


# A table that declares a fact, the column holding it, and the checklist
# dimension that would compare it. Same principle as metric coverage: a fact
# the spec states and the checklist never asserts was written down and then
# never verified.
DECLARED_FACT_TABLES = [
    ("Visual Tokens", "Repository token", "token"),
    ("Asset Inventory", "Repository name", "asset"),
    ("Copy And Labels", "copy", "copy"),
]


def _check_declared_fact_coverage(doc: SpecDoc) -> None:
    """Tokens, assets and copy the spec declares must reach the checklist."""
    if doc.checklist is None or not doc.namespace_clean:
        return
    expected_by_dim: dict = {}
    for row in doc.checklist.rows:
        dim = dimension_of(row.get("Dimension"))
        expected_by_dim.setdefault(dim, []).append(row.get("Expected"))

    for section, column, dimension in DECLARED_FACT_TABLES:
        table = doc.table(section)
        if table is None or column not in table.header:
            continue
        haystack = " ".join(expected_by_dim.get(dimension, []))
        for row in table.rows:
            value = row.get(column)
            if not value or is_placeholder(value) or value in ("—", "-", "n/a"):
                continue
            # A `TBD` entry has nothing to compare yet; it is owned by Pending
            # Decisions and the TBD tally instead.
            if row.get("Mark") == "TBD":
                continue
            if value.strip("`") not in haystack:
                doc.fail(
                    doc.at(row.line),
                    f"`{section}` declares `{value}` but no checklist `{dimension}` row "
                    f"asserts it -- a declared fact the checklist never compares is not "
                    f"verified",
                )


def _check_token_rendered_pairs(doc: SpecDoc) -> None:
    """A `token` row proves identity, not the rendered value.

    `token` is judged from source, which shows which token is referenced and
    says nothing about what it renders as. Where the spec also states a rendered
    value for that element, the rendered dimension needs its own row, or a wrong
    size passes because only the token was ever checked.
    """
    if doc.checklist is None or not doc.namespace_clean:
        return
    by_element: dict = {}
    for _, element, dim in doc.checklist_keys:
        by_element.setdefault(element, set()).add(dim)

    metrics = doc.table("Exact Metrics")
    stated: dict = {}
    if metrics is not None and "Element" in metrics.header:
        property_col = next(
            (c for c in metrics.header if c not in ("Element", "Value", "Note")), None
        )
        for row in metrics.rows or []:
            dimension = metric_dimension(row.get(property_col) if property_col else "")
            if dimension in ("typography", "color", "shape"):
                stated.setdefault(row.get("Element"), set()).add(dimension)

    for element, dims in sorted(by_element.items()):
        if "token" not in dims:
            continue
        missing = sorted(stated.get(element, set()) - dims)
        if missing:
            doc.fail(
                doc.rel,
                f"`{element}` has a `token` row but no `{'`/`'.join(missing)}` row, while the "
                f"spec states that rendered value. A token row is judged from source and "
                f"proves which token is referenced, not what it renders as",
            )


def _check_state_differences(doc: SpecDoc) -> None:
    """A dimension declared to vary needs a row per state, never a `*` row."""
    diff = doc.table("State Variance")
    if diff is None or doc.checklist is None:
        return
    state_cols = [c for c in diff.header if c not in {"Element", "Dimension", "Note"}]
    for row in diff.rows:
        values = {c: row.get(c) for c in state_cols}
        if len({v for v in values.values() if v}) <= 1:
            continue  # declared as not varying
        dim = dimension_of(row.get("Dimension"))
        element = row.get("Element")
        where = doc.at(row.line)
        if ("*", element, dim) in doc.checklist_keys:
            doc.fail(
                where,
                f"`{element}` declares `{dim}` as state-dependent, but the checklist asserts "
                "a single value with `*`; the two contradict each other, so split it "
                "into one row per state",
            )
        for col, val in values.items():
            if not val or col not in doc.state_names:
                continue
            if (col, element, dim) not in doc.checklist_keys:
                doc.fail(
                    where,
                    f"`{element}` declares `{dim}` as varying in state `{col}`, but the "
                    f"checklist has no matching `{col}` row",
                )


def _check_tokens_and_resources(doc: SpecDoc) -> None:
    """Every token and asset is reuse / new / TBD, and each owes evidence."""
    for name, subject_col in (("Visual Tokens", "Usage"), ("Asset Inventory", "asset")):
        table = doc.table(name)
        if table is None:
            if name in doc.sections:
                doc.fail(doc.rel, f"`{name}` has no table")
            continue
        for col in ["Mark", "Reference"]:
            if col not in table.header:
                doc.fail(doc.rel, f"`{name}` is missing column `{col}`")
        subject = subject_col if subject_col in table.header else table.header[0]
        for row in table.rows:
            where = doc.at(row.line)
            item = row.get(subject) or "(unnamed)"
            mark = row.get("Mark")
            if mark not in RESOURCE_MARKS:
                doc.fail(where, f"`{item}` has an invalid mark `{mark}`; expected one of "
                                f"{'/'.join(RESOURCE_MARKS)}")
                continue
            note = row.get("Reference")
            if mark == "new" and (not note or is_placeholder(note)):
                doc.fail(where, f"`{item}` is marked `new`, so it must name the existing asset rule it "
                                f"follows and where that rule lives")
            elif mark == "reuse" and (not note or is_placeholder(note)):
                doc.fail(where, f"`{item}` is marked `reuse`, so it must name the existing item in this "
                                f"repository and where it lives")
            elif mark == "TBD":
                doc.tbd += 1
                if not note:
                    doc.fail(where, f"`{item}` is marked `TBD`, so it must state the reason")


def _check_tbd_count(doc: SpecDoc) -> None:
    declared = doc.fm.get("tbd_count")
    if isinstance(declared, int) and declared != doc.tbd:
        doc.fail(doc.rel, f"`tbd_count: {declared}` disagrees with the {doc.tbd} TBD(s) actually present")


def _check_buckets(doc: SpecDoc) -> None:
    """`Do Not Build` is the single authoritative do-not-build table.

    `Draft But Visible` and `Explicitly Excluded` are the *reason* records for two of its
    categories, so their elements must also appear there -- an implementer only
    reads the one table. What must never happen is an element being both
    buildable and not.
    """
    visible = doc.bucket("Visible Elements")
    draft = doc.bucket("Draft But Visible")
    excluded = doc.bucket("Explicitly Excluded")
    do_not_build = doc.bucket("Do Not Build")

    for element, line in visible.items():
        if element in do_not_build:
            doc.fail(
                doc.at(line),
                f"`{element}` appears in both `Visible Elements` and `Do Not Build` -- one "
                "element cannot be both built and not built",
            )
    for name, bucket in (("Draft But Visible", draft), ("Explicitly Excluded", excluded)):
        for element, line in bucket.items():
            if element not in do_not_build:
                doc.fail(
                    doc.at(line),
                    f"`{element}` is recorded in `{name}` but never reaches `Do Not Build` -- "
                    "an implementer reads only Do Not Build, so a reason filed nowhere "
                    "else has no effect",
                )
    for element, line in draft.items():
        if element in excluded:
            doc.fail(
                doc.at(line),
                f"`{element}` appears in both `Draft But Visible` and `Explicitly Excluded` "
                "-- the two reason buckets are mutually exclusive, so pick one",
            )

    # You do not measure what you do not build. This is the mechanical form of
    # "the unit of comparison is not a design-tool node": a bulk-waiver replay
    # produced 49 findings because 26 of its 41 elements were scaffolding nobody would ever
    # implement, and every one of them could only be failed or waived.
    if doc.checklist is not None:
        checklist_elements: dict = {}
        for row in doc.checklist.rows:
            checklist_elements.setdefault(row.get("Element"), row.line)
        for element, line in do_not_build.items():
            if element in checklist_elements:
                doc.fail(
                    doc.at(checklist_elements[element]),
                    f"`{element}` is in `Do Not Build` yet also in the checklist -- something "
                    f"that is not built must not be measured (Do Not Build line {line})",
                )

    table = doc.table("Do Not Build")
    if table is None:
        return
    if "Category" not in table.header:
        doc.fail(doc.rel, "`Do Not Build` is missing column `Category`")
        return
    col = "Element" if "Element" in table.header else table.header[0]
    for row in table.rows:
        element = row.get(col)
        if not element or is_placeholder(element) or element in ("none", "None", "—", "无"):
            continue
        category = row.get("Category")
        if category not in DO_NOT_BUILD_CATEGORIES:
            doc.fail(
                doc.at(row.line),
                f"`{element}` has an invalid category `{category}`; expected one of "
                f"{'/'.join(DO_NOT_BUILD_CATEGORIES)}",
            )


# Order matters: front matter fills state names, the checklist fills the keys
# that the namespace, coverage, pairing and state-difference checks all read,
# and both the checklist and the token tables contribute to the TBD tally.
SPEC_CHECKS = [
    _check_sections,
    _check_front_matter,
    _check_assets,
    _check_checklist,
    _check_element_namespace,
    _check_metric_coverage,
    _check_declared_fact_coverage,
    _check_token_rendered_pairs,
    _check_state_differences,
    _check_tokens_and_resources,
    _check_tbd_count,
    _check_buckets,
]


def check_spec(path: Path) -> tuple:
    rel = path.name
    if not path.exists():
        return [Finding("fail", rel, "file does not exist")], 0

    fm, body, offset = split_front_matter(path.read_text(encoding="utf-8"))
    doc = SpecDoc(path=path, rel=rel, fm=fm, sections=parse_sections(body, offset))

    for check in SPEC_CHECKS:
        check(doc)

    if doc.tbd:
        doc.open_item(f"{doc.tbd} TBD(s) still open -- resolve before implementing affected UI")

    return doc.findings, doc.tbd


# --------------------------------------------------------------------------
# evidence ladder
# --------------------------------------------------------------------------


def find_ladder(spec_dir: Path, repo_root: Path) -> Path | None:
    """Requirement-level override wins over the project-level ladder."""
    candidates = [
        spec_dir.parent / "evidence-ladder.md",
        repo_root / ".agents" / "visual-restoration" / "evidence-ladder.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def parse_ladder(path: Path) -> dict:
    """`## T0 ...` blocks -> {tier: {"observes": [...], "blind": [...]}}."""
    tiers: dict = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(T\d)\b", line.strip())
        if m:
            current = m.group(1)
            tiers[current] = {"observes": [], "blind": [], "available": True}
            continue
        if current is None:
            continue
        m = re.match(r"^[-*]\s*(observes-dimensions|blind-dimensions|available)\s*[:：]\s*(.*)$", line.strip())
        if not m:
            continue
        field_name, raw = m.group(1), m.group(2)
        if field_name == "available":
            tiers[current]["available"] = raw.strip().lower() not in ("no", "false", "unavailable", "否")
            continue
        items = [dimension_of(x) for x in re.split(r"[,，/、]\s*", raw) if x.strip()]
        key = "observes" if field_name == "observes-dimensions" else "blind"
        tiers[current][key] = [x for x in items if x]
    return tiers


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


ROUND_RE = re.compile(r"^##\s+Round\s+(\d+)\b")


def parse_rounds(text: str) -> list:
    rounds: list = []
    current = None
    for n, line in enumerate(text.splitlines(), start=1):
        m = ROUND_RE.match(line.strip())
        if m:
            current = {"n": int(m.group(1)), "lines": [], "start": n}
            rounds.append(current)
        elif current is not None:
            current["lines"].append(line)
    for r in rounds:
        block = "\n".join(r["lines"])
        tables = parse_tables(block, r["start"])
        r["table"] = tables[0] if tables else None
        # The sweep is the round's second table: the checklist is a closed
        # world, so something has to ask what differs that no row asked about.
        r["sweep"] = next(
            (t for t in tables[1:] if "Difference" in t.header),
            None,
        )
    return rounds


SWEEP_DISPOSITIONS = ("covered", "new-row", "do-not-build", "adapted")


def spec_state_names(spec_path: Path) -> list:
    """State names from the spec frontmatter, for sweep coverage."""
    if not spec_path.exists():
        return []
    fm, _, _ = split_front_matter(spec_path.read_text(encoding="utf-8"))
    states = fm.get("states")
    if not isinstance(states, list):
        return []
    return [str(s.get("name")).strip() for s in states if isinstance(s, dict) and s.get("name")]


def _gate_sweep(
    rel: str,
    sweep: Table | None,
    dim_map: dict,
    verdicts: dict,
    state_names: list | None = None,
) -> list:
    """Every observed difference must land somewhere nameable.

    The checklist only compares what it lists, which makes Phase 1 enumeration
    a single point of failure with no backstop: a padding nobody thought to
    enumerate is never compared, and the loop reports done. The sweep is that
    backstop -- look at the two images, list what differs, and give each
    difference an exit. A difference with no disposition is the silence this
    skill exists to reject.
    """
    findings: list = []
    if sweep is None:
        return findings
    for col in ("Difference", "Disposition", "Ref"):
        if col not in sweep.header:
            findings.append(Finding("fail", rel, f"sweep table is missing column `{col}`"))
            return findings

    # Every state needs sweeping, not just the one that was easiest to capture.
    # A pressed or error state is exactly where an unenumerated difference
    # hides, and sweeping only `default` would report the screen as swept.
    if state_names and "State" in sweep.header:
        swept = {row.get("State") for row in sweep.rows}
        missing = [name for name in state_names if name not in swept and "*" not in swept]
        if missing:
            findings.append(
                Finding("fail", rel, f"the sweep never covers state(s) `{'`/`'.join(missing)}` -- "
                    f"an unenumerated difference hides in the states that were not looked at")
            )

    for row in sweep.rows:
        difference = row.get("Difference")
        if not difference or is_placeholder(difference):
            continue
        # "Swept and found nothing" is a real, recordable outcome: the sweep
        # happened, which is what the gate asks. Same sentinel convention the
        # bucket tables use.
        if difference.lower() in ("none", "none observed", "n/a", "-", "—", "无"):
            continue
        where = f"{rel}:{row.line}"
        disposition = row.get("Disposition")
        ref = row.get("Ref")
        if disposition not in SWEEP_DISPOSITIONS:
            findings.append(
                Finding("fail", where, f"`{difference}` has disposition `{disposition}`; expected "
                    f"one of {'/'.join(SWEEP_DISPOSITIONS)}")
            )
            continue
        if not ref or is_placeholder(ref):
            findings.append(
                Finding("fail", where, f"`{difference}` is `{disposition}` but names nothing -- "
                    f"a disposition without a reference disposes of nothing")
            )
            continue
        if disposition in ("covered", "new-row", "adapted"):
            if ref not in dim_map:
                findings.append(
                    Finding("fail", where, f"`{difference}` points at `{ref}`, which is not a "
                        f"checklist row. For `new-row`, add the row to the spec and re-run "
                        f"check-spec first")
                )
            elif disposition == "covered" and verdicts.get(ref) == "restored":
                findings.append(
                    Finding("fail", where, f"`{difference}` says `{ref}` covers it, but `{ref}` is "
                        f"judged restored. A visible difference cannot sit behind a restored row")
                )
    return findings


def _operative_rows(rounds: list) -> list:
    """The most recent judgment for each id, across the rounds given.

    Rounds are partial by design -- each one takes the previous round's
    remainder -- so the current state of the screen is the union of the latest
    verdict per id, not the contents of any single round.
    """
    latest: dict = {}
    for entry in rounds:
        if entry["table"] is None:
            continue
        for row in entry["table"].rows:
            rid = row.get("ID")
            if rid:
                latest[rid] = row
    return list(latest.values())


def spec_dimension_map(spec_path: Path) -> dict:
    """ID -> (State, Element, Dimension) from the spec's checklist."""
    if not spec_path.exists():
        return {}
    text = spec_path.read_text(encoding="utf-8")
    _, body, offset = split_front_matter(text)
    table = first_table(parse_sections(body, offset), "Restoration Checklist")
    if table is None:
        return {}
    return {
        row.get("ID"): (row.get("State"), row.get("Element"), dimension_of(row.get("Dimension")))
        for row in table.rows
        if row.get("ID")
    }


@dataclass
class ScreenStatus:
    screen: str
    round_no: int
    counts: dict
    remaining: list
    findings: list
    prev_unrestored: int | None
    stalled: bool
    unjudged: list = field(default_factory=list)
    # How many verdicts each tier carried. A round can be all green while
    # almost every row was judged by reading source, which proves token
    # identity and never looks at the rendered screen. That ratio decides how
    # much a clean result is worth, and it was previously invisible.
    tier_counts: dict = field(default_factory=dict)
    # The checklist is a closed world, so a round without a sweep never asked
    # what differs outside it. That cannot be reported as done.
    sweep_missing: bool = True


def _gate_restored(rid: str, evidence: str, where: str, dim_map: dict, tiers: dict) -> list:
    """`restored` owes evidence, a tier, and a tier that can see the dimension.

    The last one is the only blind-spot rule this skill keeps, because a blind
    spot read as a match is its own failure mode one level down.
    """
    if not evidence or evidence in ("-", "—"):
        return [Finding("fail", where, f"`{rid}` is restored but its evidence is empty -- evidence must point at a "
                f"concrete location")]

    match = re.match(r"^(T\d)\b", evidence)
    if match is None:
        return [
            Finding("fail", where, f"`{rid}` evidence does not name its tier (it must start with "
                    f"`T0`/`T1`/`T2`/`T3`)")
        ]
    tier = match.group(1)

    if not tiers or rid not in dim_map:
        return []
    if tier not in tiers:
        return [
            Finding("fail", where, f"`{rid}` evidence tier `{tier}` is not defined in the evidence ladder")
        ]

    dim = dim_map[rid][2]
    if dim not in DIMENSIONS:
        # Blaming the tier here would send the reader to the ladder, when the
        # actual defect is in the spec.
        return [
            Finding(
                "fail",
                where,
                f"`{rid}` has dimension `{dim}` in the spec, which is not in the vocabulary "
                "-- run check-spec and fix the spec first",
            )
        ]

    blind = tiers[tier]["blind"]
    observes = tiers[tier]["observes"]
    if dim in blind or (observes and dim not in observes):
        return [
            Finding(
                "fail",
                where,
                f"`{rid}` has dimension `{dim}`, which tier `{tier}` cannot observe -- "
                "treating a blind spot as a match is this method's own failure mode",
            )
        ]
    return []


def status_one(path: Path, repo_root: Path) -> ScreenStatus:
    rel = path.name
    findings: list = []
    text = path.read_text(encoding="utf-8")
    fm, body, offset = split_front_matter(text)
    screen = str(fm.get("screen", path.parent.name))

    spec_rel = str(fm.get("spec", "./design-spec.md"))
    spec_path = (path.parent / spec_rel).resolve()
    dim_map = spec_dimension_map(spec_path)
    if not dim_map:
        findings.append(
            Finding("fail", rel, f"cannot read the spec checklist `{spec_rel}` -- the dimension behind each "
                f"verdict cannot be checked")
        )

    ladder_path = find_ladder(path.parent, repo_root)
    tiers = parse_ladder(ladder_path) if ladder_path else {}
    if not tiers:
        findings.append(
            Finding(
                "fail",
                rel,
                "cannot find evidence-ladder.md, at the engineering level "
                "(`.agents/visual-restoration/`) or beside the requirement -- whether an "
                "evidence tier can observe a dimension cannot be decided",
            )
        )

    rounds = parse_rounds(body if offset else text)
    if not rounds:
        return ScreenStatus(screen, 0, {v: 0 for v in VERDICTS}, [], findings, None, False)

    rounds.sort(key=lambda r: r["n"])
    latest = rounds[-1]
    prev_unrestored = None
    if len(rounds) >= 2:
        prev_unrestored = sum(
            1 for row in _operative_rows(rounds[:-1]) if row.get("Verdict") == "unrestored"
        )

    counts = {v: 0 for v in VERDICTS}
    remaining: list = []
    reasons: dict = {}

    table = latest["table"]
    if table is None:
        findings.append(Finding("fail", rel, f"Round {latest['n']} has no verdict table"))
        return ScreenStatus(screen, latest["n"], counts, remaining, findings, prev_unrestored, False)

    for col in ["ID", "Verdict", "Evidence"]:
        if col not in table.header:
            findings.append(Finding("fail", rel, f"Round {latest['n']} verdict table is missing column `{col}`"))

    # A round deliberately judges only the previous round's remainder, so the
    # operative verdict for an id is its most recent one across all rounds --
    # not whatever the last round happened to contain. Counting round-locally
    # drops every item an earlier round left open, which under-reports the work
    # that is still outstanding.
    for row in _operative_rows(rounds):
        where = f"{rel}:{row.line}"
        rid = row.get("ID")
        verdict = row.get("Verdict")
        evidence = row.get("Evidence")
        reason = row.get("Action/Reason")

        if verdict not in VERDICTS:
            findings.append(
                Finding("fail", where, f"`{rid}` has an invalid verdict `{verdict}`; expected one of "
                            f"{'/'.join(VERDICTS)}")
            )
            continue
        counts[verdict] += 1

        if dim_map and rid not in dim_map:
            findings.append(Finding("fail", where, f"`{rid}` does not exist in the spec checklist"))

        if verdict == "restored":
            findings.extend(_gate_restored(rid, evidence, where, dim_map, tiers))

        if verdict == "adapted":
            if not reason:
                findings.append(
                    Finding("fail", where, f"`{rid}` is adapted but states no reason -- an adaptation must be justified "
                        f"row by row")
                )
            else:
                key = re.sub(r"\s+", " ", reason).strip()
                reasons.setdefault(key, []).append(rid)

        if verdict in ("unrestored", "unverified"):
            label = dim_map.get(rid)
            desc = f"{label[1]} {label[2]}" if label else ""
            remaining.append(f"{rid} ({desc.strip()}) [{verdict}]" if desc else f"{rid} [{verdict}]")
            if verdict == "unrestored" and not row.get("Measured"):
                findings.append(
                    Finding("fail", where, f"`{rid}` is unrestored but states no measured value")
                )
            if verdict == "unverified" and not reason:
                findings.append(
                    Finding("fail", where, f"`{rid}` is unverified but does not say why evidence could not be obtained")
                )

    for reason, ids in reasons.items():
        if len(ids) > MAX_SAME_REASON:
            findings.append(
                Finding(
                    "fail",
                    rel,
                    f"one adapted reason covers {len(ids)} rows ({', '.join(ids[:5])}...), over "
                    f"the limit of {MAX_SAME_REASON} -- a reason that blankets many rows "
                    "is not a reason",
                )
            )

    stalled = (
        prev_unrestored is not None
        and counts["unrestored"] > 0
        and counts["unrestored"] >= prev_unrestored
    )

    # A round may legitimately judge only part of the checklist -- cheap tiers go
    # first. What must never happen is the loop reporting done while rows were
    # never judged at all: that is the same silence-as-pass this skill exists to
    # stop, one level up from an unverified row.
    judged: set = set()
    for entry in rounds:
        if entry["table"] is None:
            continue
        for row in entry["table"].rows:
            rid = row.get("ID")
            if rid:
                judged.add(rid)
    unjudged = [rid for rid in dim_map if rid not in judged] if dim_map else []

    tier_counts: dict = {}
    for row in _operative_rows(rounds):
        match = re.match(r"\s*(T[0-3])\b", row.get("Evidence"))
        if match:
            tier_counts[match.group(1)] = tier_counts.get(match.group(1), 0) + 1

    latest_verdicts = {
        row.get("ID"): row.get("Verdict")
        for row in (latest["table"].rows if latest["table"] else [])
    }
    findings.extend(
        _gate_sweep(
            rel, latest.get("sweep"), dim_map, latest_verdicts, spec_state_names(spec_path)
        )
    )
    sweep_missing = latest.get("sweep") is None

    return ScreenStatus(
        screen,
        latest["n"],
        counts,
        remaining,
        findings,
        prev_unrestored,
        stalled,
        unjudged,
        tier_counts,
        sweep_missing,
    )


def render_status(st: ScreenStatus) -> str:
    out = [
        f"{st.screen} · round {st.round_no} · "
        f"restored {st.counts['restored']} / unrestored {st.counts['unrestored']} / "
        f"unverified {st.counts['unverified']} / adapted {st.counts['adapted']}"
    ]
    if st.prev_unrestored is not None:
        verdict = "STALLED" if st.stalled else "OK"
        out.append(f"ratchet: {st.prev_unrestored} → {st.counts['unrestored']}  {verdict}")
    if st.stalled:
        out.append("stalled: unrestored did not strictly decrease -- escalate the remainder to a "
            "person and stop the automatic loop")
    if st.tier_counts:
        total = sum(st.tier_counts.values())
        by_tier = " / ".join(f"{tier} {st.tier_counts[tier]}" for tier in sorted(st.tier_counts))
        # T0 reads source: it proves which token is referenced and never looks
        # at the rendered screen. Say so when it carried most of the verdicts.
        source_only = st.tier_counts.get("T0", 0)
        note = ""
        if total and source_only * 2 > total:
            note = (
                f"  ({source_only}/{total} judged from source alone, which cannot see "
                f"a rendered size or spacing)"
            )
        out.append(f"evidence: {by_tier}{note}")
    if st.sweep_missing:
        out.append(
            "no sweep: this round never compared the baseline against the implementation "
            "outside the checklist, so a difference nobody enumerated would go unseen"
        )
    if st.remaining:
        out.append("remaining: " + ", ".join(st.remaining))
    if st.unjudged:
        shown = ", ".join(st.unjudged[:8])
        more = f" …(+{len(st.unjudged) - 8})" if len(st.unjudged) > 8 else ""
        out.append(f"unjudged ({len(st.unjudged)}): {shown}{more}")
    for f in st.findings:
        out.append(f.render())
    return "\n".join(out)


def exit_code_for(st: ScreenStatus) -> int:
    if any(f.level == "fail" for f in st.findings):
        return 2
    if st.counts["unrestored"] or st.counts["unverified"] or st.unjudged or st.sweep_missing:
        return 1
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def repo_root_for(path: Path) -> Path:
    for parent in [path.resolve()] + list(path.resolve().parents):
        if (parent / ".git").exists() or (parent / ".agents").is_dir():
            return parent
    return Path.cwd()


def cmd_check_spec(args) -> int:
    path = Path(args.path)
    findings, _ = check_spec(path)
    fails = [f for f in findings if f.level == "fail"]
    opens = [f for f in findings if f.level == "open"]
    if fails:
        print(f"check-spec: FAIL ({len(fails)} finding(s)) -- {path}")
        for f in fails:
            print(f.render())
        for f in opens:
            print(f.render())
        return 2
    if opens:
        print(f"check-spec: OPEN — {path}")
        for f in opens:
            print(f.render())
        return 1
    print(f"check-spec: PASS (document only; run check-map before implementation and verify for acceptance) — {path}")
    return 0


def cmd_status(args) -> int:
    target = Path(args.path)
    # v3 status and verify have one source of truth; prose cannot override either.
    if target.is_dir():
        screens = {p.parent for name in ('evidence.json', 'restoration.md', 'design-spec.md')
                   for p in target.glob('*/' + name)}
        if (target / 'evidence.json').exists():
            return cmd_verify(argparse.Namespace(path=str(target / 'evidence.json')))
        if screens and any((s / 'evidence.json').exists() for s in screens):
            return max(cmd_verify(argparse.Namespace(path=str(s / 'evidence.json'))) for s in sorted(screens))
    else:
        bundle = target if target.name == 'evidence.json' else target.parent / 'evidence.json'
        if bundle.exists():
            return cmd_verify(argparse.Namespace(path=str(bundle)))
    print('LEGACY DOCUMENT DIAGNOSTIC ONLY: missing evidence.json; visual acceptance unverified')
    root = repo_root_for(target)
    if target.is_dir():
        logs = sorted(target.glob("*/restoration.md"))
        if not logs:
            print(f"status: no restoration.md under {target}")
            return 2
        worst = 0
        totals = {v: 0 for v in VERDICTS}
        for log in logs:
            st = status_one(log, root)
            print(render_status(st))
            print()
            for k in totals:
                totals[k] += st.counts[k]
            worst = max(worst, exit_code_for(st))
            bundle = log.parent / 'evidence.json'
            worst = max(worst, cmd_verify(argparse.Namespace(path=str(bundle))) if bundle.exists() else 1)
        print(
            f"{len(logs)} screen(s) total - restored {totals['restored']} / "
            f"unrestored {totals['unrestored']} / unverified {totals['unverified']} / "
            f"adapted {totals['adapted']}"
        )
        return worst
    if not target.exists():
        print(f"status: file does not exist -- {target}")
        return 2
    st = status_one(target, root)
    print(render_status(st))
    bundle = target.parent / 'evidence.json'
    acceptance = cmd_verify(argparse.Namespace(path=str(bundle))) if bundle.exists() else 1
    return max(exit_code_for(st), acceptance)


def cmd_verify(args) -> int:
    from evidence import verify
    try:
        report = verify(Path(args.path))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'complete': False, 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] else 1


def cmd_check_map(args) -> int:
    from mapping import check_map
    try:
        report = check_map(Path(args.path))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({'mapping_complete': False, 'complete': False, 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['mapping_complete'] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uir.py", description="visual-restoration checks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("check-spec", help="validate a design-spec.md")
    p1.add_argument("path")
    p1.set_defaults(func=cmd_check_spec)

    p2 = sub.add_parser("status", help="compute the same acceptance as verify; diagnose prose-only history without accepting it")
    p2.add_argument("path")
    p2.set_defaults(func=cmd_status)
    p3 = sub.add_parser('verify', help='compute v3 acceptance; v2 is diagnostic and requires migration')
    p3.add_argument('path')
    p3.set_defaults(func=cmd_verify)
    p4 = sub.add_parser('check-map', help='check v3 design/code mapping without requiring runtime captures')
    p4.add_argument('path')
    p4.set_defaults(func=cmd_check_map)
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    configure_utf8_output()
    sys.exit(main())
