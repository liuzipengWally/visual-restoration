---
name: visual-restoration
description: Map visual designs and inspected code to element-level specifications, design-language findings and component choices; drive local UI restoration and verify fidelity with measured evidence across platforms, projects and design systems. Use for design-to-code, visual drift correction and restoration audits.
---

# Visual Restoration

Turn design evidence into explicit implementation decisions, then compare actual
presentation with independently defined visual requirements. Read
`references/evidence-contract.md` before mapping, implementing or judging.

## Ownership

This skill owns visual analysis, design-to-code mapping, scoped UI implementation,
comparison and reporting. It does not own product decisions, design-system
migration, account/permission management, environment provisioning, orchestration
or engineering-wide test policy. An audit does not authorize edits. Ask when a
required choice exceeds scope or authority; otherwise discover facts and proceed.

Project/platform capabilities supply source, component documentation, resource
rules, build/run/capture mechanisms and units. Discover them by capability, not a
hardcoded skill name. They provide facts and execution, **not the answer to which
component best matches the design**. Do not require a complete adapter first.
Cache verified facts on demand using `references/evidence-ladder-template.md`;
recheck stale entries.

The validator checks declared relationships, values and evidence integrity. It
cannot interpret arbitrary pictures, discover every undeclared element, certify
candidate suitability, or prove human descriptions truthful. The model reviews
design enumeration and final page/control crops. A caller requiring mandatory
invocation must enforce that externally; this skill is not a scheduler.

## Artifacts and routing

