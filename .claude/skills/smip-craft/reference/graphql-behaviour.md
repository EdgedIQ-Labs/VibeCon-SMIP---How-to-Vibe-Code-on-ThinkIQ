# GraphQL against SMIP: behaviour the schema dump does not tell you

The schema (`___SMIP_SAAS_SIDE___/SMIP Exports/smipGraphQlSchem.json` in a
VibeCon project) says what fields exist. These are the things it does not say,
each earned on a live tenant. Dates are when they were observed.

## Cost and batching

- A read costs roughly 0.3 to 0.5 s; a mutation roughly 2.7 s on a busy tenant
  (thermalworks, 2026-09). A per-record loop of four writes puts 1,700 records
  on a five-hour path.
- **Aliased mutations are the whole performance story.** One document holding
  `a0: updateAttribute(input:{...}) {clientMutationId} a1: ...` applies fifty
  writes in one round-trip. About 6,700 round-trips became about 200 that way.
- The only real ceiling is **payload size**, not alias count. Size the chunk
  to the payload: 100 aliases for a create with four scalar fields, 50 where
  each alias returns a dozen attribute nodes or carries long strings.
- Aliased mutations apply **in order and do not roll back**. A failing chunk
  leaves its predecessors written. Design every batch job to be idempotent and
  re-runnable against a fresh read, not transactional.
- There is **no batch delete**. `deleteObject` one id at a time, with progress.

## Writes

- **Value fields are not interchangeable.** An attribute declared DATETIME
  stores into `datetimeValue` and reads back `stringValue: null`. Writing it
  as `stringValue` leaves it **silently empty**. Same for enumerations:
  `enumerationValue` is the stored value defined on the enum type, **not an
  index**; an unknown value silently no-ops.
- `updateAttribute` with `stringValue: ""` clears the field; omitting the
  field leaves it alone. Empty string is a real value.
- `partOfId` is a **Thing to Thing** edge. Parenting an `Object` under an
  `Account` is legal and is how federation records hide from the instance
  tree. A wrong `partOfId` silently relocates an object; read the current one
  first if you might need to put it back.
- Deleting a **type** cascades to its instances. Hard delete, no prompt.
- Renaming a type attribute propagates to every instance, values included;
  renaming an account re-slugs its `relativeName`. Both safe after a backfill.
- An attribute whose slug collides with a built-in node column (`description`,
  `category`, ...) **shadows it** in the UI and can corrupt the real column on
  Save. Avoid those names.

## Reads

- **`Thing` is the only type exposing `objectsByPartOfId` and
  `accountsByPartOfId`.** `Object`, `Account`, `Equipment`, `Place`,
  `Organization` are projections over it. To read an account's children:
  `object(id){ accounts { asThing { objectsByPartOfId { ... } } } }`.
  `account.asThing.asObject` is null, the wrong face of the node, not a dead
  end.
- `Object.partOf` returns a `Thing`. Walking `record.partOf.partOf` gives a
  record's account, then its host, with `typeName` on each; `fqnList` is
  available on `Thing`, `fqn` on `Object`.
- **Scope a query by subtree with `filter: { idPath: { contains: "<id>" } }`**
  on `objectsByTypeId`. `idPath` comes back as a **list**; compare whole
  segments, never substrings, or `123` matches `1234`.
- `fqn` / `fqnList` are **lowercase slugs**, and the slugger spells punctuation
  out: a dot becomes `_period_`, `(` becomes `_lpar_`. Do not derive display
  names from them.
- `tiqTypes(condition: { displayName: "..." })` returns a **list**; assert
  exactly one before using its id, and assert the id against the one you wrote
  the script for, so a recreated type aborts loudly.
- Only the **root** nodes have `partOfId: null`. Filter
  `objects(filter: { partOfId: { isNull: true } })` to list them.
- Base ThinkIQ libraries are `locked: true`: you cannot attach a script or an
  attribute to a base type. Derive a subtype in your own library.
- **`relationshipTypeNodes.objectReferenceType` carries a leading space:**
  `" type"` / `" instance"` (seen 2026-10-12, in both GraphQL and the library
  export, on custom and built-in relationship types). Trim before comparing.
  `== "type"` silently matches nothing. A relationship type can target type
  nodes (`" type"`) as well as instances. That is native, not off-label.
  Verified by a live write 2026-10-12: `createRelationship` with
  `objectId` = the type's id works. Read it back via
  `relationships(condition:{subjectId}) { object { systemType asTiqType { relativeName } } }`.
  `systemType` is `"type"`, and `asObject` is null for a type target.

## Aliased read fan-out

Fetching attributes or account records for many objects is one aliased query
per chunk: `o0: object(id:"1"){...} o1: object(id:"2"){...}`. Chunk at 50 for
plain attributes and 25 where each alias fans out through
`accounts > asThing > objectsByPartOfId > attributes`.

## Scripts

- Scripts hang on a **library, a type, or an object**; display scripts usually
  hang on a type. `script(id){ relativeName partOfId scriptType outputType }`.
  `tiqType(id)` and `object(id)` on the parent id tell you which.
- `updateScript` writes the database row. The platform runs scripts from
  **disk**, `<relativeName>_<id>.php`, which only an IDE Save rewrites. See the
  `smip-script-sync` skill for the deploy discipline.
- **`createScript` does not set the defaults the UI sets**, and the IDE's
  Edit Config dialog breaks without them. Found 2026-10-12, and again on
  trimtabs on 2026-11-06 (script 239107 "Gross Gas Model").
  - A GraphQL-created script gets `document: null` and `initialInputs: null`.
    The 2026-10-12 one also got `run: true`, `useOutputsFromLastRun: true`
    and `maxAcceptableRunSecs: 0`.
  - The symptom is that the Edit Script / Edit Config dialog hangs on load or
    opens with blank Display Name, Internal Name and Language. The console
    shows `TypeError: Cannot read properties of null (reading
    'start_timestamp')` from `tiq.components.min.js`. That is the null
    `initialInputs`. A null `document` was not tested on its own, so set both.
  - The giveaway is `owner` set to the API user (e.g. `TT_Worker`) instead of
    a person. A GraphQL-made script has an API-user owner, and that owner
    alone does not block editing. When a script's dialog misbehaves and the
    owner is the API user, check these fields first.
  - Fix: pass the fields in `createScript`, or run `updateScript` right after
    creating, with
    `document: "{\"template\":false}"`,
    `initialInputs: "{\"start_timestamp\":\"1970-01-01T00:00:00.000+00:00\",\"interval_seconds\":\"60\"}"`,
    `run: false`, `maxAcceptableRunSecs: 50`, all copied from a UI-made display
    script. Send the JSON fields as JSON-encoded **strings**, the form the
    tenant stores and returns. `useOutputsFromLastRun` can be either value;
    UI-made display scripts on trimtabs carry both. Every UI-made display
    script has `run: false`. To repair an existing script, send the same
    patch, then open the dialog and Save.
- `createScript` returned HTTP 400 when the input carried `relativeName` and a
  `<?php` body. Omitting `relativeName` and creating with a plain placeholder
  body worked, and the platform slugged `relativeName` from the displayName.
  Which of the two caused the 400 is unknown. Push the real body afterwards
  with `smip-script-sync` (backup, stamp, read-back), after writing the
  sidecar by hand.
