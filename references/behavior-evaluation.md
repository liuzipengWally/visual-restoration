# Behavior evaluation during skill maintenance

Read only for an explicit evaluation or maintenance task. Ordinary UI restoration
does not run a benchmark or add cases to the skill. This document is reusable
methodology, not a growing collection of page examples or expected answers.

## Separate package, inputs and run outputs

Resolve skill-root and target project-root independently of cwd. Keep durable
evaluation material in
`<project-root>/specs/<maintenance-task>/evaluations/<run-id>/` (or an explicit
caller-approved artifact root outside the skill). Record inputs, reviewer rubric,
agent outputs, command results and limitations there. Do not overwrite a prior
run. A temporary isolated workspace is optional; archive cited outputs and their
dependencies before delivery, preserving relative paths, bytes and fingerprints.
If a reference cannot be preserved, report the gap rather than inventing evidence.

Isolation concerns what the evaluated agent can read, not whether results belong
outside the project. Give that agent only the skill, relevant raw design/code
inputs and authorized capabilities. Keep reviewer criteria, previous conclusions
and expected component choices out of its context. Distinguish actual source,
reconstructed excerpts and synthetic inputs; mark device/render limits explicitly.

## Choose cases for the changed behavior

Use the smallest relevant selection, not a fixed page suite or mandatory platform
matrix. Useful dimensions include mixed component systems, same-system variant or
theme mismatches, wrappers changing the final drawing, independent compound
children, screenshot-only provenance, visual versus interaction bounds, units,
data-dependent controls and unavailable capture capabilities. Inputs must present
evidence and constraints, not the expected implementation answer.

A separate reviewer checks the chosen implementation and its rationale against
the design and inspected code: independent property/child coverage, actual drawing
dependencies, preserved behavior, unresolved conditions and evidence claims. A
correct component name alone is insufficient. Record overlooked details and
unsupported claims, including when a mapping correctly remains incomplete.

Run the applicable check-map/verify/status commands on produced bundles using
absolute skill and artifact paths as in SKILL.md. Save actual stdout/exit codes
under the run directory. Distinguish structural checks, model decision evidence,
implementation checks and actual rendered/device verification. Synthetic cases
and a few qualitative runs do not establish live UI parity or a reliability rate.

## Promote regressions deliberately

Skill tests contain only curated minimal fixtures that exercise a concrete
reusable invariant and have a maintained test consumer. Prefer generating
synthetic files in a temporary directory. Promotion from a task requires an
explicit maintenance decision: identify the failure, minimize input, remove
project identities and unrelated/private content, and show added coverage.
An entire page screenshot, task transcript or one-off report is not a regression
merely because it is stored under a directory named inputs or evals.

The skill owns these instructions and its helpers' output contracts. It does not
own global retention, archive scheduling or enforcement over arbitrary external
tools; callers supply such policies when required. Report observed output-path
violations instead of promising that prose rules can prevent every external write.
