---
name: smip-craft
description: How the SMIP (ThinkIQ) platform actually behaves - the lessons the GraphQL schema dump and the docs do not give you. Use BEFORE writing or laying out a display script (embedding, horizontal overflow, the standard header, previewScript URLs), before writing GraphQL against a tenant (aliased mutations, the asThing hop, DATETIME values, idPath scoping, createScript fields the IDE needs), whenever a script's IDE Edit Config dialog opens blank or throws on start_timestamp, and whenever a display script "loses" part of its layout or a query returns nothing for no visible reason. Project-agnostic; the same tenant behaviour holds everywhere.
---

# smip-craft

Behavioural knowledge about the SMIP platform, earned on live tenants and
written down so it is not rediscovered on contact. Nothing here is project
convention; every item is something the platform does whether you like it or
not. Each project's `CLAUDE.md` says what the model means; this skill says how
the platform will treat what you write.

This skill is the **knowing** half of working the platform; `smip-script-sync`
is the **acting** half (moving scripts between a project folder and a tenant,
with the DB-is-not-disk rule and its consent discipline). Same umbrella, kept
as two skills so reading about the platform never loads a tool that writes to
it.

Two references, read the one your task touches:

| You are about to... | Read |
|---|---|
| write or restyle a display script, add a header, embed an SVG or wide table, build a link to a script | [reference/display-scripts.md](reference/display-scripts.md) |
| write a GraphQL query or mutation, batch writes, read records under an account, filter by subtree, write a datetime | [reference/graphql-behaviour.md](reference/graphql-behaviour.md) |

## The six things people relearn most often

1. **A display script is a separate document inside an `<object>`**, with no
   wrapper pinning its width. Wide content widens the document and pushes
   right-aligned things off-screen. Clamp `#app` first, always.
2. **`std_inputs.script_name` has no `.php`.** The `previewScript` route wants
   the disk file name with it. Build `<relativeName>_<id>.php` from GraphQL.
3. **Aliased mutations are the whole write-performance story.** One document
   with fifty `a0: updateAttribute(...) a1: ...` costs one round-trip; a loop
   costs fifty at ~2.7 s each on a busy tenant.
4. **A DATETIME attribute written as `stringValue` stores silently empty.**
   Use `datetimeValue`.
5. **`Thing` is the only type exposing `objectsByPartOfId`.** To read the
   objects under an account you go `account.asThing.objectsByPartOfId`.
6. **A script made with `createScript` needs `initialInputs` and `document`
   set**, or the IDE's Edit Config dialog crashes on `start_timestamp` and
   the script cannot be saved from the UI. If `owner` is the API user, the
   script was created over GraphQL, so check these fields first. Values are in
   [graphql-behaviour.md](reference/graphql-behaviour.md#scripts).

## Adding to this skill

When a tenant surprises you and the fix was not in a project's code, the
lesson goes here, in the matching reference, with the date and tenant it was
observed on. Fix the template copy first (`Automation Template/.claude/skills/
smip-craft/`), then copy the folder into the project. Deploying scripts is a
different skill: `smip-script-sync`.
