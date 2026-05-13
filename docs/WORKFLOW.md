# Workflow

How to actually use this template well. The
[QUICKSTART](QUICKSTART.md) gets you to "rows on the screen"; this doc
covers what you should do *next*, and the discipline that keeps a
VibeCon-SMIP project from turning into spaghetti.

## Recommended setup — give your LLM the whole repo

The big shift isn't "use an LLM to write code." It's the move from
copy-pasting snippets into a chat to having the LLM **inhale the whole
project** and cross-reason across files. This template is built for that
mode.

The repo is dense in a deliberate way: one `TOOL_REGISTRY` entry fans out
to a REST endpoint, an MCP wrapper, an OpenAI tool spec, and a docs-page
section, plus a dual-mode import pattern in `SMIP_IO/`. A snippet-mode LLM
will guess at how it all fits. A whole-project-mode LLM, with every file in
context, will name the three places to edit and copy the existing registry
entry's shape into them.

So open the folder in something that can hold the whole tree in context —
Claude Desktop with the folder mounted as a project, Cursor or Claude Code
in the project root, or any LLM-aware editor where the model has read
access to every file.

Bonus: the built-in MCP server gives that same in-context LLM a live channel
into the SMIP itself — read the registry to know *what* tools exist, then
*call* them through MCP to see real data. Source code plus live introspection
in one chat session.

One downstream effect worth naming: **prompts get shorter**. When the LLM
has the whole repo as context, you don't spell out file paths, conventions,
or stack choices — those are all there to read. Talk in intent, not specs.
The prompts elsewhere in this doc reflect that. If you find yourself
writing a long technical prompt with file paths and substitution rules,
that's usually a sign you don't trust the context — fix the context (load
more of the repo), not the prompt.

## The recommended path

The temptation, especially with an LLM in the loop, is to skip straight to
"build a page that does X" and let the LLM stuff raw GraphQL queries into
the Vue component. That works and produces something on screen quickly.
It also produces spaghetti — every page reinvents the same queries, the
chat agent can't help you because nothing is registered as a tool, and the
round-trip back to SMIP-side scripts becomes a rewrite rather than a port.

The disciplined path is six steps:

### 1. Bootstrap with a library export

Export a library from ThinkIQ as JSON and drop it into the repo. A
reasonable home is alongside the existing reference one in
`___SMIP_SAAS_SIDE___/JS SDK Template/library_export.json`, or under a
project-specific `data/` folder.

The reason this matters: it gives any whole-project-mode LLM your actual
domain vocabulary. "What tools should I build?" goes from a generic
GraphQL conversation to "given that your library has *these* types and
*these* attributes, here are the four tools that cover 80% of your
foreseeable queries."

Skip this step and your tools end up generic; do it once and the LLM
becomes a competent collaborator on *your* domain, not GraphQL-in-the-
abstract.

### 2. Build tools first, not pages

Spend a session — sometimes just 30 minutes with a good LLM — building
3–6 tools in `SMIPMethods` + `TOOL_REGISTRY` *before* you build any page
or script that uses them. Use the QUICKSTART step-5 pattern:

1. Method on `SMIPMethods` (`SMIP_IO/smip_methods.py`)
2. Registry entry (`SMIP_MCP/smip_tools.py`)
3. Typed MCP wrapper (`SMIP_MCP/smip_mcp_server.py`, 3 lines)

Once a tool is in the registry it's reachable from the REST endpoint, the
agentic chat, the MCP server, and the docs page — automatically. That
fan-out is the whole point of doing this work first; you're not just
abstracting GraphQL, you're producing a single artifact that four
different surfaces consume.

Naming and shape conventions to follow:

- **Empty input means "all"** wherever it makes sense.
- **Server-side filters where possible** — push filtering down to the
  GraphQL layer rather than fetching everything and trimming client-side.
- **Flat rows over nested trees** — a row should be self-contained where
  practical so callers don't cross-reference a tree to get useful results.

### 3. Vibe-code thin pages and scripts

Now you can build pages and scripts freely, and the discipline is simple:
they should be **thin shells around tool calls**, not GraphQL clients.

A page should look like:

```js
const resp = await fetch('/api/tool/your_tool_name', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ args: { ... } }),
});
const json = await resp.json();
this.rows = json.data;
```

Not like:

