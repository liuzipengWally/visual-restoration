# design-spec.md template

For missing/mismatched assets, follow `resource-workflow.md`. Record the exact
source node/export, original, variant, project target and conversion path. Split
each icon from its parent control; add silhouette and `visibility/resource-loaded`
requirements. An imported file is not a verified resource. Link its provenance
record through the matching element in evidence.json.

Copy to `<project-root>/specs/<requirement>/ui-implement/<screen>/design-spec.md`
and fill in every section. project-root is the target project, not the skill
directory or shell cwd. Keep associated evidence in the same task artifact tree.

Use evidence-contract.md v3. Draft evidence.json before implementation, including
the source inventory, design-language findings and code mapping. The prose tables
are reviewable views of that mapping, not a separate competing specification.
Run check-spec for document structure and check-map for mapping readiness.

**Everything in square brackets is a placeholder and `check-spec` rejects them**
-- so this template does not pass validation as-is. That is deliberate: an
unfinished spec must not be used as a spec.

Section names and table column names must be preserved verbatim: `check-spec`
finds them by name. Keep the section order.

---

```yaml
---
screen: [kebab-case screen name, same as the directory]
platform: [android / ios / web / flutter / ...]
design_language: [known name / inferred name / unknown / mixed; details below]
impl_target: [compose / swiftui / uikit / react / ...]
scroll_axis: [none / vertical / horizontal]
frame_size: [393x852]
states:
  - name: [default]
    source_ref: [design document and node, or baseline image and crop]
    baseline: ./assets/[default].png
requirement_ref: [ticket key / document path / inline]
retrieved_at: [ISO8601, must match assets/source-meta.json]
tbd_count: 0
---
```

## Requirement Anchor

What business capability this screen carries -- enough to answer "why is this
element here". Scope for this release: which elements are built and which are
not. Authoritative source for copy. Cite requirement item numbers.

## Design Source

Design document/nodes or screenshot regions, retrieval method, date/fingerprint,
units/normalization and uncertainties. Save assets/source-meta.json with the
same retrieved_at and a states object keyed by state name. Each entry describes
the retrieved node fingerprint or screenshot hash; do not invent node metadata
when only a screenshot is available. Historical Figma frontmatter remains readable.

### Design language and implementation mapping

Keep design language, component system and technical platform separate. Names can
be unknown/inferred and a page can mix systems. Source/component identity is not
proof of rendered fidelity. The structured counterpart lives in evidence.json.

| Region / Element | Design language / confidence / evidence | Code candidate / system / exact parameters | Inspection / rationale / rejected competitor | Wrapper / theme / drawing dependencies |
|---|---|---|---|---|
| [Action] | [observed component origin or visual facts] | [reuse / adjust / new / pending and target] | [source location, API/version facts, comparison] | [config through wrappers to final surface] |

## Visual Baseline

The baseline image path per state, plus an **exact** description of the
composition (not "the layout is reasonable"), the frame size, and the scroll
axis.

## State Inventory

| State | Trigger | Baseline | Difference from default |
|---|---|---|---|
| [default] | [when this state is shown] | ./assets/[default].png | — |

## State Variance

State columns use the state names from the frontmatter. **List only what really
varies**; a row whose value is identical across states declares "does not vary
by state", and one `*` row in the checklist covers it.

If a row's value differs between states, the checklist must have **one row per
state** and may not use `*`.

| Element | Dimension | [default] | [pressed] | Note |
|---|---|---|---|---|
| [RowItem] | [color] | [neutral_base] | [neutral_b5] | [pressed feedback] |

## Visible Elements

Approved by the requirement and to be implemented.

| Element | Source node / screenshot region | Description |
|---|---|---|
| [Title] | [100:210] | [purpose] |

## Draft But Visible

Visible in Figma but rejected by the requirement: draft or leftover placeholder
work. **An element here must also appear in `Do Not Build`.**

| Element | Source node / screenshot region | Requirement call | Reason |
|---|---|---|---|
| [SystemOverlay] | [100:213] | [excluded] | [why this visible item must not be implemented] |

## Explicitly Excluded

Visible, genuinely app content, and deliberately out of scope this release.
**An element here must also appear in `Do Not Build`.**

