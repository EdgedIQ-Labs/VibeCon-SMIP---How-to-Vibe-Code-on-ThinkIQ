# CLAUDE.md

Operating guide for an agent working in this repo. It holds the cross-cutting
facts that aren't obvious from any single file: the realm map, the run
commands, and the rules that keep writes to the live system-of-record safe.
For *what the project is* and why, read [`README.md`](README.md) first — this
file does not repeat it.

## What this repo is

**VibeCon-SMIP** — a localhost-first automation template for the CESMII SMIP
(ThinkIQ). Modern Python for automation; SMIP-side scripts only for things
that must live in SMIP's runtime. The template's spine is *one tool registry,
four surfaces* (REST / MCP / chat / docs page). Sibling to DevCon-SMIP: DevCon
teaches you to code on ThinkIQ, VibeCon teaches you to vibe-code on it.

## Read next (authoritative docs)

| Doc | When to read |
|---|---|
| [`README.md`](README.md) | Orientation: the three script buckets, the playground, the template's opinion. |
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Clone → working chat agent calling tools. The five-beat smoke test. |
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | How to grow it well: tools-before-pages, conventions, the JS SDK parity contract. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | What's where and why: registry mechanics, script flavors, the shim. |
| [`___SMIP_SAAS_SIDE___/SMIP JS SDK/README.md`](___SMIP_SAAS_SIDE___/SMIP%20JS%20SDK/README.md) | The generic SMIP-side JS SDK that mirrors the Python tools. |

## Agent realms (who owns what)

Work is routed to realm-specific subagents; resume the same agent for
follow-ups. Each owns its folders and stays out of the others'.

| Agent | Model | Owns |
|---|---|---|
| `smip-methods-and-tools` | opus | The keystone: `SMIP_IO/` (the `SMIPMethods` SDK), `SMIP_MCP/` (the `TOOL_REGISTRY`), `SMIP_API/` (the Flask fan-out). Every other realm consumes this. |
| `script-writer` | sonnet | `SCRIPTS/` — numbered headless Python automation against the SoR. |
| `display-and-browser-scripts` | sonnet | The SMIP-side twins: `DISPLAY_SCRIPTS/`, `BROWSER_SCRIPTS/`, the `PLAYGROUND/` workbench, and their paste targets under `___SMIP_SAAS_SIDE___/`. |
| `js-sdk-compiler` | sonnet | The SMIP-side JS SDK mirroring Python tools: `SMIP JS SDK/` + `JS SDK Template/`. |

**`smip_methods.py` has a single writer.** `smip-methods-and-tools` is the sole
owner of `SMIP_IO/smip_methods.py` — both regions, above and below the
`Internal / automation-only` banner. Other agents (notably `script-writer`)
**request** new methods from it rather than editing the file; they import and
call once the method exists.

**JS↔Python parity is a contract.** When a tool is added or changed in the
Python registry and should round-trip to SMIP, `js-sdk-compiler` mirrors it
(same name, params, return shape) into the matching JS folder.

## Run commands (verified against code)

Flask processes — pick the one whose realm you're in:

```
python PLAYGROUND/playground.py        # twin workbench  → http://localhost:5105/playground
python SMIP_API/smip_flask_api.py      # registry/docs/chat → http://localhost:5000  (docs at /, chat at /chat)
python SMIP_MCP/smip_mcp_server.py     # MCP server (stdio)
```

**Credentials & secrets (never commit):**
- SMIP transport (local): `SMIP_IO/config.json` (copy from `config.example.json`; gitignored).
- App config (local): `.env` at repo root (copy from `.env.example`) — `AZURE_OPENAI_*` (chat), `PLAYGROUND_ROOT_FQN`.

## Operating rules (the cross-cutting ones)

- **One registry, four surfaces.** A single `TOOL_REGISTRY` entry in
  `SMIP_MCP/smip_tools.py` fans out automatically to `/api/tool/<name>`, the
  MCP tool, the `/api/chat` tool spec, and the docs page. **Never wire a
  surface by hand that the registry should derive.** Adding a tool = three
  edits: the `SMIPMethods` method, the registry entry, and (if LLM-exposed) the
  ~3-line typed MCP wrapper. Set `llm_exposed: False` for mutations/bulk
  fetches so they reach REST but stay out of the chat agent's reach.

- **The description is the product.** It's what the chat agent reads to *pick* a
  tool and what the docs page renders. Say what it returns and when to use it.

- **Three script flavors.** `SCRIPTS/` = headless local automation (no SMIP-side
  twin). `DISPLAY_SCRIPTS/` = node-bound Vue twins (SMIP passes `node_id`).
  `BROWSER_SCRIPTS/` = standalone page twins. The twins run locally against the
  `_shims/tiq_runtime.js` runtime so the body is paste-identical to the
  SMIP-side script. The shim is a SMIP/Joomla compat layer.

- **Writes to the SoR are destructive and not atomic.** `create_object`,
  `update_attribute(s)`, `delete_object(s)` write immediately — no undo, and
  claim-check-then-write has a race. Scripts must: offer `--dry-run` first,
  resolve all target ids up front and fail fast, scope every write under a known
  root, and be idempotent/re-runnable. Deleting a type **cascades** to its
  instances — hard delete, no prompt, no soft-delete; a peer tenant is the only
  recovery surface. Resolve by name, act by id (mutations take digit-string ids).

- **Base ThinkIQ libraries are `locked: true`.** You can't attach a script or
  attribute to a base type. Derive a sub-type in your own unlocked library,
  attach there, and re-type the instances. (README has the three-beat detail.)