```js
// avoid: raw GraphQL in the page
const resp = await fetch('/graphql', { ...giant query string... });
```

A script should look like:

```python
methods = SMIPMethods(SMIPClient())
rows = methods.your_tool_name(...)
```

Not like:

```python
# avoid: ad-hoc GraphQL in the script
client.query("query { ... }")
```

Twins live under `BROWSER_SCRIPTS/<page_name>/` (page-level) or `DISPLAY_SCRIPTS/<page_name>/` (node-bound) (folder per page, `.py`
launcher + `.html` Vue file). Scripts live directly under `SCRIPTS/` as
`<NN>_<task>.py`. Both are vibe-code-friendly: each runs in its own
process, the backend is unaffected, and a buggy page can't break sibling
pages. See [ARCHITECTURE](ARCHITECTURE.md) for the full launcher pattern.

**Worked example to point your LLM at.** One sample page ships in
`BROWSER_SCRIPTS/` and `DISPLAY_SCRIPTS/` to set the shape:

- `01_list_libraries/` — minimal. One fetch on mount, render an `id` /
  `displayName` table. Two files: `list_libraries.py` (launcher on a
  free port) and `list_libraries.html` (Vue 3 from CDN, calls
  `/api/tool/get_libraries`). That's the whole pattern — every
  project-specific page is a copy of this with the tool name and the
  rendering swapped out.

For a richer shape — interactive controls, client-side caching, no
round-tripping per keystroke — point your LLM at the SMIP-side artifact
at `___SMIP_SAAS_SIDE___/SMIP Browser Scripts/unit_converter.html`. It's the
end state of the round-trip described in step 7 below: the
`get_quantities_with_units` tool you built in
[QUICKSTART step 5](QUICKSTART.md), plus a vibe-coded Vue page with two
coupled dropdowns and a flip button, ported into a SMIP browser
script. Read it as "if you do this whole workflow correctly, here's
what you end up with."

The recommended vibe-coding loop is: build the tool first (step 2), then
prompt your LLM in plain language. Something like:

> Build me a page that uses the `<tool_name>` tool. Make it look like
> `01_list_libraries`.

That's enough. The LLM picks up the `BROWSER_SCRIPTS/` and `DISPLAY_SCRIPTS/` conventions, the launcher
pattern, the Vue 3 + CDN choice, and the thin-shell-around-a-tool-call
shape from the existing samples and the architecture doc. No need to
hand it file paths or stack choices.

### 4. Validate the tool surface from an LLM angle

After every meaningful tool registry change, exercise the registry from
an angle where the LLM has to *choose* which tool to call rather than
being told. This validates the registry differently than your pages do
— your pages call specific tools by name; the agent has to pick based
on the tool descriptions. If the agent can't pick the right tool, your
descriptions are too vague.

Three ways to do this, in order of setup cost:

- **The built-in chat agent** at `/chat` or `/chat_canvas` (requires the
  Azure OpenAI `.env` from QUICKSTART step 4). Ask a natural-language
  question and watch the tool calls.
- **An MCP client** like Claude Desktop or Cursor pointed at
  `smip_mcp_server.py` (requires the MCP bonus step from QUICKSTART).
  Same idea, different runtime — same source of truth.
- **The docs page** at `/` (no extra setup). It generates a "Run" form
  per registered tool with the registered description visible. Read the
  description as if you were an LLM seeing it for the first time — would
  you know when to use this tool? If not, sharpen the description.

This is one of the cheapest, highest-signal feedback loops in the
template. Use whichever surface you have wired up.

### 5. Round-trip to SMIP-side scripts

Once a page or script earns its keep — meaning it's done a job a few times
and you want it on the SMIP side rather than running on localhost — port
it to one of the vendored Joomla/PHP browser-script templates under
`___SMIP_SAAS_SIDE___/SMIP Browser Scripts/  (and SMIP Display Scripts/)`:

| Sample                          | Use it for                                          |
| ------------------------------- | --------------------------------------------------- |
| `sample_browser_script.html`    | Standalone pages (no specific instance binding)     |
| `sample_display_script.html`    | Pages bound to an instance via `context.std_inputs.node_id` |

The conversion is largely mechanical — Vue + GraphQL is on both sides —
but the SMIP-side script uses the JS SDK rather than your Python tools.
Which leads to the parity question…

