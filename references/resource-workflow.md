# Missing resource acquisition and integration

Read when the design contains an icon, iconfont glyph, vector drawable, image or
variant absent from the project. Use the common record below; keep project tool
names and directories in the engineering adapter. This workflow includes actual
acquisition/installation; exporting from a proprietary design source still needs
that source's available export capability or a supplied original file.

## 1. Discover and resolve

Identify the specific design node/asset, visible variant, dimensions, color and
theme behavior. Search existing exports, icon packages, font mappings and asset
catalogs by semantics, then compare actual contours and variants. Record direct
reuse only when they match. Prefer reusing an exact existing library export over
duplicating the same file. A screenshot showing an icon is not its vector source.

Inspect neighboring assets and configuration to establish naming, target format,
registration, theme variants, raster scale conventions and build integration.
List the actual project rule path and a neighboring example. Do not invent a
new asset pipeline when the project already has one.

## 2. Obtain the original

Resolve skill-root from the installed package, project-root from the target
application, and screen-root from its task artifacts (by default
`<project-root>/specs/<requirement>/ui-implement/<screen>/`). Substitute absolute
paths below; cwd does not determine output ownership. The application asset target
is production code; records and preserved originals are task evidence under specs.

Use the design tool's export/asset API for the exact surviving node or use its
returned asset URL. Prefer the original SVG for vectors and the original image
fill for photos. For compositions, export the intended node with specified
format, transparency and scale. If the tool only returns screenshots, look for
an export operation or source attachment; do not trace a screenshot and label it
the original. Record pending when the original cannot be obtained.

Invoke the tool with the verified design identifier, using its actual schema.
For authenticated export, prefer the existing tool session and import its local
output. Do not put credentials into CLI flags or records. Never download imagery
merely to bypass a tool's image-display restrictions.

```sh
python3 -B "<skill-root>/scripts/resources.py" acquire \
  --source /path/to/exported/icon.svg \
  --target "<project-root>/assets/icon.svg" \
  --record "<screen-root>/resources/icon-default.json" \
  --design-source 'design-file/node-id' \
  --variant 'default/light/20' \
  --rule '<project-root>/asset-rule.md; example: assets/existing.svg'
```

`--source` also accepts a tool-provided HTTP(S) asset URL. Downloads have a 30s
timeout and 32 MiB limit; HTML/login pages and unsupported formats are rejected.
Signed URL query/fragment is omitted from provenance. Use a stable node ID for
`--design-source`, not a credential-bearing URL. Original bytes are preserved in
`originals/<sha256>.<format>` beside the record. Supplied glyph maps are also
preserved there as `<sha256>.glyph-map.json`, not left dependent on a temporary
export. Same-byte reruns of a newly acquired record are idempotent;
different existing files are never silently overwritten. Choose a new variant
path or explicitly review a replacement through the normal editing workflow.
The command can leave new files after an I/O failure; inspect/retry rather than
deleting broad directories. Format detection is not a full decoder/build check.

## 3. Convert without losing meaning

| Resource | Procedure |
|---|---|
| SVG / vector icon | Preserve original; use exact package export, project SVG loader/component generator, or registered converter. Keep viewBox, strokes, fill rules and internal whitespace. |
| VectorDrawable | `--convert svg-to-vector` supports origin-zero viewBox, matching aspect ratio and solid RGB path fills only. Reject transforms, groups, gradients, stroke, opacity and theme colors. Verify generated XML with the target build; fillType support depends on target Android configuration. |
| iconfont | Obtain the matching font version and authoritative glyph map; `--glyph-map glyphs.json` uses `{ "call": "U+E001" }`. Never guess codepoints from design names. Register font-family/platform font and mapping. Signature/map syntax checks do not establish that the font contains the glyph: inspect cmap with the project's font tooling and render the actual glyph. |
| PNG/JPEG/WebP/GIF/AVIF/PDF | Preserve the original bytes when the project supports the format. Otherwise use existing image tooling with explicit output size, scale, transparency, color and animation handling. Never silently flatten animation or rasterize a tintable vector. |
| Platform catalogs and generated components | Import the raw asset, then update asset catalogs, resource IDs, source exports or generated wrappers using the project's existing mechanism. Verify packaging and actual loading. |

The built-in converter takes SVG viewport units as output dp; use it only when
the project/designer's intended logical size matches. Other conversions are
performed with the existing project tool. Register its real output, preserving
the original and exact tool/version/arguments:

```sh
python3 -B "<skill-root>/scripts/resources.py" acquire \
  --source /path/to/original.svg --converted /path/to/converted.xml \
  --converter-description 'project-vector-tool version; exact arguments' \
  --target "<project-root>/res/drawable/icon.xml" \
  --record "<screen-root>/resources/icon-default.json" \
  --design-source 'design-file/node-id' --variant 'default/light/20' \
  --rule '<project-root>/resource-rule.md; example: res/drawable/existing.xml'
```

No arbitrary command from a design file or resource manifest is executed by the
helper. Component wrappers and catalogs are generated/edited separately, then
included as integration files. Unsupported formats remain pending; this tool
does not promise arbitrary format conversion.

## 4. Register and verify

The acquire command creates a resource record with original/output file hashes,
design source, variant, asset rule and conversion provenance. New artifact paths
are relative to the record's directory, using `/` separators. Resolve returned
references against that directory, never cwd. On different Windows drives a
relative reference is impossible: the target remains an explicit absolute external
dependency. Report that limitation or choose a same-drive artifact location;
do not claim such a record is independently portable. Historical absolute-path
records remain readable and are not rewritten by audit.

`origin` and `asset_rule` retain descriptive provenance; a historical source path
is not a live dependency. Audit reads the preserved original, installed output,
glyph map and integration references. Before hashing a record into evidence.json,
finish integration entries with record-relative paths and choose the final layout.
Archive/move the referenced tree together (including product assets and integration
files), not just the JSON or screen directory. Moving that tree without changing
relative relationships preserves record bytes and hashes. Missing external files
remain unverified; copying specs alone is not a complete source archive.

Do not normalize an already-judged record in place or reacquire over it to migrate
paths. Preserve that historical record; if a new layout requires changed paths,
create a new reviewed record/bundle and refresh affected fingerprints/evidence.

After actual engineering integration, add:

```json
{
  "integration": [{
    "path": "relative/path/to/import-or-catalog",
    "sha256": "hash of actual integration file",
    "reference": "literal registered name or import path"
  }],
  "visual_requirements": ["R-icon-contour"],
  "load_requirements": ["R-icon-loaded"]
}
```

Use a new reviewed record if the previous round was already judged; never rewrite
historical evidence to turn it green. Add a hashed reference to this record under
the matching evidence.json element's `resource_records`. New icon/image elements
must have records. Both requirement types belong to that same element: visual
requirements use `comparison.mode=visual`; load requirements assert
`property=visibility/resource-loaded`, `expected=true`, and require runtime or
render measurement (not source inspection). Test the actual font glyph or
resource instance, not merely an enclosing empty element's presence.

Run `resources.py audit record.json`, then `uir.py verify evidence.json`.
`audit` only means provenance/integration is ready for verification; it cannot
declare visual fidelity. Final acceptance requires loading AND silhouette review
in every required state. Build/packaging checks remain the adapter's job.

On export failure, unsupported conversion, stale files, missing registration,
missing glyphs or visual mismatch: retain the original, record the exact blocker,
and leave the resource pending/unverified/unrestored. Do not use a placeholder,
different icon or generated approximation as an exact restoration.
