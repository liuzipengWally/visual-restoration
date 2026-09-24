# Evidence contract v3

## What is checked

One human specification and one machine projection: `design-spec.md` retains
scope, source descriptions and the checklist; `evidence.json` retains structured
mapping and evidence. `restoration.md` summarizes computed results per round.
No authored verdict overrides measurements. Paths are relative to the bundle;
file references are `{path, sha256}` using SHA-256 content hashes. The bundle lives
in the target project's task artifacts (by default under project-root/specs), not
the installed skill or command working directory. Preserve referenced files and
their relative layout when archiving; never change hashes to hide missing files.
Set final paths before computing record/mapping fingerprints. A relocation is
byte-preserving only when the referenced dependency tree keeps the same relative
layout; packaging specs alone need not include application source/assets. Legacy
absolute references are readable but not automatically portable. Changing a judged
record's paths requires a new reviewed bundle, not silent hash replacement.

`uir.py check-map evidence.json` checks the design/code mapping before UI edits,
with empty captures, observations and sweeps allowed. `uir.py verify evidence.json`
adds implementation freshness, observations, comparison and sweeps. `uir.py status`
uses exactly the same acceptance result when a bundle exists. `check-spec` only
checks Markdown; success is neither mapping readiness nor visual acceptance.

Exit codes: 0 requested check passed; 1 incomplete/migration needed; 2 malformed
input. Version 2 is retained as `legacy_diagnostic`, always complete=false and
migration_required=true. Preserve it; collect missing facts, do not backfill
fictional evidence. Unsupported versions are invalid.

## Top-level fields

| Field | Contract |
|---|---|
| version | 3 |
| specification | hashed design-spec.md; same R-* IDs, state, element, property and expected values |
| platform | technical implementation environment, e.g. framework/runtime |
| states | unique state names actually defined by scope/design/component specification |
| design_languages | regional language findings described below |
| design_inventory | independently visible/styled design items, including declared compound children |
| design_review | reviewer, inventory_complete:boolean, details of page/control omission review |
| elements | design-to-code mappings and type-property coverage |
| requirements | independent expected values, comparisons and applicable data conditions |
| implementation | status pending/complete and relevant dependency file references |
| captures, observations, sweeps | may be empty in a mapping draft |
| adaptations | optional authorized per-requirement expectation changes |

The validator checks what is declared; inventory_complete is a reviewer assertion,
not automated image recognition. The model must compare inventory with the design.
A wholly omitted design element can only be discovered by design review, not JSON.

## Design provenance and language

A source reference is either:

- `{kind:"node", document:"design document ID/URL", locator:"node/component/variable ID"}`
- `{kind:"screenshot", artifact:{path,sha256}, locator:"crop(x,y,width,height)"}`

Crop coordinates are nonnegative integers; width and height are positive, in
image pixels. Record scale/normalization if measurements use other units. A node
reference names a retrievable authority; offline integrity of that remote source
is not established by its name. Save retrieved baselines/metadata when available.

A design-language finding has `id, status, name, reason, evidence`. Status is
known/inferred/unknown; name may be null when unknown. Evidence is a nonempty list
of `{source:<source reference>, detail:"observed origin/properties/visual facts"}`.
An unknown name is valid if observable requirements can be mapped. Do not infer
identity from an installed library, framework or file title alone.

A design_inventory item has `id, source, children:[inventory IDs], disposition`.
For build, add `element:<element ID>`; for excluded, add `reason, authority` and no
element. Use a tree/forest, no duplicate parents or cycles. A build child maps to
its own element under the mapped parent. Compound actions/separators/icons with
independent presentation cannot be covered by their parent's dimensions.

## Elements and implementation decisions

Each element has `id, parent:null|ID, type, design_language:<finding ID>,
design_refs:[inventory IDs], properties, mapping`. Optional `states` restricts
property coverage to this element's defined states; otherwise all bundle states
apply. Requirement states must agree; do not use * for an element absent in a
state unless asserting that absence explicitly.

`mapping` contains:

- `mode`: reuse / adjust / new / pending. Pending blocks mapping readiness.
  Adjust means implementation changes that preserve the design, not a waiver.
