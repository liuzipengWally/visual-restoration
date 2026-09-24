# Visibility triage

Step 4 of Phase 1. This step decides what ends up in the checklist, so it
decides the whole skill's signal-to-noise ratio.

## Why it is mandatory

A designer duplicates an old screen and lays the new one on top. **The old nodes
are still there, carry no hidden flag, and are merely covered.** An agent
reading the node tree implements the union of two designs.

One measured frame: 50 retrieved nodes reduced to 17 elements. 26 subtrees were
discarded, taking 6 descendants with them, and **only 7 of those carried a
hidden flag**. Among the rest were a complete six-label bottom navigation and a
floating action button, both fully covered, both marked visible.

Another measurement: of 41 nodes, 26 were design-tool scaffolding (`Container`,
`Frame/Container`, `Grouped List`, `Status + App Wrap`, `Glass Effect`). Once
they entered the comparison they produced 49 findings, and a finding has only
two exits -- fail, or waive. All 49 were waived with one boilerplate sentence
and the report printed PASS. **That is the cost of skipping triage.**

## Compare visible evidence with available source structure

> **The baseline establishes visible appearance; available source structure
> supplies exact values. User scope and corrections determine what to build.**

With screenshot-only input, enumerate visible regions without inventing nodes or
hidden metadata. Record uncertainty where an exact value cannot be established.

Crop the baseline screenshot to a candidate node's box and **look at it**. Do
not read the node tree and guess.

## Three classes that must be checked

A script can propose candidates, but the call is made by looking. These three
classes are mandatory:

### 1. Occluded by a later layer

Node A's box is fully covered by node B, which comes later in document order.
For sources whose documented stacking order is back to front, B is on top of A.
Check the source capability's ordering convention rather than assuming it universally.

Crop to A's box: is what you see A's content, or B's?

### 2. Occluded by the **union** of later layers

No single later node covers A, but several together do. This class is the
easiest to miss -- single-node containment never detects it.

### 3. Near-full-frame shapes

Rectangles or frames sized close to the whole frame. Usually one of two things:
a backing plate the designer pasted in, or a dialog's scrim. The first must not
be implemented, the second must. **Only looking tells them apart.**

## When the call cannot be made

**Write `TBD`.**

An undecidable case becomes a question for the designer, and that is the correct
outcome. Guessing erases the reason this skill exists. Leaving a candidate
unfilled also counts as undecided, so "I forgot" cannot pass silently.

## Where things go

Once the call is made, triage by **requirement**, not by the design:

| Bucket | What goes in |
|---|---|
| `Visible Elements` | Rendered, and approved by the requirement |
| `Draft But Visible` | Rendered, but rejected by the requirement -- draft, placeholder, leftovers from a previous version |
| `Explicitly Excluded` | Rendered, genuinely app content, deliberately out of scope this release |
| `Do Not Build` | The two buckets above **plus** scaffolding **plus** system chrome |

**`Do Not Build` is the single authoritative do-not-build list** and an
implementer reads only it. The two reason tables above are records of *why*;
their elements must also appear in Do Not Build, and `check-spec` verifies that.

## Scaffolding vs system chrome

Both go to `Do Not Build`, under different categories, because the reasons
differ:

- **`scaffold`** -- a design-tool structural container with **no counterpart at
  runtime**: auto-layout groups, `Frame/Container`, wrappers that exist purely
  to align things.
- **`system-chrome`** -- **exists at runtime but is owned by the OS**: status
  bar, clock, battery, home indicator, notch, keyboard, device shell.

System chrome deserves particular suspicion: **it is fully visible**, so
visibility triage alone keeps it, and the spec ends up instructing you to
implement a phone.

The rule is **match the leaves, not their wrapper**. A measured trap: a header
frame contained both the status bar and the app bar, and matching by wrapper
discarded Cancel and Save along with it.

## After triage

Use available value-retrieval capabilities (for example Figma design context and
variable retrieval) **on surviving content roots**, not on the raw
nodes. Triaging first keeps discarded layers out of a code generator's output
entirely, which is far more reliable than filtering afterwards.

**Never infer copy from a layer name.** In a real file, a node named `🟡 Title`
rendered "Hello, Alice". A layer name is the designer's note, not the content.