Resolve three locations separately: **skill-root** (this installed package),
**project-root** (the target project), and **screen-root** (this task's artifacts).
The command's working directory is not an artifact root. By default screen-root is
`<project-root>/specs/<requirement>/ui-implement/<screen>/`; honor an explicit
caller-provided artifact location outside the skill. Without a project, use a
caller-approved workspace; never fall back to the installed package.

Keep `design-spec.md`, `evidence.json`, `restoration.md`, design/runtime evidence,
raw measurements and per-round outputs together under screen-root. Do not introduce
a second independent specification. Production assets used by the application
still go to the project's actual asset locations, with provenance in screen-root.

During ordinary restoration, treat skill-root as read-only: do not save task
inputs, screenshots, reports, evaluation cases or caches there. Temporary work
belongs in a task-scoped temporary directory; copy any evidence cited by the final
report into the task artifacts before that directory expires. Preserve referenced
relative paths and hashes when archiving; record unresolved external dependencies.
Reusable project capability facts may live in the optional project cache below;
task-specific findings and run outputs belong in specs, not that cache.

## Open-source and privacy boundary

This package is designed to be reusable across projects. Keep examples synthetic:
use reserved example domains, invented requirement IDs, generic component/token
names and generated node IDs. Never commit real design URLs, screenshots, source
paths, ticket IDs, customer or employee names, dynamic user copy, runtime dumps,
access tokens, signed URLs or build metadata from a target project.

Task evidence can contain sensitive material even when the skill itself does not.
Before sharing a screen-root or evaluation bundle, inspect images, text, metadata,
resource records and dependency manifests for personal, customer, project and
machine-identifying data. Prefer relative paths; remove `.git`, `.DS_Store`,
`__pycache__`, compiled bytecode and temporary captures from release archives.

| Situation | Action |
|---|---|
| New target or incomplete mapping | Map; draft evidence v3 before UI edits |
| Mapping ready, implementation requested | Implement scoped mapped changes |
| Implementation available, verification requested | Capture and compare |
| Prior report claims completion | Check evidence and freshness; prose is not acceptance |
| New finding or changed design/source/style/theme/data | Reopen affected requirements and dependencies |
| v2 or prose-only history | Preserve diagnostics; gather missing v3 evidence without inventing it |

Mapping-only and verification-only work are supported. Use
`references/design-spec-template.md` and `references/restoration-template.md`.
Archive the previous round's bundle, spec and captures before revising them;
append corrections to the report. Old reports remain historical.

## 1. Describe the design before selecting code

1. Establish scope, platform, copy/behavior authority and user corrections. A
   restore-this-screen request plus current implementation can establish scope:
   preserve business behavior and dynamic content, change presentation. Do not
   demand a separate ticket when context suffices.
2. Retrieve baselines and available component origins, instance properties,
   variables, resources and geometry. Figma metadata, screenshots, design context
   and variables are source-capability examples, not dependencies. Screenshot-only
   sources use hashed image regions: record measurement uncertainty, never invent
   nodes, hidden states, library identity or exact tokens.
3. Group evidenced states with `references/state-grouping-guide.md`. Triage with
   `references/triage-guide.md`: approved, draft-but-visible, explicitly excluded.
   Baselines show visible appearance; source metadata supplies available exact
   values. Record authority for user corrections, including mistakes in designs.
4. Enumerate page → regions → controls → independently styled children in the
   spec and evidence draft's design inventory. Expand compound main/disclosure
   actions, separators and icons with independent appearance, not every technical
   node. Review the whole design and control crops for omissions.
5. Write element/property requirements independently of implementation: value or
   constraint, source, state and data conditions. Fill/border/radius cannot borrow
   height requirements; resource identity cannot prove icon silhouette. Distinguish
   visible bounds from interaction bounds. Use semantic properties in the contract.

For scrolling content, specify the height of each section and element or its
content constraint; a whole frame's absolute height along the scrolling axis is
not a requirement. Dynamic action counts and text follow data: a sample group
width is not automatically fixed. Do not invent missing states or infer copy
from layer names. Keep draft/excluded items in Do Not Build, out of implementation.

## 2. Infer design language and map implementation

Record separately, per region/control when needed:

- **Design language**: the visual/interaction specification expressed by the design.
- **Component system**: engineering components, tokens and resources implementing it.
- **Technical platform**: framework/runtime, not visual identity.

Language findings are known, inferred or unknown, with design-side evidence and
reasons. Mixed systems are valid. Unknown identity does not block matching
observable requirements. Inspect actual target imports, dependency versions,
available public APIs, variants, assets, themes, wrappers and relevant styles.
An installed library or design-file title alone does not determine the choice.

1. Satisfy explicit user requirements, platform and project constraints.
2. Inspect available candidates with authoritative design associations first.
3. Compare actual structure, shape, resources, theme semantics and defined states
   against independent requirements. Normalize values/units for comparison; use
   semantic bindings and inspected theme behavior for token identity. Equal color
   values do not make tokens interchangeable.
4. Choose reuse, adjust existing presentation, new under project rules, or pending.
   Record exact API parameters, inspected code facts, rationale and decisive
   exclusion reasons for competing candidates. Do not manufacture alternatives
   when one explicit mapping suffices.
5. Trace configuration → wrappers/theme → final drawing surface. Record relevant
   style dependencies and effects. Platform capabilities may inspect CSS/SVG,
   native modifier order, themes or default controls. Host bounds/styles do not
   necessarily describe the artwork they contain.

Cross-system reuse can match; a same-system component can use the wrong variant.
Adjusting implementation to meet the same design is **not a visual adaptation**.
Only authorized changes to visual requirements belong in Platform Adaptation:
identify requirement/property, replacement expectation and preserved requirements.
Existing code is not authority to waive differences. Pending is not N/A.

For missing/mismatched resources read `references/resource-workflow.md`. Reuse
existing acquisition/integration audits; do not add generic converters or replace
artwork with a semantically similar icon and claim a match.

## 3. Check mapping, then implement

Resolve the placeholders below to absolute paths before execution; commands can
run from any working directory. Use the available Python 3 interpreter (`python3`
shown here). `-B` prevents Python bytecode caches in the installed package.
The executable CLI entry points emit stdout/stderr as UTF-8, including through
pipes; subprocess callers must decode them as UTF-8. Importing the helpers does
not change the host application's streams.

```bash
python3 -B "<skill-root>/scripts/uir.py" check-spec "<screen-root>/design-spec.md"
python3 -B "<skill-root>/scripts/uir.py" check-map "<screen-root>/evidence.json"
```

These checks print results; they do not create report directories. If saving their
output, the caller writes it to screen-root, never to skill-root or an implicit cwd.

check-spec is document-only. check-map uses v3 inventory, requirements and mapping
without runtime captures. Resolve uncovered applicable properties and pending
decisions before implementing affected UI. N/A needs a design-based reason, not
an inability to measure; the validator cannot judge that reason independently.

Read the spec, especially Do Not Build, before writing code. Reuse behavior;
modify scoped presentation/resources and maintain selected parameters and
wrapper/theme relationships. Mark implementation complete only after changes
exist and appropriate engineering checks ran. Record remaining checks without
equating build success to visual success.

## 4. Capture, compare, correct

Discover existing capabilities incrementally. Source (T0) proves identities;
actual static render (T1), runtime (T2) or platform capture (T3) proves only what
it can observe. Choose sufficient evidence per requirement, not a tier quota.
A token match never eliminates rendered-color verification. Unavailable capture
means specific unverified properties, not authority to add infrastructure.

Capture provenance includes design/spec revision, running build identity and
dependency fingerprints, viewport/units/scale, theme, language and data facts.
Keep raw output and normalization details. Current checkout is not proof of
current running build. Include transitive wrappers, assets and themes.
When data lacks a designed control, describe needed data; its appearance remains
unverified. Do not force business flags/actions to create a screenshot.

Each round:

1. Check design/source freshness and re-map affected requirements. Preserve
   expectations instead of fitting them to output.
2. Gather real measurements/screenshots through authorized capabilities. Read
   actuals from hashed outputs, never copy expectations into observations.
3. Compare applicable requirements in correct states/data. Review page and control
   crops for omissions. Add requirements for new findings and recheck mapping.
4. Run `python3 -B "<skill-root>/scripts/uir.py" verify "<screen-root>/evidence.json"`; append computed
   results to restoration.md. `status <evidence.json|restoration.md|directory>`
   uses the same acceptance, not a separate prose completion rule.
5. Fix scoped differences and repeat for affected rows/dependencies. New findings
   can increase counts; that alone is not lack of progress. If capabilities or
   authority block progress, report precise remaining items without claiming
   completion. External workflows own budgets and mandatory invocation.

## Delivery

Report **mapping complete**, **implementation complete**, and **visually verified**
separately, including differences, unverified conditions and approved adaptations.
verify/status exit 0 means v3 acceptance (adaptations counted separately);
1 means incomplete/migration needed; 2 means invalid input. check-map exit 0 is
mapping readiness only. Build, source identity and green prose are not render
evidence. Synthetic fixtures are not live platform/device validation.

## Maintenance

Only an explicit skill-maintenance task changes this package. Keep generic
instructions, templates, scripts and curated minimal regression tests here.
Run `python3 -B -m unittest discover -s tests -t tests` in skill-root; tests use
temporary fixtures and must not leave outputs in the package.

Before publishing a copy, run `python3 -B "<skill-root>/scripts/publication_check.py" "<skill-root>"`.
Treat failures as release blockers, then perform human review
of screenshots, archives, design metadata and dependency manifests as well.

For model behavior evaluation read `references/behavior-evaluation.md`. Its inputs,
page images, reviewer rubric, agent outputs and reports belong to the maintenance
task under `<project-root>/specs/<maintenance-task>/evaluations/<run-id>/`, not the
skill. Ordinary tasks must not append cases or promote artifacts into tests.
Promotion requires an explicit maintenance decision and a minimized, reusable
regression with demonstrated coverage value, not a copied page/task archive.