### 6. Keep the JS SDK in lockstep with TOOL_REGISTRY

For step 5 to work, every tool a SMIP-side script needs must also exist
on the JS side. The JS side is split in two on purpose, and where you
put a new method depends on what kind of method it is.

**Two folders, one namespace.**

| Folder                                          | Holds                                              | Lifecycle                                                    |
| ----------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------ |
| `___SMIP_SAAS_SIDE___/SMIP JS SDK/`             | **Generic**, tenant-agnostic SMIP plumbing         | Grown in *this* repo. Edit here directly.                    |
| `___SMIP_SAAS_SIDE___/JS SDK Template/`         | **Domain / tenant-specific** methods               | Vendored snapshot of DevCon-SMIP Topic 06. Edits go upstream first, then re-vendor. |

Both libraries declare into the same two globals (`apiDemoMethods` and
`apiDemoTools`) using the additive merge pattern at the top of
`02 API Tools.html`:

```js
var apiDemoTools   = (typeof apiDemoTools   !== 'undefined') ? apiDemoTools   : [];
var apiDemoMethods = (typeof apiDemoMethods !== 'undefined') ? apiDemoMethods : {};
apiDemoTools.push( /* this library's descriptors */ );
Object.assign(apiDemoMethods, { /* this library's methods */ });
```

A consumer SMIP script does two `includeScript` calls — one for
`smip_js_sdk.api_tools`, one for the tenant SDK — and both sets of
methods land on the same `apiDemoMethods.<name>` namespace. Order
doesn't matter. From the consumer's point of view it's one SDK.

**Where does a new method go?** Decide by asking "would another
SMIP project, on a different tenant, want this exact method?":

- *Yes* → it's generic. Put it in `SMIP JS SDK/`. Examples:
  `updateAttribute`, `updateObject`, `getTypes`, `getObject`,
  `getEnumTypes` — the five already there. New candidates: anything
  that wraps a stock PostGraphile mutation/query without referencing
  tenant types, attribute names, or domain vocabulary.
- *No* → it's tenant-shaped. Put it in `JS SDK Template/`. Examples:
  the doublet demos in the existing template, plus your project's own
  `searchHeatNumbersByGrade`, `getStorageShelfChildEquipment`, etc.

**The narrowing pattern.** A tenant method isn't just "another method on
the same namespace" — it's typically a *narrowing* of a generic one.
The generic `getObject` has to fetch all ten value-variant columns
(`boolValue` / `intValue` / `floatValue` / `stringValue` / `datetimeValue`
/ `intervalValue` / `objectValue` / `enumerationValue` / `geopointValue` /
`referencedNodeId`) plus `dataType` on every attribute, because it
doesn't know your schema. A tenant `getMotors` does:

```js
// Generic — schema-agnostic. Returns all 10 value variants + dataType
// per attribute. Caller has to find the hp attribute, check its
// dataType, read floatValue.
const obj = await apiDemoMethods.getObject({
  nodeId,
  includeAttributes: true,
});

// Tenant — schema-aware. Built once you know "Motor has hp (FLOAT)
// and snr (STRING)". Returns clean, flat rows.
const motors = await apiDemoMethods.getMotors({ search: "..." });
// → [{ id, displayName, hp: 7.5, snr: "MTR-2024-0317" }, ...]
```

The tenant method's GraphQL fragment fetches `hp { floatValue }` and
`snr { stringValue }` — not all ten variants — and shapes the result
into a flat row with the right JS type per field. The library export
(WORKFLOW step 1) is the input that lets you write that: it tells you
the type's attribute schema, so you know which value variant to pull
and how to type the field.

Domain methods are where "Motor has hp and snr" stops being a thing
the caller has to remember and starts being a thing encoded in one
place. Build them as you discover stable read/write shapes you reach
for repeatedly — same incremental pace as growing `TOOL_REGISTRY` on
the Python side. The generic layer stays the universal fallback for
exploration and one-offs; the tenant layer is what carries your
project's actual day-to-day vocabulary.

**Why the split is worth the effort.** It lets the generic plumbing
*grow in this repo* — every project that uses VibeCon-SMIP contributes
back to a shared, tenant-agnostic JS SDK, the same way generic helpers
on `SMIPClient` accumulate over time. Domain-specific stuff stays
out of the way in the template, which is itself versioned upstream
in DevCon-SMIP. Without the split, generic helpers would be locked
inside someone's tenant fork and unavailable to the next project.