| Element | Source node / screenshot region | Reason | Owner | Needs review |
|---|---|---|---|---|
| [OptionalRow] | [100:214] | [out of scope this release] | [product owner] | [yes] |

## Exact Metrics

Width, height, spacing, padding, margin, corner radius, alignment. A concrete
value per entry, or `TBD: reason`.

| Element | Property | Value |
|---|---|---|
| [Dialog] | [corner-radius] | [16dp] |

## Visual Tokens

`Mark` has three values: `reuse` (name the repository item and where it lives) /
`new` (name the existing rule it follows and where that rule lives) / `TBD`
(state the reason, and it goes to Pending Decisions).

| Usage | Type | Repository token | Design value | Mark | Reference |
|---|---|---|---|---|---|
| [title color] | [color] | [ExampleColor.neutral_0] | [#000000] | [reuse] | [file path] |

## Asset Inventory

Icons, images, fonts. Same three `Mark` values. `new` must name the rule it
follows and the density/size variants needed.

| asset | Type | Repository name | Mark | Reference | Variant |
|---|---|---|---|---|---|
| [check icon] | [icon] | [ExampleIcons.Check] | [reuse] | [file path] | [vector] |

## Copy And Labels

| copy | Authoritative source |
|---|---|
| [Label] | [requirement §3.2 / design / user-specified] |

## Platform Adaptation

Fill only for an authorized change to an actual visual requirement. A different
component system or adjusted implementation that preserves appearance is not an
adaptation. Cite the concrete authority, exact property, approved replacement
expectation, and preserved requirement IDs; no generic dropped dimension waiver.
Mirror these decisions in evidence.json adaptations and verify the replacement.

| Requirement / Property | Original expectation | Approved replacement | Authority / Reason | Preserved requirements |
|---|---|---|---|---|
| [R-ID / interaction/height] | [design size] | [approved target] | [specific authority] | [R-IDs still verified] |

## Do Not Build

**The single authoritative do-not-build list; an implementer reads only this
table.** It merges four categories: `scaffold` (design-tool structural
container), `system-chrome` (owned by the OS), `draft` (from "Draft But
Visible"), and `excluded` (from "Explicitly Excluded"). `Category` accepts only
those four values. An element here **must not** appear in the checklist.

| Element | Source node / screenshot region | Category | Reason |
|---|---|---|---|
| [Container] | [100:215] | [scaffold] | [design-tool structural container, absent at runtime] |
| [System/Home Indicator] | [100:216] | [system-chrome] | [owned by the OS] |

## Pending Decisions

TBDs, ambiguous tokens, assets awaiting creation, components with no match,
unresolved visual values. Resolve before implementing affected UI; missing runtime
capability belongs in verification limitations, not a made-up design decision.

## Not Derivable

Interaction, motion, responsive behaviour, edge states -- whatever a static
frame cannot yield. Mark it here and **do not invent it**.

### Data conditions

Record required business data per element/requirement, mirrored as applies_when
facts in evidence.json. Current data lacking a designed control leaves that
control unverified; it does not remove its requirements or authorize enabling it.
Use content/layout constraints for dynamic names and variable action counts.

## Restoration Checklist

The grain is **element × property × applicable state/data condition**. Independently
styled children need their own rows, including visibility. There is no row cap.

`State`: `*` = all states; a state name = that state only.
`Dimension` must start with a vocabulary term; use the exact semantic property
names in evidence-contract.md when linking core coverage entries. Additional
standalone detail may follow a `/`:
`copy` `typography` `color` `geometry` `spacing` `shape` `asset` `visibility` `component` `interaction` `token`.
`Expected` must be a concrete value or `TBD: reason`, never a hedge.
`Source` points at the authority: `requirement §x` / `figma <node_id>` /
`user-specified` / screenshot path plus crop. Runtime evidence is not a design source.

| ID | State | Element | Dimension | Expected | Source |
|---|---|---|---|---|---|
| R-001 | * | [HeaderTitle] | copy | [`Label`] | [requirement §3.2] |
| R-002 | * | [Title] | typography | [17sp / 700 / 20sp / -0.2] | [design 100:210] |
| R-003 | * | [Dialog] | shape/corner-radius | [16dp] | [design 100:211] |
| R-004 | * | [Title] | token | [ExampleColor.neutral_0] | [design var 100:210] |
