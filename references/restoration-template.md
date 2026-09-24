# restoration.md template

For new rounds use `evidence-contract.md` v3 and attach the immutable bundle and
computed `uir.py verify` report. The prose table below is a human summary, not
proof. Preserve historical rows; a new finding reopens affected rows even when
the previous round reported completion. Record superseded conclusions explicitly.

Copy to `<project-root>/specs/<requirement>/ui-implement/<screen>/restoration.md`.
Resolve project-root from the target project, not the skill or shell cwd. Archive
referenced temporary outputs in this task's artifact tree before delivery, keeping
their relative references and hashes valid; note unavailable dependencies.
**Append a section per round; never overwrite the previous one**. Reopened findings can
increase counts; there is no automatic strictly-decreasing ratchet.

The `## Round N` heading format and the table column names must be preserved
verbatim for historical document diagnostics. Current status uses evidence.json
and the same computation as verify; no prose verdict can override it.

---

```yaml
---
screen: [same as design-spec.md]
spec: ./design-spec.md
round: [current round]
---
```

## Round 1 — [ISO8601]

Evidence tiers used: [which tiers this round actually ran, and why no higher one did]

Mapping complete: [computed check-map result and remaining decisions].
Implementation complete: [scoped changes, dependency scope and engineering checks].
Visually verified: [computed verify result; fixture-only is not device validation].
Bundle / spec / computed report: [archived paths and fingerprints].
Build association / capture context: [running-build method, viewport, theme, units].
Unverified data conditions: [requirement IDs, missing controls/data, capabilities needed].
Reopened since prior round: [source/design/user findings and affected requirements].

| ID | State | Verdict | Measured | Evidence | Action/Reason |
|---|---|---|---|---|---|
| R-001 | * | restored | [Label] | T1 [default.png crop(24,24,64,24)] | |
| R-002 | * | unrestored | [20sp/700] | T1 [default.png crop(24,24,64,24)] | [used header2, should be header3] |
| R-003 | * | unverified | — | — | [the T1 tier cannot capture this state; needs T2] |
| R-004 | * | adapted | [observed approved replacement value] | T2 [capture locator] | [adaptation ID, exact property, authority and preserved requirements] |
| R-005 | * | restored | [ExampleColor.neutral_0] | T0 [Screen.kt:88] | |

### Sweep

Put the baseline and the implementation capture side by side and list **every**
visible difference, including ones no checklist row asked about. The checklist
only compares what it lists, so without this a difference nobody enumerated is
never compared and the round reports done anyway. `status` will not report done
for a round with no sweep.

| Difference | State | Evidence | Disposition | Ref |
|---|---|---|---|---|
| [card content sits closer to the edge than the design] | [default] | [T1 default.png vs ./assets/default.png] | [new-row] | [R-045] |
| [none observed] | [pressed] | [T1 pressed.png vs ./assets/pressed.png] | — | — |

Every difference gets exactly one disposition:

| Disposition | Meaning | `Ref` must name |
|---|---|---|
| `covered` | An existing checklist row already asserts this | that row's ID, and it may not be `restored` this round |
| `new-row` | No row asked about it, so the spec gains one | the new checklist row's ID, after `check-spec` passes again |
| `do-not-build` | The difference is an element that must not be built | the `Do Not Build` element |
| `adapted` | A deliberate platform adaptation | the row judged `adapted` |

`none observed` records that the sweep ran and found nothing, which is a real
outcome. A difference with no disposition is the silence this skill rejects.

Summary: restored [n] / unrestored [n] / unverified [n] / adapted [n]

## Round 2 — [ISO8601]

Handle remaining and reopened requirements and their dependencies. Reuse only
still-current evidence; compare the full page and controls for new omissions.

...

---

## How to fill this in

**Four verdicts, each with a hard requirement:**

| Verdict | Hard requirement |
|---|---|
| `restored` | Computed match in v3, traced to the correct state/data/build and actual observable property; prose includes a concrete capture/measurement location |
| `unrestored` | Must state the measured value. It is the next round's input |
| `unverified` | Must say in "Action/Reason" **why evidence could not be obtained**. Never counts as a pass |
| `adapted` | Authorized requirement/property replacement in v3, observed to match it, with preserved requirements verified; not a general library/platform waiver |

**Evidence format**: `<tier> <location>`. The location must let a reader go
straight to it:

- `T0 ChoiceDialogScreen.kt:88` -- file and line
- `T1 default.png crop(24,24,64,24)` -- screenshot crop coordinates
- `T1 RUN-01/portrait_light crop(24,24,64,24)` -- one capture out of a
  run that exported many, so the citation says which
- `T2 dump.xml //node[@resource-id="title"]` -- a locator inside a dump
- `T2 observed.png crop(0,236,393,380)` -- a runtime screenshot

Each adaptation cites its actual requirement and authority. A shared underlying
cause does not exempt independent properties from comparison. Component-system
identity changes without visual requirement changes are not adaptations.

Contradictory observations require resolution, never an authored green verdict.
An observed visual difference is unrestored; insufficient/conflicting provenance
or duplicate observations is unverified until resolved in a new bundle.

**Never hand-edit an already-judged row to turn it green.** Open a new round
instead.
