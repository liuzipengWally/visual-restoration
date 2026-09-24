# Recognizing multiple states

Step 2 of Phase 1. One screen usually has several frames in the design tool:
default, pressed, selected, disabled, expanded, error, empty, loading. The task
is to decide which links are **different states of the same screen** and which
are different screens.

## The asymmetry principle

**Merging wrongly is far worse than splitting wrongly.**

Merge wrongly and two different screens' checklists end up in one table, which
is very hard to notice -- every row looks reasonable, they just do not describe
the same thing. Split wrongly and the only cost is duplicated content across two
specs, which is obvious at a glance.

So: **do not merge by default.** Use scope and observable evidence; ask when a
material ambiguity remains. Availability of a person does not depend on phase.

## Signals, in descending reliability

### 1. The caller states it explicitly (most reliable; prefer this form)

```
screen=choice-dialog
states={default: <link>, pressed: <link>, disabled: <link>}
```

If this is given, use it and stop inferring.

### 2. Same file key plus a frame-naming family

`newContact_1` / `newContact_2`, `xxx/default` / `xxx/pressed`,
`xxx - default` / `xxx - selected`.

A naming family is a strong signal but not evidence -- a designer also uses `_1`
`_2` for "step one" and "step two", which are two screens.

### 3. Same file key plus overlapping structural skeleton

Same frame size, highly overlapping element-name sets, and differences confined
to a few nodes.

### 4. Visual similarity

The screenshots share an overall composition and differ locally.

## The test: what counts as "states of one screen"

**All four** must hold:

1. **The same navigation destination** -- not a jump to another screen
2. **The same viewport, or explicitly specified responsive variants**
3. **A highly overlapping structural skeleton**
4. **The differences are local visual changes** -- selected/disabled/expanded/
   error/empty/loading, not a swap of the main content

## A real counter-example

In one example, the `editor` screen and the `category` dialog looked like "two
screens of one flow"; in fact the latter is **a separate destination opened from
the former**.

The example separates them: they are two screens, each with its own spec and its own
checklist. The original split was right.

Why this matters: those two screens had 41 and 41 design elements. Merged into
one checklist, "which row belongs to which screen" could never be answered
again.

## How states land in the artifacts

**One screen = one `design-spec.md` + one `restoration.md` + N baseline
screenshots.**

The same screen also has one evidence.json v3 mapping/verification bundle.
Screenshot-only inputs can establish local visual differences without named
nodes. Include only evidenced states, not a mandatory default/hover/pressed list.

The thing that gets out of hand with multiple states is combinatorial
explosion: N states × M checks. The remedy is to **treat state as one dimension
of the checklist whose default value is "all states"**:

- In the checklist's `State` column, the large majority of rows are `*`, meaning
  every state must satisfy them
- Only rows that genuinely vary by state get one row per state

### `State Variance` is where that is declared

It records which dimensions of which elements vary by state. That is also **the
most valuable input to the implementation** -- it decides whether state needs to
be extracted at all, and how it should be modelled.

| Element | Dimension | default | pressed | Note |
|---|---|---|---|---|
| RowItem | color | neutral_base | neutral_b5 | pressed feedback |
| RowItem | visibility | check hidden | check shown | |
| Dialog | shape | 16dp | 16dp | unchanged |

The rules, which `check-spec` enforces:

- A row whose values are **identical** across states declares "does not vary by
  state", and one `*` row in the checklist covers it
- A row whose values **differ** across states must have **one checklist row per
  state**
- A row that declares variance while the checklist uses `*` is a
  **contradiction and fails validation** -- `*` asserts one value for all states

The last rule is worth explaining: why can a varying dimension not be covered by
a single `pressed` row? Because the default state's value is a real check too.
A `pressed` row alone means "the pressed state was implemented and the same
property was never checked in the default state".

## When a state cannot be captured

In Phase 2 some states may yield no evidence -- a static-render tier being
unable to capture a pressed state is common.

Judge it `unverified`, state the reason, and then **escalate to a tier that can
observe that state** per the ladder rules. Never mark it `restored` because it
could not be captured.
