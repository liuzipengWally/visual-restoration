"""Fixture builders for the visual-restoration tests.

The base spec and log are deliberately *valid*: every test mutates one thing and
asserts that exactly that thing is caught. A base fixture that only passes by
accident makes every negative test meaningless.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

RETRIEVED_AT = "2026-01-15T10:00:00Z"

BASE_SPEC = f"""---
screen: choice-dialog
platform: android
design_language: ExampleUI
impl_target: compose
figma_file_key: DEMOFILE
scroll_axis: none
frame_size: 393x852
states:
  - name: default
    node_id: "100:200"
    url: https://design.example.invalid/file/DEMOFILE?node-id=100-200
    baseline: ./assets/default.png
requirement_ref: REQ-0001
retrieved_at: {RETRIEVED_AT}
tbd_count: 0
---

## Requirement Anchor

Choice dialog, letting a user choose one of six categories for a record.
This example ships the 6 built-in categories only, with no custom category.
Copy is authoritative in the requirement.

## Design Source

Design file DEMOFILE / 100:200, metadata plus screenshot.

## Visual Baseline

default: `./assets/default.png`, frame 393x852, does not scroll. The dialog sits
in the lower half of the screen, title at the top left, 6 category rows stacked
vertically, one cancel button at the bottom right.

## State Inventory

| State | Trigger | Baseline | Difference from default |
|---|---|---|---|
| default | open the dialog | ./assets/default.png | — |

## State Variance

| Element | Dimension | default | Note |
|---|---|---|---|
| Dialog | shape | 16dp | single state, no variance |

## Visible Elements

| Element | Figma node | Description |
|---|---|---|
| Title | 100:210 | dialog title |
| Dialog | 100:211 | dialog container |
| TitleAlias | 100:210 | alias used by alignment cases |
| Card | 100:211 | container whose padding is measurable |
| Screen | 100:200 | the frame's content root |
| RowItem | 100:212 | one category row |

## Draft But Visible

| Element | Figma node | Requirement call | Reason |
|---|---|---|---|
| SystemOverlay | 100:213 | excluded | device shell, not app content |

## Explicitly Excluded

| Element | Figma node | Reason | Owner | Needs review |
|---|---|---|---|---|
| OptionalRow | 100:214 | custom category is out of scope in this example | product owner | yes |

## Exact Metrics

| Element | Property | Value |
|---|---|---|
| Dialog | corner-radius | 16dp |

## Visual Tokens

| Usage | Type | Repository token | Design value | Mark | Reference |
|---|---|---|---|---|---|
| title color | color | ExampleColor.neutral_0 | #000000 | reuse | example-ui/.../ExampleColor.kt |

## Asset Inventory

| asset | Type | Repository name | Mark | Reference | Variant |
|---|---|---|---|---|---|
| check icon | icon | ExampleIcons.Check | reuse | example-ui/.../ExampleIcons.kt | vector |

## Copy And Labels

| copy | Authoritative source |
|---|---|
| Category | requirement §3.2 |

## Platform Adaptation

| Design form | Implementation here | Carried Dimension | Dropped Dimension |
|---|---|---|---|
| platform grouped-list separator | ExampleUI Divider | color | geometry |

## Do Not Build

| Element | Figma node | Category | Reason |
|---|---|---|---|
| Container | 100:215 | scaffold | design-tool structural container, absent at runtime |
| System/Home Indicator | 100:216 | system-chrome | owned by the OS |
| SystemOverlay | 100:213 | draft | device shell, not app content |
| OptionalRow | 100:214 | excluded | custom category is out of scope in this example |

## Pending Decisions

None.

## Not Derivable

Dialog enter/exit motion, landscape layout, overflow behaviour of an
over-long label.

## Restoration Checklist

| ID | State | Element | Dimension | Expected | Source |
|---|---|---|---|---|---|
| R-001 | * | Title | copy | `Category` | requirement §3.2 |
| R-002 | * | Title | typography | 17sp / 700 / 20sp / -0.2 | design 100:210 |
| R-003 | * | Dialog | shape/corner-radius | 16dp | design 100:211 |
| R-004 | * | Title | token | ExampleColor.neutral_0 | design var 100:210 |
| R-020 | * | RowItem | asset | ExampleIcons.Check | design 100:212 |
"""

BASE_LADDER = """# Evidence ladder — test project