- `reference`: exact component/resource or proposed target; `system`: engineering
  component system, possibly custom. Neither is the design-language identity.
- `parameters`: explicit variant/size/resource/theme configuration ({} if none).
- `code_evidence`: nonempty inspected file references with `locator` and `detail`;
  record relevant API/version/import/theme facts. New targets cite inspected
  project constraints and neighboring implementation/resource rules.
- `rationale`: why actual capabilities satisfy requirements. Optional
  `alternatives:[{reference,reason}]` records decisive exclusion of real competitors.
- `style_dependencies:[{path,sha256}]`: related wrappers, themes, asset/style files
  (empty only when inspection finds none). Refresh facts after scoped edits.
- `render_chain:[{role,reference,effect}]`: trace configuration, wrappers/theme and
  final drawing surface. Record no wrapper explicitly when applicable.

Cross-system selection is allowed. Same-system identity alone is insufficient.
A host's properties may not describe SVG artwork or a native child drawing layer.
Core checks do not encode CSS selectors or native driver rules.

## Property coverage

Each type property uses either `{requirements:[IDs]}` or `{na_reason:"design-based
reason"}`, never both. N/A is not unavailable evidence. Requirement refs must
belong to the same element, cover its states, and have a compatible semantic
property. Each independently styled child also needs visibility/present=true.

| Type | Required coverage entries |
|---|---|
| container | bounds, layout, spacing, background, boundary, scrolling |
| control | variant, visible-bounds, interaction-bounds, fill, border, radius, layout, states |
| icon/image | resource, silhouette, bounds, color, stroke, whitespace |
| text | content, font, size, weight, line-height, tracking, wrap |

Canonical requirement properties for those entries:

| Coverage entry | Compatible properties |
|---|---|
| bounds | geometry/bounds, geometry/width, geometry/height, geometry/constraints |
| visible-bounds | geometry/visible-bounds, geometry/width, geometry/height, geometry/constraints |
| interaction-bounds | interaction/bounds, interaction/width, interaction/height |
| layout | geometry/layout, geometry/alignment, spacing/internal |
| spacing | spacing/gap, spacing/padding, spacing/margin |
| background | color/background |
| boundary | shape/boundary, shape/border, shape/border-width, color/border |
| scrolling | interaction/scrolling |
| variant | component/variant |
| fill | color/fill |
| border | shape/border, shape/border-width, color/border |
| radius | shape/corner-radius, shape/radius, shape/contour |
| states | interaction/states |
| resource | asset/resource, asset/variant |
| silhouette | shape/silhouette |
| color | color/foreground, color/tint |
| stroke | shape/stroke, shape/stroke-width |
| whitespace | spacing/whitespace |
| content | copy/content, copy/name, copy/label |
| font / size / weight | typography/font / typography/size / typography/weight respectively |
| line-height / tracking | typography/line-height / typography/tracking respectively |
| wrap | typography/wrap, typography/truncation |

Each applicable detail still needs a requirement: height does not imply width,
and border color does not imply border width. Coverage checks the semantic family,
not completeness of every visible attribute. Additional standalone properties
can be declared without discharging a core entry. Extend canonical semantics with
tests when truly needed; do not introduce author-defined aliases that let fill
claim geometry/height.

## Requirements

Each row has `id, element, state, property, expected, unit, source, design_ref,
applies_when, comparison`. source is the human authority text in the checklist;
design_ref is a same-element inventory ID. For numeric Markdown expectations
use value plus unit, e.g. 36px. Other expectations use their textual form.

`applies_when` is an explicit object of scalar facts; {} is unconditional.
Example: `{"meetingAvailable":true,"contactType":"person"}`. Facts compare by key,
value and type with captured data_conditions. Wrong/missing conditions leave the
row unverified, not absent-by-design or adapted. Missing current data is not a
reason to change business features. Dynamic text uses a constraint, not sample
names; dynamic width uses inspected layout constraints, not the sample action count.

Comparison modes:

- number: finite expected and nonnegative finite tolerance, exact unit match.
- equals: type-and-value equality.
- content: text minimum length only, with nonnegative integer min_length;
  wrapping/geometry require separate rows.
