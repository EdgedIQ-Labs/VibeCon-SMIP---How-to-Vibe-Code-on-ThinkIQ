# SMIP JS SDK — generic, tenant-agnostic apiDemoMethods helpers + descriptors

A library of methods that abstract directly against the SMIP — generic type and instance lookups and mutations for creating and editing instances. Tenant-specific vocabularies and descriptors belong in a separate tenant SDK; the generic SMIP plumbing lives here.

The library carries the bits of the descriptor-driven SDK pattern that don't depend on what's in the tenant. Two generic mutations wrap PostGraphile's `updateAttribute` / `updateObject`, with `_buildPatchLiteral` translating a JS patch object into a GraphQL `patch: {…}` literal with proper undefined / null / scalar semantics. Three generic queries — `getTypes` (lists tiqTypes with optional toggles for typeToAttributeTypes, objectsByTypeId, subTypes, subTypeOf, and childEquipment), `getObject` (single-object fetch with optional attributes / partOf / childObjects / type subselections), and `getEnumTypes` (lists enumerationTypes and zips the four parallel SMIP arrays into friendly `{name, value, color, description}` objects) — cover the common read paths. Both write and read sides cover all ten `ScalarTypeEnum` attribute datatypes (see the table below).

## Files

- `00 Guzzle Client.php` — generic Guzzle PHP client. API-key wiring kept as commented-out reminders for when you re-target it at an authenticated REST API. Endpoint defaults to `https://example.com/api/v1/` — edit the two private fields when consuming.
- `01 API Template.php` — generic PHP dispatch skeleton with no cases (SMIP JS SDK is JS-only; PHP cases are the tenant's to fill in). Tenant-specific libraries that want their own PHP-side methods can either fork this template or `includeScript` it and add `case "<MethodName>":` blocks.
- `02 API Tools.html` — the SDK proper. Defines (or extends) `apiDemoMethods` with `_buildPatchLiteral` + the two mutations + the three queries (`getTypes`, `getObject`, `getEnumTypes`) via the additive merge pattern below. Adds 5 descriptors to `apiDemoTools` (one per non-helper method) so the doc page renders an interactive form for each. The descriptors are explicitly developer-facing — the mutation forms can write to the SoR if exercised carelessly.
- `03 API Documentation.html` — generic Vue page that renders any descriptor catalog. Reused by tenant-specific SDKs that want a doc page; on its own it shows the five SMIP JS SDK tools.
- `smip_js_sdk_library_export.json` — importable SMIP library named `smip_js_sdk` containing the four scripts above. Tenant-agnostic — re-export from any SMIP and overwrite this file when the library evolves, or run `makeExportJson.py` (next entry) to rebuild it from the on-disk script bodies without a SMIP round-trip.
- `makeExportJson.py` — local rebuilder for `smip_js_sdk_library_export.json`. Run with `python3 makeExportJson.py` from this folder to refresh the JSON from the four script files when you've edited them on disk and want the export to track. Output is byte-deterministic across all three project copies when their sources are in sync. Use this for git-friendly workflows; the SMIP IDE re-export is still authoritative when SMIP metadata (file_version, schema_version) drifts.

## Additive merge pattern

Both `02 API Tools.html` (this library) and any tenant-specific equivalents use the same guard at the top:

```js
var apiDemoTools   = (typeof apiDemoTools   !== 'undefined') ? apiDemoTools   : [];
var apiDemoMethods = (typeof apiDemoMethods !== 'undefined') ? apiDemoMethods : {};
apiDemoTools.push( /* this library's descriptors */ );
Object.assign(apiDemoMethods, { /* this library's methods */ });
```

Whichever library loads first establishes the global; later loads merge their contributions in. Same-named fields are last-one-wins. Order of `includeScript` calls in a consumer script doesn't matter.

## What ships in `apiDemoTools` (descriptors visible on the doc page)

- **`UpdateAttributeViaJs`** — Mutation. `attributeId` (digits) + `patch` (JSON). DESTRUCTIVE.
- **`UpdateObjectViaJs`** — Mutation. `id` (digits) + `patch` (JSON, e.g. `{"importance": -260420}`). DESTRUCTIVE.
- **`GetTypesViaJs`** — Query. `typeNameSearch` (optional substring) + 6 toggles for what to include alongside each type: typeToAttributeTypes, objectsByTypeId (+ instanceNameSearch + per-instance attributes), subTypes, subTypeOf, childEquipment.
- **`GetObjectViaJs`** — Query. `nodeId` (digits) + 5 toggles for what to include alongside the object: attributes (default ON), partOf, childObjects, childAttributes (folded into childObjects), type.
- **`GetEnumTypesViaJs`** — Query. `displayNameSearch` (optional substring) + `includeValues` toggle (default ON) that zips the four parallel SMIP arrays (`enumerationNames` / `defaultEnumerationValues` / `enumerationColorCodes` / `enumerationDescriptions`) into a friendlier `enumerationTypeObjects` array of `{name, value, color, description}` objects on each row.

## What ships in `apiDemoMethods` (callable from any consumer script)

- `_buildPatchLiteral(patch)` — internal helper. Translates `{ floatValue: 12.5, datetimeValue: null }` into the GraphQL literal `{ floatValue: 12.5, datetimeValue: null }` with proper `undefined`-skip / `null`-emit / scalar-encoding semantics.
- `updateAttribute({ attributeId, patch })` — wraps `mutation updateAttribute(input: { id, patch })`. The patch object accepts one value field per ScalarTypeEnum datatype (full table below).
- `updateObject({ id, patch })` — wraps `mutation updateObject(input: { id, patch })`.
- `getTypes(args)` — wraps `query tiqTypes(filter: { displayName: { includesInsensitive: ... } }) { ... }` with optional related-data subselections (typeToAttributeTypes, objectsByTypeId + per-instance attributes, subTypes, subTypeOf, childEquipment). Each toggle adds a fragment to the query body; defaults all OFF for a lean response. When per-instance attributes are turned on, every value variant is returned (see datatype table below) plus `dataType`.
- `getObject(args)` — wraps `query object(id: ...)` with optional related-data subselections (attributes default ON, plus partOf, childObjects, childAttributes folded inside childObjects, type). When attributes are on, every value variant is returned plus `dataType` so the caller can route on `attribute.dataType` to pick the matching value field without a second round-trip.
- `getEnumTypes(args)` — wraps `query enumerationTypes(filter: ...)` with the four parallel arrays the SMIP stores per enumeration (`enumerationNames`, `defaultEnumerationValues`, `enumerationColorCodes`, `enumerationDescriptions`). When `includeValues` is on (default), each row is augmented with an `enumerationTypeObjects` array of `{name, value, color, description}` objects assembled by zipping those four arrays positionally.

## Attribute datatype coverage (the canonical 10)

The SMIP exposes ten attribute scalar datatypes via the `ScalarTypeEnum` GraphQL enum. The SDK covers all ten on both write (one field per datatype on `AttributePatch`) and read (every variant returned by `getObject` / `getTypes`-with-instance-attributes, plus `dataType` so callers can route).

| `dataType` (ScalarTypeEnum) | Patch / read field   | GraphQL type (read)              | Notes                                                               |
| --------------------------- | -------------------- | -------------------------------- | ------------------------------------------------------------------- |
| `BOOL`                      | `boolValue`          | `Boolean`                        |                                                                     |
| `INT`                       | `intValue`           | `BigInt`                         | string in JSON; string-encode large ints on write                   |
| `FLOAT`                     | `floatValue`         | `Float`                          |                                                                     |
| `STRING`                    | `stringValue`        | `String`                         |                                                                     |
| `DATETIME`                  | `datetimeValue`      | `Datetime`                       | ISO-8601 string, e.g. `"2026-04-20T10:00:00Z"`                      |
| `INTERVAL`                  | `intervalValue`      | `Interval` object                | `{ seconds, minutes, hours, days, months, years }` on read; `IntervalInput` on write |
| `OBJECT`                    | `objectValue`        | `JSON`                           | stringified JSON on write                                           |
| `ENUMERATION`               | `enumerationValue` (+ `enumerationName`) | `String` (+ `String`) | companion `enumerationTypeId` / `enumerationValues` / `enumerationName` are also on the patch |
| `GEOPOINT`                  | `geopointValue`      | `String`                         | schema types this as `String`                                       |
| `REFERENCE`                 | `referencedNodeId`   | `BigInt`                         | string in JSON; FK to another node                                  |

Plus the meta `dataType` field (a `ScalarTypeEnum` value) on `AttributePatch` itself, which lets a patch re-type an attribute. All ten value fields and the companion ENUMERATION fields clear to GraphQL null when set to `null` in the patch; setting a field to `undefined` (or omitting it) skips it. See the inline JSDoc on `apiDemoMethods.updateAttribute` and `apiDemoMethods.getObject` in `02 API Tools.html` for the per-field example block.

## Importing into your SMIP

1. Settings → Libraries → Import → choose `smip_js_sdk_library_export.json`.
2. **After every re-import**, open each of the four scripts in the SMIP IDE so the script body manifests from the database to disk. (SMIP defers writing the script body to disk until the script is opened in the IDE; consumers like Joomla / `includeScript` need the on-disk file.)
3. Open the API Documentation script to exercise the four tools interactively. Try `GetTypesViaJs` with `typeNameSearch='Storage Shelf'` and `includeSubTypes=true` to see the abstract type and its leaf subtypes — if that comes back populated, the SDK is wired correctly.
4. To consume from a tenant-specific library or display script:

   ```php
   TiqUtilities\Model\Script::includeScript('smip_js_sdk.api_tools');
   ```

   …after which `apiDemoMethods.updateAttribute(...)` / `updateObject` / `getTypes` / `getObject` / `getEnumTypes` are globally available.
