# evidence-ladder.md template

For v3 record design extraction, available component/asset facts and conventions,
measurement units/conversions, capture environment, dependency fingerprint scope,
and per-platform validation status (live validated / fixture-only / unverified).
Do not infer availability from the presence of a test configuration alone.

Engineering-level location: `.agents/visual-restoration/evidence-ladder.md`. A
requirement-level `specs/<requirement>/ui-implement/evidence-ladder.md`
overrides it and takes priority. Both paths are relative to the target project,
not the installed skill or the command's working directory. This optional cache
holds reusable capability facts, not task screenshots, measurements or reports;
those belong in the task's specs artifact directory. When a capability exports to
a temporary/tool-owned location, archive evidence used in the report under specs.

**Discover only what is needed, cache and recheck it.** It records what carries each
cost tier *in this project* -- that is project data, which is why it does not
live in the skill. The skill holds only the tier definitions and how to discover
them.

The `## T<n>` heading format and the three field names
`observes-dimensions` / `blind-dimensions` / `available` must be preserved
verbatim: `status` finds them by name.

---

## How to discover capabilities

This cache is optional, not a prerequisite adapter implementation. Project facts
do not preselect the right component; the skill compares design requirements with
inspected candidates. No generic DOM collector, native driver or startup commands
belong in the skill. Discover existing capabilities and respect operation authority.

In descending priority:

1. **Calling context** -- the caller (a workflow or an outer process) already
   named the evidence procedure. If so, use it and stop discovering.
2. **The repository's skill / tool registry** -- scan registration points such
   as `.agents/skills/`, `.claude/skills/`, `AGENTS.md`, and **match on
   capability description**: screenshot / snapshot / preview / visual / baseline
   / golden / layout dump / UI comparison / a11y. **Never hardcode a name.**
3. **Test and build configuration** -- which UI render, snapshot, or screenshot
   tasks can actually be run.
4. **Existing evidence artifacts** -- screenshot directories, baseline
   directories, and reports already in the repository; work backwards to how
   they were produced.
5. **Platform-native fallback** -- when none of the above exists, use T3: what
   the platform gives for free, with no change to the project under test.

If unavailable, record affected requirements as unverified. Ask only when a
material choice/authority is needed; lack of a capture tool is not permission to
provision infrastructure, change flags or invent data.

## Dimension vocabulary

`observes-dimensions` / `blind-dimensions` accept only these values, the same
set as the checklist's `Dimension` column:

`copy` `typography` `color` `geometry` `spacing` `shape` `asset` `visibility` `component` `interaction` `token`

`token` is the **identity** of a design-system token (which token), while
`color` / `typography` / `shape` are the **rendered values**. The distinction is
the point: almost any runtime capture can see a color value but not which token
it came from -- and "right value, wrong token" drifts the next time the theme
changes.

---

## Template

```markdown
# Evidence ladder — [project]

Discovered on [date]. Recheck stale entries before relying on them.

Design sources: [node/region retrieval capabilities and limitations].
Code facts: [API/version/docs/asset rules; no preselected component answer].
Units and normalization: [raw and normalized units, scale, conversion evidence].
Build provenance: [running-build association and relevant dependency snapshot method].
Data: [how required conditions can be supplied within existing authority].
Validation status: [live validated / fixture-only / unverified, with evidence].

## T0 source

- means: [read the source directly / AST scan]
- trigger: no build required
- output: file and line
- observes-dimensions: token, component, copy, asset
- blind-dimensions: geometry, spacing, shape, typography, color, visibility, interaction

## T1 static render

- means: [this project's preview/snapshot capability, in the project's own words]
- trigger: [command or entry point]
- output: [where screenshots and layout data land]
- observes-dimensions: geometry, spacing, shape, typography, color, visibility, copy, asset
- blind-dimensions: token, interaction

## T2 runtime

- means: [this project's device/simulator capture capability]
- trigger: [command or entry point]
- output: [where screenshots and dumps land]
- observes-dimensions: geometry, spacing, shape, typography, color, visibility, copy, asset, interaction
- blind-dimensions: token

## T3 platform-native fallback

- available: no
- means: [what the platform gives for free, e.g. UI/a11y dump plus screencap]
- trigger: [command]
- output: [location]
- observes-dimensions: geometry, spacing, visibility, copy
- blind-dimensions: token, color, shape, typography, asset, interaction
```

---

## Filling it in

- **Write `means` in the project's own words.** This file is project data, so it
  may name concrete tools, scripts, and test classes in this repository. The
  skill itself may not.
- **Be honest in `blind-dimensions`.** It is what lets `status` reject "a tier
  that cannot see a token declared a token restored". Too wide and checks are
  missed; too narrow and rows that could pass get stuck as `unverified`.
- Prefer the existing capability that can observe the required property/state;
  a higher-cost fallback can fill a specific blind spot without repeating all rows.
- When both fields are given, `blind-dimensions` wins. When only
  `observes-dimensions` is given, any dimension outside it counts as
  unobservable.
