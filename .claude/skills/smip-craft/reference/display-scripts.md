# Display scripts: how SMIP renders them, and what that does to your layout

Observed on a production tenant, 2026-09-21/22, and bitten more than
once before that. Read before laying out a header, a wide table, or an SVG.

## The pane is an `<object>`, not an inline render

Opening a display script's tab in the Model Explorer puts this in the pane:

```html
<object data="/index.php?option=com_thinkiq&task=previewScript
              &script_name=<relativeName>_<scriptId>.php
              &script_id=<scriptId>&parent_id=<node.partOfId>&node_id=<nodeId>
              &hideHeader&hideFooter" width="100%" height="...">
```

Your script is therefore a **separate HTML document** produced by the
`previewScript` route, wrapped in the platform's own page chrome:

```
body.flex
└── .page-content.py-3
    └── .container-fluid.d-flex.flex-grow-1
        └── .row.flex-grow-1
            └── main.d-flex.flex-grow-1.flex-column.col-12
                └── #app        <- your Vue root
```

The same route without `hideHeader&hideFooter` is the full-page view: what the
Overview tab's display-script links open, and what the standard header's
"open in tab" icon builds.

Facts about the route:

- `script_name` is the **disk file name** `<relativeName>_<id>.php`, extension
  included. The PHP `Context` injects `std_inputs.script_name` **without**
  `.php`; used verbatim it lands on a blank page. Build the name from GraphQL
  `script(id){relativeName}` plus the script id.
- `parent_id` is the node's parent object (`object.partOfId`) and is
  **optional**: a root node such as External Users renders without it.
- It is authenticated by the Joomla session cookie, not the GraphQL bearer, so
  you cannot fetch it from a script or a test.
- `std_inputs` also carries `node_id`, `script_id`, `parent_id`,
  `output_type`, `in_IDE`, and null `start_timestamp`/`end_timestamp`.

## The horizontal-overflow trap

Nothing in that wrapper chain pins the document's width to the pane. So:

1. Content wider than the pane widens the **whole embedded document**: a
   graphviz SVG at its natural `pt` size, a table with many columns, a long
   unbroken string. The pane grows a horizontal scrollbar.
2. Everything right-aligned (`float-end`, `justify-content-end`, `right:0`)
   then sits at the document's *true* right edge, off-screen until the user
   scrolls sideways. It looks as if the wide content "ate" the header icons.
   The DOM is intact. In devtools, inside the embedded frame,
   `el.getBoundingClientRect().x > innerWidth` is the tell.
3. `#app` is a flex item of `main` (a flex column). A flex item's default
   `min-width: auto` makes its minimum width its content's minimum width, so
   an overflowing child widens `#app` itself, not just a scroll region.

### The fix: supply the bucket the wrapper does not

```html
<style>
  /* graphviz output carries a viewBox; capping the width scales the drawing
     down instead of widening the document */
  #graph svg { max-width: 100%; height: auto; display: block; }
</style>

<div id="app" style="position:relative; max-width:100%; overflow-x:hidden;">
  <!-- header affordances: position:absolute inside the clamped #app -->
  ...
  <div id="graph" style="max-width:100%; overflow-x:auto;"></div>
  <div class="table-responsive"><table class="table">...</table></div>
</div>
```

- `overflow-x` set to anything but `visible` also resets the flex item's
  `min-width: auto` to 0, which is what actually stops `#app` growing.
- Do **not** use `position: fixed` for header affordances: the full-page view
  has the site banner on top. `position: absolute` inside the clamped `#app`
  works in both views.
- Start every new display script with the `#app` clamp. It costs nothing on
  scripts that never overflow.

## The standard header: two icons, labels in `title`

Font Awesome Pro (light style) is loaded by the platform's page wrapper.

| Icon | Link |
|---|---|
| `fa-light fa-code` | the script in the IDE: `/applications/ide?node_ids=<scriptId>&selected=<scriptId>` |
| `fa-light fa-arrow-up-right-from-square` | the script full-page in a new tab: the `previewScript` URL above, built from GraphQL |
| `fa-light fa-file-csv` | a CSV export button, where the view is a table |