**Keep starter tools, hide them from the docs page.** The Python side
already does this: `SMIPMethods` has plenty of internal-only methods
(`get_enum_type_by_display_name`, `create_object`, `delete_object`,
`update_attribute`) that are intentionally NOT in `TOOL_REGISTRY`. They
exist as scaffolding; they're not part of the public, LLM-facing,
docs-page surface.

The JS SDK should mirror that. The four generic mutations/queries that
ship in `SMIP JS SDK/` are the SDK's permanent smoke test — running
`GetTypesViaJs` from the doc page is the JS equivalent of running
`get_libraries` from `/api/tool/` to answer "is the wiring alive?".
Tenant-specific descriptors that ship in the template can stay
discoverable in `apiDemoTools` but should be hidden from the doc page
(a `documented: false` flag or equivalent) once you only want to see
your project's actual surface, not the template's scaffolding.

This convention preserves four things at once:

- **The smoke test.** Any project can always verify the SMIP-side
  wiring with the same starter tools.
- **Python ↔ JS parity.** Both sides have the same generic-vs-domain
  split — `SMIPClient`/generic-`SMIPMethods` ↔ `SMIP JS SDK`, and
  project-specific `SMIPMethods` ↔ `JS SDK Template` — so a developer
  working on either side doesn't have to relearn the convention.
- **A clean public contract.** The docs page reflects the project's
  real API, not "here's our project plus everything that came in the
  template box."
- **A growing generic surface.** New generic SMIP plumbing accumulates
  in `SMIP JS SDK/` and is reusable across every downstream project.

When you build a new Python tool that you know will round-trip, mirror
it on the JS side at the same time — same name, same parameters, same
return shape, in whichever of the two folders matches its scope.
Future-you will thank present-you for the discipline.

### 7. Hand the conversion to your LLM, paste, validate

You have a localhost page that earns its keep (step 5) and the matching
tool present on the JS SDK side (step 6). Hand the port to the same
whole-project-mode LLM that built the page. Same plain-language style
as step 3 — the LLM already knows what a SMIP browser script is, where
the templates live, where the GraphQL query lives in `TOOL_REGISTRY`,
and how to swap in `tiqJSHelper.invokeGraphQLAsync`.

> Create a browser script I can copy into the SMIP.

That's the literal prompt that produced
`___SMIP_SAAS_SIDE___/SMIP Browser Scripts/unit_converter.html` from a
localhost `BROWSER_SCRIPTS/unit_converter/` Vue page that lived in this repo
when these docs were written — since deleted to leave the round-trip as
an exercise (see the meta note below). The LLM does the templated
substitution, drops the Vue CDN tag, scopes the CSS, emits the right
Joomla/PHP preamble — all from context. The conversion is largely
mechanical because both sides are already Vue + GraphQL.

Then ship it:

1. Copy the LLM's output into your SMIP's browser-script editor.
2. Save and preview.
3. Confirm the page renders and behaves identically to the localhost
   version.

If it doesn't work first try, the usual suspects are:

- The SMIP runtime's Vue version doesn't support a feature your
  localhost page relied on (less likely with Vue 3 from CDN; both sides
  are typically aligned).
