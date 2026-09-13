---
name: smip-script-sync
description: Sync SMIP (ThinkIQ) platform scripts - display, browser and headless PHP - between a VibeCon-style project folder and the tenant over GraphQL. List, pull, bind, push (dry-run by default) and status. Knows that a GraphQL write is NOT a deploy because scripts execute from disk and need an IDE Save. Use when asked to push, pull, deploy, stage, compare, back up or sync SMIP scripts / display scripts / paste targets.
argument-hint: "[list|pull|bind|push|status] [--dir <folder>] [--apply]"
---

# smip-script-sync

Moves platform scripts between a local folder and an SMIP tenant. The bundled
`smip_script_sync.py` is self-contained (needs only `requests`) and reads the
project's `SMIP_IO/config.json`, so it works in any VibeCon-SMIP project
without importing that project's code.

Run it from the project root. The script sits next to this file, so use
whichever copy of the skill is loaded:

```bash
python .claude/skills/smip-script-sync/smip_script_sync.py <command> [options]   # project copy
python ~/.claude/skills/smip-script-sync/smip_script_sync.py <command> [options] # user-level copy
```

On Windows `~` is `%USERPROFILE%`. Both copies are meant to stay identical;
when you change one, copy it over the other.

## The one fact that governs everything

**Writing a script over GraphQL updates the database row. It does not deploy.**
Scripts execute as files on disk inside the Joomla host, named
`{relativeName}_{id}.php`. The file is rewritten only when someone opens the
script in the platform IDE and presses **Save**. Until then the live page runs
the old code, and nothing visible over GraphQL tells you so.

Therefore:

- `push --apply` reports **"DB UPDATED - NOT YET LIVE"** and prints the IDE URL
  for each staged script. Never tell the user a script is deployed or live.
- `status` **infers** liveness from write ordering: a server `updatedTimestamp`
  later than the one recorded at staging means somebody saved after us. Say
  "live (inferred)", not "verified".
- The full reasoning, the evidence, and what the PHP side can do that GraphQL
  cannot are in [reference/platform-notes.md](reference/platform-notes.md).
  Read it before changing the tool or arguing with its output.

## Consent rule

**Never run `push --apply` as a follow-on to editing a file.** Editing a local
paste target is ordinary work. Writing it to the tenant is a separate act that
needs its own explicit request from the user, every time. These scripts are
live UI in a shared tenant, `updateScript` replaces the body outright, and the
backups this tool writes are the only undo. If a file is ahead of the tenant,
say so and stop.

`list`, `pull`, `bind` (dry run), `push` (dry run) and `status` are read-only
against the tenant and fine to run whenever they help.

## Commands

| Command | What it does | Writes to |
|---|---|---|
| `list` | Inventory: id, host (library/type/object), scriptType, outputType, updated, name. Filter with `--library/--type/--object/--name/--id`, or `--json`. | nothing |
| `pull --dir D <scope>` | Writes selected deployed scripts into D as `<displayName>.<ext>` plus a `<file>.smip.json` sidecar. Never overwrites a differing local file without `--force` (and backs it up first). Scope is required: `--library "My Lib"`, `--name "eMaint Record"`, `--type`, `--object`, `--id`, or `--all`. | local folder |
| `bind --dir D [--apply]` | Matches local files that have no sidecar to deployed scripts by content similarity, shows the match and confidence, writes sidecars with `--apply`. Refuses below `--min-similarity` (0.60). | local sidecars |
| `push --dir D [--apply]` | Unified diff of every local file against its deployed script. `--apply` backs up the deployed body to `<dir>/.smip_sync/backups/` and writes the local body to the tenant DB, then prints the IDE URLs. | **tenant DB** |
| `status --dir D` | For each script staged by this tool: "NEEDS IDE SAVE" or "live (inferred)". | nothing |

`--dir` defaults to `___SMIP_SAAS_SIDE___/SMIP Display Scripts`, the VibeCon
paste-target folder. Pass it explicitly for `SMIP Browser Scripts` or any other
folder. State and backups live in `<dir>/.smip_sync/` unless `--state-dir` says
otherwise. Backups are worth committing; they are the only history.

### File extensions on pull

PHP with output DISPLAY or BROWSER becomes `.html` (VibeCon convention, the
editor gets HTML highlighting for the Vue template). PHP HEADLESS/CLASS becomes
`.php`, PYTHON `.py`, SQL `.sql`.

### Matching

A sidecar `<file>.smip.json` holding the script id is authoritative. Without
one, the tool falls back to content similarity and says so. Local names and
deployed names rarely correspond (`user management.html` is deployed as
"Manage External Users"), so run `bind --apply` once per project to make
matching deterministic and rename-proof.

## Recipes

**Adopt an existing project's paste targets**

```bash
python .../smip_script_sync.py list                            # whole tenant; scripts hang on libraries, types AND objects
python .../smip_script_sync.py bind --dir "___SMIP_SAAS_SIDE___/SMIP Display Scripts"
python .../smip_script_sync.py bind --dir "___SMIP_SAAS_SIDE___/SMIP Display Scripts" --apply
```

Check every match line before `--apply`. A wrong bind followed by a push
overwrites the wrong script. Note that display scripts usually hang on a
**type** (the record type they render), not on the library, so `--library`
will not find them; use `--type`, `--name` or no filter.

**Deploy a change** (only when the user asks for the push)

```bash
python .../smip_script_sync.py push --dir "..."                # diff, dry run
python .../smip_script_sync.py push --dir "..." --apply        # stage to DB, back up first
# user opens each printed IDE URL and presses Save
python .../smip_script_sync.py status --dir "..."              # confirm nothing still NEEDS IDE SAVE
```

Optional `--stamp` inserts a one-line `// staged by smip-script-sync <utc>`
marker after `<?php` so the staged version is self-describing in the IDE. The
comparison ignores that line, so stamped scripts still read as up to date.

**Round-trip an edit someone made in the IDE**

```bash
python .../smip_script_sync.py push --dir "..."                # the diff shows the IDE change as "-" lines
python .../smip_script_sync.py pull --dir "..." --name "eMaint Record" --show-diff
python .../smip_script_sync.py pull --dir "..." --name "eMaint Record" --force   # local is backed up first
```

**Bootstrap a new project from a tenant**

```bash
mkdir -p "___SMIP_SAAS_SIDE___/SMIP Display Scripts"
python .../smip_script_sync.py pull --dir "___SMIP_SAAS_SIDE___/SMIP Display Scripts" --library "My Library"
```

## Configuration

Resolution order: `--config PATH`, `$SMIP_CONFIG`, `./SMIP_IO/config.json`
(also up to three parent folders), `./config.json`. The file is the VibeCon
shape, a `SMIP` object with `graphQlEndpoint`, `clientId`, `clientSecret`,
`role`, `userName`. Env overrides: `SMIP_GRAPHQL_ENDPOINT`, `SMIP_CLIENT_ID`,
`SMIP_CLIENT_SECRET`, `SMIP_ROLE`, `SMIP_USER_NAME`, or `SMIP_BEARER` to reuse
a token. Never print or copy these values.

## Roadmap: the platform half

Manifesting DB to disk and verifying it is impossible over GraphQL but trivial
from PHP running on the platform (`file_put_contents` to
`$script->scripts_folder . $script->script_file_name`, then md5 of the file
against md5 of the row). The ThinkIQ-Labs Library-Vault does exactly this. When
a project is ready to put PHP on the platform, the plan is a small headless
library script with `Manifest` and `Verify` functions, shipped as an importable
library export JSON. Details in the reference notes. Until then the IDE Save is
the deploy step, and this tool says so.