```html
<a class="float-end btn btn-sm btn-link mt-2" style="font-size:1.1rem; color:#126181;"
   v-bind:href="`/applications/ide?node_ids=${context.std_inputs.script_id}&selected=${context.std_inputs.script_id}`"
   target="_blank" title="Source in the IDE"><i class="fa-light fa-code"></i></a>
<a v-if="previewUrl" class="float-end btn btn-sm btn-link mt-2" style="font-size:1.1rem; color:#126181;"
   v-bind:href="previewUrl" target="_blank" title="Open full-page in a new tab"><i class="fa-light fa-arrow-up-right-from-square"></i></a>
```

`previewUrl` comes from one small fire-and-forget query at mount:

```js
LoadPreviewUrlAsync: async function(){
    try {
        let inputs = this.context.std_inputs || {};
        let scriptId = String(inputs.script_id || "").trim();
        let nodeId = String(inputs.node_id || "").trim();
        if(!/^\d+$/.test(scriptId) || !/^\d+$/.test(nodeId)){ return; }
        let r = await tiqJSHelper.invokeGraphQLAsync(`
            query StandardHeader {
                script(id: "${scriptId}") { relativeName }
                object(id: "${nodeId}") { partOfId }
            }`);
        let data = (r || {}).data || {};
        let relativeName = (data.script || {}).relativeName || "";
        let parentId = String((data.object || {}).partOfId || "");
        if(!relativeName){ return; }
        let params = { option: "com_thinkiq", task: "previewScript",
                       script_name: `${relativeName}_${scriptId}.php`,
                       script_id: scriptId, node_id: nodeId };
        if(parentId){ params.parent_id = parentId; }
        this.previewUrl = `/index.php?${new URLSearchParams(params)}`;
    } catch (e) { /* link stays hidden */ }
},
```

Boards that cannot spare a title bar use the same two icons in a
`position:absolute` strip of `1.9rem` at the top-right, no title, no rule.

## Older source-link URL to retire on sight

`/index.php?option=com_modeleditor&view=script&id=<id>` is the pre-IDE form
and still lurks in old scripts, usually inside a `<div hidden>` header. Replace
it with the `/applications/ide?node_ids=...&selected=...` form.

## Joomla rewrites `data="` inside `<object>` tags

Found 2026-10-12. Joomla's SEF plugin turns relative URLs into absolute ones
in served HTML. One of its patterns matches an `<object …>` tag's `data="` and
prefixes the site base `/`. The pattern is roughly `<object\s+[^>]*data\s*=\s*"`,
so it also catches the tail of **`v-bind:data="…"` (or `:data="…"`)**.
`v-bind:data="AuditViewUrl(ActiveRecord)"` reached the browser as
`v-bind:data="/AuditViewUrl(ActiveRecord)"`. Vue compiled that into
`data: /AuditViewUrl(...)`, an unterminated regex, and the whole app died with
**`Uncaught SyntaxError: Invalid regular expression: missing /`** in an anonymous
`VM…` chunk from `tiq.core.min.js`. The local twin never shows it, because
the rewrite happens only when the platform serves the page.

- To embed one display script in another via `<object>`, use the object-form
  binding **`v-bind="{ data: someUrl }"`**, so that no `data="` text exists
  in the tag. Keep the literal out of comments too.
- `v-bind:href` / `v-bind:src` are not hit: those rules need whitespace right
  before the attribute name. A *plain* relative `href="x"` or `src="x"`
  would be rewritten.
- Diagnose with DevTools → the `VM…:line` link on the error. It opens Vue's
  compiled render function. Look for a binding whose value gained a leading `/`.

## Runtime facts that shape twins

- `tiqJSHelper.invokeGraphQLAsync(query)` takes **one** argument; a second
  `variables` object is silently dropped and the server then rejects
  `Variable "$id" ... was not provided`. Interpolate digit-validated ids into
  the document instead.
- `createApp`, `tiqJSHelper`, `apiDemoMethods` and the `tiq.*` component stubs
  are globals on the platform; the local twin gets them from
  `_shims/tiq_runtime.js`.
- The script runs from **disk**, `<relativeName>_<id>.php`, rewritten only by
  an IDE Save. A GraphQL `updateScript` changes the row, not the page. See the
  `smip-script-sync` skill.
