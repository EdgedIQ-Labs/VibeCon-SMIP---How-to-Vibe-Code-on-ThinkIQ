# SMIP platform notes: scripts, the database, and the disk

What an agent needs to know about how SMIP (ThinkIQ) stores and runs scripts,
gathered from live experiments on `thermalworks.thinkiq.net` (2026-09-01 and
2026-09-13) and from reading the ThinkIQ-Labs Library-Vault export (2024-03,
schema 4.8.11). Tenant-agnostic unless marked.

## Two copies of every script

| Copy | Where | Written by | Read by |
|---|---|---|---|
| Row | Postgres `model.scripts` | GraphQL `createScript` / `updateScript`, IDE Save, PHP `Script->save()` | GraphQL, the IDE editor, PHP model classes |
| File | Joomla host, `.../scripts/{relativeName}_{id}.php` | IDE Save, PHP `file_put_contents` | **the runtime** (`invokeScript`, `previewScript`, display rendering, cron) |

The runtime executes the file. A row that is newer than its file is silently
ignored until something rewrites the file.

**Evidence.** On 2026-09-01 the display scripts `eMaint Record` (173644) and
`SNow Record` (178723) were both pushed via `updateScript` seconds apart. Only
173644 was then opened in the IDE and saved. Its page changed; the other kept
rendering the old code. The IDE tab showed the file as `emaint_record_173644.php`.

## Why a GraphQL push leaves an existing file stale

The Library-Vault's `libvault_php_api` carries the platform's own write logic:

```php
function saveToDisk(string $file, string $content, bool $force_write = false): void
{
    if (!file_exists($file) || $force_write) {
        file_put_contents($file, $content);
        chmod($file, 0755);
    }
}
```

The file is written when it is **missing** or when a write is **forced**. A
brand-new script therefore works on first run (the file gets created), while
an updated script keeps its old file. The IDE Save is the forced write.

## What GraphQL exposes, and does not

Live `Script` type (36 fields, identical to the schema dump):

```
id systemType typeName displayName description typeId partOfId fqn relativeName
createdTimestamp updatedTimestamp sourceCreatedTimestamp sourceUpdatedTimestamp
document editStatus idPath scriptType script outputType cronExpression
initialInputs useOutputsFromLastRun run maxAcceptableRunSecs execOnDerived owner
unlinkRelativeName importance accessGroupIds
onLibrary onType onObject asThing type partOf
```

- No filename, path, hash or disk timestamp. The filename is **derived**:
  `{relativeName}_{id}.php`.
- `sourceUpdatedTimestamp` is null on every script; `document` is an inert
  `{"template":false}`; `editStatus` stays 1. None of them move on IDE Save.
- The IDE Save bumps `updatedTimestamp`, the same field `updateScript` bumps.
  So the only GraphQL-side signal is write ordering: record the server's
  `updatedTimestamp` returned by your push; if the tenant later shows a newer
  one, someone wrote after you (almost always an IDE Save).
- Root query: `scripts(filter, condition, first, offset, orderBy)` and
  `script(id)`. Mutations: `createScript`, `updateScript`, `deleteScript`. No
  publish, compile, run or manifest mutation.
- `scripts { ... }` tenant-wide is the only query that finds scripts hanging on
  libraries, types **and** objects in one pass; `tiqTypes { scripts }` misses
  the instance-attached ones.

Enums: `scriptType` is PYTHON | PHP | SQL. `outputType` is HEADLESS | CLASS |
BROWSER | DISPLAY. A record script left HEADLESS never renders.

Mutation shape used by the tool (variables avoid escaping the body):

```graphql
mutation UpdateScript($input: UpdateScriptInput!) {
  updateScript(input: $input) { script { id displayName outputType scriptType updatedTimestamp } }
}
# variables: {"input": {"id": "173644", "patch": {"script": "<?php ..."}}}
```

IDE URL for a script: `https://<tenant>/applications/ide?node_ids=<id>&selected=<id>`.

## What the PHP side exposes

