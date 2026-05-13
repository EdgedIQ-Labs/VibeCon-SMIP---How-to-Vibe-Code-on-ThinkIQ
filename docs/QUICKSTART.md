# Quickstart

Getting from `git clone` to a working chat agent calling tools against your
SMIP, in five steps. Each step adds exactly one new dependency and verifies it
before moving on — if a step fails, you know which layer to debug.

You'll need: Python 3.10+, an SMIP (ThinkIQ) tenant with API credentials, and
optionally an Azure OpenAI deployment (only needed for steps 4–5).

## Step 1 — Install dependencies

From the project root:

```
pip install -r requirements.txt
```

That's it for tooling — no Node, no build step.

## Step 2 — Connect to your SMIP

The transport layer needs credentials for your tenant. Copy the example config
and fill it in with your real values:

```
cp SMIP_IO/config.example.json SMIP_IO/config.json
```

Open `SMIP_IO/config.json` and replace each `REPLACE_WITH_*` placeholder:

```json
{
  "SMIP": {
    "graphQlEndpoint": "https://YOUR_INSTANCE.thinkiq.net/graphql",
    "clientId":        "...",
    "clientSecret":    "...",
    "role":            "...",
    "userName":        "..."
  }
}
```

`config.json` is gitignored, so your secrets stay local.