## T0 source

- means: read the source directly
- trigger: no build required
- output: file and line
- observes-dimensions: token, component, copy, asset
- blind-dimensions: geometry, spacing, shape, typography, color, visibility, interaction

## T1 static render

- means: <this project's preview/snapshot capability>
- trigger: <command>
- output: <directory>
- observes-dimensions: geometry, spacing, shape, typography, color, visibility, copy, asset
- blind-dimensions: token, interaction

## T2 runtime

- means: <this project's on-device capture capability>
- trigger: <command>
- output: <directory>
- observes-dimensions: geometry, spacing, shape, typography, color, visibility, copy, asset, interaction
- blind-dimensions: token

## T3 platform fallback

- available: no
- observes-dimensions: geometry, spacing, visibility, copy
- blind-dimensions: token, color, shape, typography, asset, interaction
"""

# Note the tier split: `token` is judged by T0 (free, reads source) while the
# geometry rows need T1. That is the cost ladder working as designed.
BASE_LOG = """---
screen: choice-dialog
spec: ./design-spec.md
round: 1
---

## Round 1 — 2026-09-03T11:00Z

Evidence tiers used: T0 source + T1 static render

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
| R-001 | * | restored | Category | T1 default.png crop(24,24,64,24) | |
| R-002 | * | restored | 17sp/700/20sp/-0.2 | T1 default.png crop(24,24,64,24) | |
| R-003 | * | restored | 16dp | T1 default.png crop(0,236,393,380) | |
| R-004 | * | restored | ExampleColor.neutral_0 | T0 ChoiceDialogScreen.kt:88 | |
| R-020 | * | restored | ExampleIcons.Check | T0 ChoiceDialogScreen.kt:140 | |

### Sweep

| Difference | State | Evidence | Disposition | Ref |
|---|---|---|---|---|
| none observed | default | T1 default.png vs ./assets/default.png | — | — |
"""

# A round whose sweep found something. `covered` may only point at a row that
# is not restored, so the pair has to move together.
SWEPT_LOG = BASE_LOG.replace(
    "| R-003 | * | restored | 16dp | T1 default.png crop(0,236,393,380) | |",
    "| R-003 | * | unrestored | 20dp | T1 default.png crop(0,236,393,380) | corner is 20dp |",
).replace(
    "| none observed | default | T1 default.png vs ./assets/default.png | — | — |",
    "| dialog corner looks softer | default | T1 default.png vs ./assets/default.png | covered | R-003 |",
)


def make_repo(tmp: Path) -> Path:
    """A minimal repository root the ladder lookup can anchor on."""
    (tmp / ".agents" / "visual-restoration").mkdir(parents=True, exist_ok=True)
    return tmp


def make_ladder(repo: Path, text: str = BASE_LADDER) -> Path:
    path = repo / ".agents" / "visual-restoration" / "evidence-ladder.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_screen(
    repo: Path,
    *,
    requirement: str = "REQ-0001",
    screen: str = "choice-dialog",
    spec: str = BASE_SPEC,
    states: tuple = ("default",),
    meta: dict | None = None,
    write_meta: bool = True,
) -> Path:
    """Materialize `specs/<req>/ui-implement/<screen>/` with spec and assets."""
    screen_dir = repo / "specs" / requirement / "ui-implement" / screen
    (screen_dir / "assets").mkdir(parents=True, exist_ok=True)
    (screen_dir / "design-spec.md").write_text(spec, encoding="utf-8")
    for state in states:
        (screen_dir / "assets" / f"{state}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    if write_meta:
        if meta is None:
            meta = {
                "retrieved_at": RETRIEVED_AT,
                "figma_file_key": "DEMOFILE",
                "states": {
                    state: {"node_id": "100:200", "fingerprint": f"sha256:{state}"}
                    for state in states
                },
            }
        (screen_dir / "assets" / "source-meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return screen_dir


def make_log(screen_dir: Path, text: str = BASE_LOG) -> Path:
    path = screen_dir / "restoration.md"
    path.write_text(text, encoding="utf-8")
    return path


def spec_path(screen_dir: Path) -> Path:
    return screen_dir / "design-spec.md"


def messages(findings) -> str:
    return "\n".join(f.message for f in findings)