Inside a script running on the platform, `TiqUtilities\Model\Script` has the
fields GraphQL lacks:

| Member | Meaning |
|---|---|
| `->script_file_name` | the on-disk name, e.g. `emaint_record_173644.php` |
| `->scripts_folder` | the folder the runtime loads from |
| `->script_ext` | `php` etc. |
| `Script::getIdFromFileName($name)` | inverse of the naming rule |
| `Script::deleteScriptFromDisk($path)` | remove the file |
| `Script::includeScript('lib.relname')` | include another script by fqn |
| `->save()` | write the row |
| `Script::getDb()->run($sql, $params)` | raw SQL against `model.scripts` |

VibeCon display scripts already use the first one:

```php
$php_api = new TiqUtilities\Model\Script('my_library.my_php_api');
$php_api_file_name = $php_api->script_file_name;   // handed to the browser
```

and the browser calls the PHP with `tiqJSHelper.invokeScriptAsync(fileName, fn, arg)`,
which POSTs to `/index.php?option=com_thinkiq&task=invokeScript` with form
fields `script_name`, `output_type=browser`, `function`, `argument` (JSON).
This route is authenticated by the **Joomla session cookie**, not the GraphQL
bearer token. Display scripts render via `task=previewScript&script_name=...`.

## The Library-Vault precedent

ThinkIQ-Labs "GitHub for SMIP Libraries" (six PHP script templates in one
library export) syncs scripts between a tenant and a GitHub repo, from inside
the platform. Its own roadmap panel names the same debt:

> atm when you pull, the script gets updated in the pg record, but not in the
> ..../scripts/my_file_23948738.php actual script file.

and its `UpsertScript` fixes it the only way possible, from PHP:

```php
$aScript->script = $aObject->text;
$aScript->save();                                                   // row
saveScript($aScript->script_file_name, $aScript->scripts_folder, true);  // file, forced
```

Its `PostprocessScript` also shows that staleness **is** detectable from the
platform: it stamps each script's `document` with `md5($script->script)` and
`filemtime($scripts_folder . $script_file_name)`. Compare md5 of the file
contents to md5 of the row and you have a real live-or-stale verdict.

Other conventions worth copying: one `.php` per script plus a
`<file>.___meta___.json` sidecar carrying run, document, output_type,
script_type, display_name, relative_name, initial_inputs, cron_expression,
max_acceptable_run_secs, use_outputs_from_last_run. Fqn, owner and the body are
deliberately left out of the sidecar. The vault library itself travels as an
importable library export JSON, which is how tooling PHP reaches a new tenant.

## The platform half (not built yet)

When a project is willing to put PHP on the platform, a headless library
script with two functions closes the loop:

- `Manifest(ids | libraryId)`: for each script, `saveScript(script_file_name,
  scripts_folder, true)`. Turns "push, then click Save N times" into
  "push, then one call".
- `Verify(ids | libraryId)`: return `{id, md5_row, md5_file, filemtime,
  updated_timestamp}` per script. Turns "live (inferred)" into "live (verified)".

Two ways to trigger it from a laptop: reuse a browser session cookie against
`task=invokeScript`, or give the script a `cron_expression` with `run = true`
so it self-heals every minute and the client workflow becomes push, wait,
verify. It must be bootstrapped once by IDE Save (its own file has to exist),
and it ships as a library export JSON like the vault and the VibeCon JS SDK.

## Things that bit us

- Content matching between local files and deployed scripts is necessary
  because names drift (`user management.html` is deployed as "Manage External
  Users"). A weak match must be refused, not guessed at.
- CRLF/LF and trailing whitespace make every file look dirty forever unless
  the comparison normalises them.
- An injected staging marker must be excluded from the comparison or the tool
  pushes the same file every run.
- `updateScript` replaces the body outright and the platform keeps no history.
  Back up the deployed body before every write.
- Base ThinkIQ libraries are `locked: true`; you cannot attach a script to a
  base type. Derive a sub-type in your own library.