- visual: hashed baseline and render capture, design/runtime crops, explicit
  reviewer, detailed contour/region comparison and boolean match.

shape/silhouette, shape/contour and shape/appearance require visual mode. An asset
name does not establish shape. Identity requirements can use source evidence;
appearance requirements need rendered measurement or comparison.

## Captures and actual observations

Capture fields: `id, state, kind:source|measurement|render, specification_sha256, mapping_sha256,
artifact, dependencies, code_version, viewport, scale, theme, language,
data_conditions, method`. data_conditions is an object ({} is valid); viewport
and method record units, context and normalization. Hash all relevant dependencies,
including dirty and transitive source, wrappers, themes and assets.

Set mapping_sha256 to the value returned by check-map at capture time. It binds
machine-only conditions, source links, mapping parameters and approved adaptations;
changing these reopens old observations even if Markdown expectations are unchanged.

Non-source captures also have `build_id` and a hashed `build` manifest:
`{id, method, dependencies:[{path,sha256}]}`. The project capability supplies the
observed running-build association and dependency snapshot from that build, not
the current checkout copied after capture. Reuse existing build/provenance output
or record an inspected association; do not build new infrastructure. Missing
association means unverified. Verification rejects a mismatched build ID or
dependencies different from current implementation scope. It cannot independently
prove an agent's asserted running-build association truthful.

Implementation status=complete needs nonempty current dependency hashes including
declared style_dependencies. This is tracked separately from visual verification;
hashes alone do not prove correctness or engineering-test completion.

Observation fields: `id, requirement, state, capture, locator`.
For number/equals/content, locator keys a hashed measurement JSON object:

```json
{
  "call-fill": {
    "element": "Call",
    "property": "color/fill",
    "surface": "actual control artwork",
    "value": "#ffffff",
    "unit": "sRGB"
  }
}
```

The element/property must match the requirement. Surface describes what was
actually measured; the model/platform capability must choose the real drawing
surface. Declaring a surface is not proof that a host measurement reached it.

Visual observations use runtime locator=crop(...), design_locator=crop(...) and
`review:{reviewer,details,match:boolean}`. Describe compared contours/regions;
generic “looks good” is insufficient. Values come from artifacts, not observations'
authored expected/verdict fields. Duplicate observations cannot override one
another. Source cannot prove rendered geometry/color/shape.

Each state needs a sweep: `state,capture,baseline,reviewer,
regions:["page","controls"],findings:[{description,requirements:[IDs]}]`.
No findings is an explicit review. A linked discrepancy reopens restored/adapted
rows. Unmapped findings block acceptance; add their requirements first. For
data-conditioned controls compare only observable portions, while their missing
requirement observations remain unverified.

## Authorized visual adaptations

Optional top-level records have `id, requirement, property, states, reason,
authority, replacement, remaining_requirements`. Property must exactly match
the target; states must apply. Reference concrete approval or a binding platform
constraint accepted in task scope, not “existing component”. Preserved requirement
IDs must exist, cannot include self or other adapted rows, and must actually pass.

Replacement uses expected/unit (plus tolerance for number); visual replacement
uses a hashed approved baseline and locator crop. Content constraints cannot be
waived. Observation adaptation is the record's ID, not a free-form waiver.
Numeric/equality observations must match the approved replacement; visual ones
need adaptation_design_locator matching the approved crop and a detailed
adaptation_review. Missing observations never become adapted. Report adaptations
separately from exact restoration.

## Resource integration and limits

For newly imported icons/images, follow resource-workflow.md and attach
resource_records file references to the element. Existing resource audits remain
unchanged: provenance, integration, same-element visual and actual-load
requirements must pass. Successful download/build/import alone is insufficient.

Archive bundles/specs/captures per round. Reopen affected rows on related changes,
new findings or conflicting evidence. Never convert missing proof to a pass.
Mapping complete, implementation complete and visually verified are distinct.
The executable synthetic fixtures in tests/test_evidence_v3.py demonstrate the
contract, not actual platform rendering. See behavior-evaluation.md for separate
design/code reasoning evaluation; its run-specific inputs and outputs stay in
the maintenance task's specs directory, outside the skill package.