- A GraphQL field name differs between what's in your tool's query and
  what the SMIP-side schema actually accepts at this tenant (rare —
  TOOL_REGISTRY's query is the source of truth on both sides).
- A CSS rule conflicts with the SMIP's host stylesheet (most common).

Iterate locally first when you hit one of these — `BROWSER_SCRIPTS/` and `DISPLAY_SCRIPTS/` reload on
file save, the SMIP-side IDE doesn't. Fix in `BROWSER_SCRIPTS/` or `DISPLAY_SCRIPTS/`, re-port, re-paste.

> **⚡ Meta note: the unit-converter round-trip is vibe-coded
> end-to-end.** The artifact you can still see in the repo —
> `___SMIP_SAAS_SIDE___/SMIP Browser Scripts/unit_converter.html` — is the
> SMIP-side output of the full step 1–7 loop. The Python tool behind
> it is the same `get_quantities_with_units` you build in
> [QUICKSTART step 5](QUICKSTART.md) by pasting a single prompt;
> the localhost Vue page that fed the round-trip
> (originally at `BROWSER_SCRIPTS/unit_converter/`) was deleted from the
> starter once it had served its purpose, but rebuilding it from the
> tool is itself a one-prompt task following the loop above. A few
> minor human course corrections kept the UX honest ("default to
> °F → °C", "add a flip button"). Zero hand-written JavaScript, zero
> hand-written GraphQL. Read the SMIP-side file as the existence-proof:
> this is what the loop produces.

## Review the language — it's the artifact

An LLM in whole-project mode will happily produce a mountain of
artifacts from a single prompt — methods, registry entries, classes
in `SMIP_IO/model/`, docstrings, intent comments, tool descriptions.
Most of that mountain is **language**, not code. Open any production
file in this repo and count: roughly 80% prose, 20% Python. That
ratio is deliberate.

The language is the highest-leverage artifact you'll ship, because
it's what almost everything else reads:

- It's what the **LLM reads** when you load the repo into a future
  whole-project session. Vague descriptions become vague assumptions
  every time.
- It's what the **`/chat` agent reads** when picking a tool. Bad
  description, bad tool selection — see anti-patterns below.
- It's what the **docs page renders**, what **IDE tooltips show**, and
  what **you** will read in three months when you've forgotten the why.

The first draft of all this language is LLM-generated, and it's almost
never right the first time. The LLM hedges, repeats, generalizes, uses
templated phrasings, and confidently misnames things. Going through
every method, every tool, every class on a dedicated review pass —
reading the language out loud and rewriting wherever it's wrong,
vague, or missing the *why* — is some of the highest-leverage time
you will spend on a project. It compounds: every future LLM session
on the codebase becomes more reliable because the context it reads is
more honest.

Treat the language review as part of the build, not a polish step.
When you finish a session where the LLM produced a batch of new tools
or model classes, **always plan a follow-up pass just to read what
was written**. Most of the work in that pass is human judgment about
wording, naming, and intent — exactly the thing the LLM is least
equipped to nail on the first try.

**Do that pass *with* the LLM, not alone in VS Code.** Open the same
whole-project session and tell it something like:

> Let's review the tools and the docstrings one by one. One after the
> other, bathroom, sleep, and shower breaks included.

The LLM will walk you through each artifact in order, pause for your
judgment at every one, and resume cleanly when you come back — "ok,
pick up where we left off?" — even days later. The review will
genuinely run across multiple sessions; that's fine, the file tree
holds your place. Trying to do this solo by scrolling through files
in your editor is slower and weaker: you'll skim where you should
pause, and the patterns across files (this tool's description echoes
that one's because the LLM templated both) won't show up until much
later.

**And once you've done a solo pass, the same pattern scales to your
team.** Hand individual tools (and the model classes they touch) to
colleagues with the relevant subject-matter expertise — the control
engineer who knows the equipment hierarchy, the operations manager
who lives with the downtime reason codes, the metallurgist who knows
what a heat number actually means in *your* plant. Open the LLM
session, point it at the tool, let the SME read the description out
loud, and transcribe their corrections in real time. **Subject-matter
expertise is a team sport.** The right name for a thing, the right
"when do I use this" hint, the right unit of measure for a field —
that knowledge usually lives in someone else's head. The clean tool
boundaries and the 80%-prose ratio are what make the handoff
practical: you're giving a colleague a small, self-contained,
mostly-prose artifact to react to — not asking them to navigate
Python.

## Anti-patterns to watch for

A few failure modes worth naming so you can spot them early:

**Pages with raw GraphQL.** First red flag of the discipline slipping.
The fix is always the same: extract the query into a tool. Your future
chat agent will thank you, and so will the next page that needs the
same data.

**Tools with vague descriptions.** "Get stuff from the SMIP" is not a
description. The agent in `/chat` is the test — if it can't pick your
tool reliably given the user's natural-language question, the
description needs more specifics about *what* and *when to use*.

**One giant tool that does everything.** The temptation when you have
a complex query is to expose it as one big tool with twelve optional
parameters. Resist. Smaller tools with sharper purpose compose better
in agent conversations and are easier to round-trip into JS SDK
parity.

**Scripts that don't exit cleanly.** A `SCRIPTS/` script should `return
0` on success and non-zero on failure so it can be wired into a
pipeline or scheduled task. If it just hangs or prints "Done" without
exiting, that's not yet a worker script.