**Don't have these values yet?** You'll need to set up an *authenticator* in
your ThinkIQ tenant first — that's what produces the `clientId` /
`clientSecret` pair the SMIP uses for its JWT challenge/response auth flow.
See the CESMII guide:
[Accessing the SMIP GraphQL API remotely](https://github.com/cesmii/GraphQL-API/blob/main/Docs/jwt.md#accessing-the-smip-graphql-api-remotely).
Once you've created an authenticator, paste its values into `config.json`.

**Verify it.** Run the sample script:

```
python SCRIPTS/01_list_libraries.py
```

If you see something like:

```
3 library/-ies:
        12  My Library
        13  Another Library
        14  Project Library
```

…then transport, JWT auth, and GraphQL all work. If you see an error, fix it
here before moving on — every later step depends on this.

## Step 3 — Start the Flask app and verify the page workflow

The Flask app is what serves the docs page, the chat UIs, and the
`/api/tool/<name>` endpoint that pages call. Boot the sample page (which
imports the same Flask `app` and mounts itself on its own port):

```
python PLAYGROUND/playground.py
```

Then open <http://localhost:5101/list_libraries> in your browser.

You should see the same library rows you got from the script in step 2,
rendered as an HTML table. Same data, browser shape — that confirms the
PLAYGROUND launcher pattern works (sys.path, route decoration, same-origin
fetch through `/api/tool/get_libraries`, Vue 3 from CDN).

If the page loads but the table is empty or shows an error, open the
browser devtools console — the page logs the failed `fetch` clearly.

**Focus the tree.** The playground's left pane shows the instance tree
rooted at whatever `PLAYGROUND_ROOT_FQN` is set to in `.env`. The default
is `thinkiq_system` (the SoR root), which works but puts everything two or
three levels below where your project actually lives. Set it once per
project to save yourself the navigation:

```
PLAYGROUND_ROOT_FQN=thinkiq_system.your_org_node
```

`.env` isn't introduced until step 4 — if you want to do this now,
`cp .env.example .env` and set that one variable. The Azure OpenAI keys in
the same file can stay as placeholders until you're ready for step 4.

> **You can stop here and still have a useful VibeCon-SMIP.** Steps 1–3
> give you transport, a tool registry, the Flask app's docs page, the
> `/api/tool/<name>` dispatch endpoint, and the BROWSER_SCRIPTS/DISPLAY_SCRIPTS + SCRIPTS workflow.
> That's enough to build automation against your SMIP indefinitely.
> Steps 4 (the agentic chat agent) and the bonus MCP server section
> below are **optional layers** — useful, but not required for the
> template to do its job.

## Step 4 — Add the .env and verify the chat agent (optional)

The `/api/chat` endpoint runs an agentic loop backed by Azure OpenAI: the
LLM is given your TOOL_REGISTRY as OpenAI tool specs and decides when to call
them. To wire it up, drop a `.env` at the project root:

```
cp .env.example .env
```

Edit `.env` with your Azure OpenAI credentials (and set the playground
root if you haven't already):

```
AZURE_OPENAI_ENDPOINT=https://YOUR_RESOURCE.openai.azure.com/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2025-01-01-preview     # optional
AZURE_OPENAI_DEPLOYMENT=gpt-4o                   # optional

PLAYGROUND_ROOT_FQN=thinkiq_system.your_org_node  # focus the playground tree
```

Stop the page launcher from step 3 (Ctrl-C) and start the main API instead:

```
python SMIP_API/smip_flask_api.py
```

It runs on <http://localhost:5000>. Visit <http://localhost:5000/> first —
that's the auto-generated documentation page (sections rendered from
`TOOL_REGISTRY_PUBLIC`). You should see a section for `get_libraries` with its
description and a "Run" button you can press to invoke it directly.

Then visit <http://localhost:5000/chat> and ask:

> What libraries are in the SMIP?

The agent should call `get_libraries`, get the rows back, and answer in
natural language. If you watch the network panel, you'll see the
`/api/chat` request return both the answer and the tool-call history.

If you get a 500 from `/api/chat`, the most common cause is missing or
typo'd Azure OpenAI env vars — check the Flask terminal output, the
error message names which key is missing.

## Step 5 — Import a library, build your first tool — with one prompt

The smoke tests pass. Now make the template *yours* by adding one
project-specific tool — and notice that the whole point of this template
is that you don't add it by hand. You prompt for it.

**5a. Drop your library export.** Export a library from ThinkIQ as JSON
and drop it somewhere a whole-project-mode LLM will see. A reasonable
home is alongside the existing one:

```
___SMIP_SAAS_SIDE___/JS SDK Template/library_export.json     # already there for reference
```

…or under a new `data/` folder if you want to keep it cleanly separated.
The point is just that the file lives in the repo so the LLM picks it
up as context — that's what turns "build me a tool against GraphQL" from
a generic conversation into one grounded in *your* domain vocabulary.

**5b. One prompt, three edits.** Open the project in any whole-repo
LLM surface (Claude Desktop with the folder mounted, Cursor or Claude
Code in the project root, or your editor of choice with the model
holding every file in context). Paste this prompt verbatim — talk to
it the way you would another developer:

> i want to build a unit converter. let's add a tool that gets
> quantities and units with conversion offsets and factors from
> graphql:
>
> ```graphql
> query GetQuantitiesWithUnits {
>   quantities {
>     id displayName description quantitySymbol
>     measurementUnits {
>       id displayName description
>       conversionOffset conversionMultiplier symbol
>     }
>   }
> }
> ```

That's it. Notice what's *not* in the prompt: no "follow the conventions
in this repo," no "the smoke-test `get_libraries` tool is the shape to
copy," no "make all three edits in one pass." Those would be cheats —
hand-holding the LLM through the meta-pattern. With the whole repo in
context, the LLM reads the existing `get_libraries` tool, infers the
convention itself, and ports it to the new query. The prompt is the
intent ("I want to build a unit converter"); the edits are derived.

(*Why this query and not a simpler `quantities { id displayName }`?
Because this is the exact tool that powers the worked unit-converter
round-trip referenced in [WORKFLOW.md](WORKFLOW.md) step 7 — the
SMIP-side end state lives at
`___SMIP_SAAS_SIDE___/SMIP Browser Scripts/unit_converter.html`. The richer
query is what the converter consumes: nested units with offset and
multiplier so the math can happen client-side. Building it here
threads the same tool name end-to-end through the docs.*)

**5c. Verify the LLM landed the edits in the right three places.** Pop
the hood and confirm. The fan-out pattern is the whole reason the
template exists, and it's worth seeing it once with your own eyes:

1. **The method** in `SMIP_IO/smip_methods.py` — a
   `get_quantities_with_units` method on `SMIPMethods` that runs the
   GraphQL query and returns the `quantities` list (each row carrying
   its nested `measurementUnits`). Same shape as `get_libraries` right
   above it, just with a deeper query string.
2. **The registry entry** in `SMIP_MCP/smip_tools.py` — a new dict in
   `TOOL_REGISTRY` with `name`, `summary`, `description`, `parameters`,
   `ui`, and an `fn` lambda dispatching to
   `m.get_quantities_with_units()`. This entry is the single source of
   truth — `/api/tool/get_quantities_with_units`, the OpenAI tool spec
   for `/api/chat`, and the docs-page section all derive from it.
3. **The typed MCP wrapper** in `SMIP_MCP/smip_mcp_server.py` — three
   lines mirroring the `get_libraries` wrapper, so FastMCP can read
   the Python signature when generating the JSON schema for an MCP
   client (Claude Desktop, Cursor, etc.).

If any of those three is missing or off-shape, paste the diff back and
ask the LLM to fix it — the conventions in the repo are dense enough
that a corrective pass is fast.

**5d. Restart and test.** Restart the Flask app:

```
python SMIP_API/smip_flask_api.py
```

Visit <http://localhost:5000/> — a new `GetQuantitiesWithUnits` section
appears in the docs page automatically. Visit
<http://localhost:5000/chat> and ask:

> How many feet are in a meter?

The agent picks the new tool (because the description names the
conversion-factor fields), gets the unit list back, and computes the
answer. Try a few more — "convert 100°F to Celsius", "list every
quantity defined in the SMIP" — to see it pick up the same tool from
different angles. You're now operating the template the way it's meant
to be operated.

**The takeaway.** Read step 5c again. You'd have to do all of that by
hand the old way: write the method, write the registry entry, write the
MCP wrapper, hold the conventions in your head, get the GraphQL syntax
right, keep three files in sync. With a whole-repo LLM and a prompt
that includes the query, the prompt *is* the work. The starter kit's
job was to lay the conventions down so densely the LLM has no excuse to
drift; once that's true, building a tool collapses from "a session" to
"a prompt." Every project-specific tool you add from here on out
follows the same loop.

## Bonus: connect an MCP client (optional)

Pillar 2 of VibeCon-SMIP is the built-in MCP server — `SMIP_MCP/smip_mcp_server.py`.
It exposes the same `TOOL_REGISTRY` you've been building to any MCP client
(Claude Desktop, Cursor, custom agents) over stdio or SSE.

For a stdio connection (the default — used by Claude Desktop and most
local agents), the launch command is just:

```
python SMIP_MCP/smip_mcp_server.py
```

Wire that into your MCP client's config as the command for a new server.
Your client will then see every `@mcp.tool`-wrapped function in
`smip_mcp_server.py` (including the `get_quantities_with_units` you just
added) and can call them in conversations or workflows.

For SSE deployment (e.g. running on Azure Web App), see the comments at
the top of `smip_mcp_server.py`.

You can skip this entirely and the rest of the template still works —
this layer just adds a second LLM-facing surface alongside `/api/chat`.

## You're up

If steps 1–3 worked, you have a working VibeCon-SMIP. (Steps 4 and the
MCP bonus are nice-to-haves; step 5 is where the template starts paying
back the time you put into it.) From here:

- **[WORKFLOW.md](WORKFLOW.md)** — the recommended way to grow this.
  Strategic / best-practice content: bootstrapping with library exports,
  vibe-coding thin pages and scripts that call your tools (instead of raw
  GraphQL), validating via the chat agent, the round-trip back to SMIP-side
  scripts, the JS SDK parity convention.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — what's where and why. Reference
  for when you need to understand a piece of the wiring.
