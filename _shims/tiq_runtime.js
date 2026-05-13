/* ===========================================================================
 * DISPLAY_SCRIPTS / _shims / tiq_runtime.js
 *
 * Local-twin runtime shim. Provides the same browser-side globals a SMIP
 * browser-script would see when running inside Joomla, but routed through
 * the Flask app this repo already exposes:
 *
 *   window.tiqContext               <- { std_inputs: { node_id, script_id } }
 *                                     populated from URL params, so the
 *                                     local twin's `context.std_inputs.node_id`
 *                                     references resolve the same way they
 *                                     do in SMIP.
 *
 *   window.tiqJSHelper              <- { invokeGraphQLAsync(query, variables?) }
 *                                     posts to /api/graphql; returns the
 *                                     raw GraphQL response { data, errors }
 *                                     so SDK code that does `resp.data.X`
 *                                     works unmodified.
 *
 *   window.apiDemoMethods           <- matches the SMIP-side SDK surface for
 *                                     the methods this repo's local twins
 *                                     consume. Generic helpers ship here
 *                                     (_buildPatchLiteral, updateAttribute,
 *                                     updateObject) — they work for any
 *                                     project against the SMIP mutation
 *                                     surface. Project-specific reads
 *                                     get appended here as twins are
 *                                     ported.
 *
 * The shim is served as a static file at /shims/tiq_runtime.js — wired up
 * by DISPLAY_SCRIPTS/__init__.py's `_register_shared_shim_routes`. Local
 * twins load it with a plain <script src> tag.
 *
 * SMIP-only link interception is also implemented here: <a href^="/applications/">
 * links get rewritten on hover (title) and intercepted on click (clipboard +
 * toast) on localhost. On SMIP itself the shim isn't loaded, so the link's
 * default behavior is restored.
 * =========================================================================== */

(function () {
  // -------------------------------------------------------------------
  // tiqContext — fed from the URL the playground uses to mount the
  // iframe. The playground passes ?node_id=<id> when a tree node is
  // selected; this shim reads it back here so the twin's
  // `context.std_inputs.node_id` resolves to the selected SMIP object.
  // -------------------------------------------------------------------
  const params = new URLSearchParams(window.location.search);
  const nodeId   = params.get("node_id")   || "";
  const scriptId = params.get("script_id") || "0";
  window.tiqContext = window.tiqContext || {
    std_inputs: { node_id: nodeId, script_id: scriptId },
  };
  // SMIP's PHP wrapper also injects $user via json_encode; local twins
  // don't have a real user, but the binding has to resolve so the Vue
  // template doesn't throw.
  window.tiqUser = window.tiqUser || null;

  function jsonHeaders(extra) {
    return Object.assign({ "Content-Type": "application/json" }, extra || {});
  }

  // -------------------------------------------------------------------
  // tiqJSHelper.invokeGraphQLAsync — drop-in for the SMIP global.
  // Posts to /api/graphql (the raw passthrough on the Flask app) and
  // returns the GraphQL response unchanged. Shim consumers do
  //   const resp = await tiqJSHelper.invokeGraphQLAsync(query);
  //   resp.data.tiqTypes / resp.errors / ...
  // exactly the way they would on the SMIP side.
  // -------------------------------------------------------------------
  async function invokeGraphQLAsync(query, variables) {
    const r = await fetch("/api/graphql", {
      method:  "POST",
      headers: jsonHeaders(),
      body:    JSON.stringify(variables == null ? { query } : { query, variables }),
    });
    if (!r.ok) {
      let env = {};
      try { env = await r.json(); } catch (_) {}
      throw new Error(env.error || ("HTTP " + r.status));
    }
    return await r.json();
  }
  window.tiqJSHelper = window.tiqJSHelper || {};
  if (!window.tiqJSHelper.invokeGraphQLAsync) {
    window.tiqJSHelper.invokeGraphQLAsync = invokeGraphQLAsync;
  }

  // -------------------------------------------------------------------
  // /api/tool/<name> envelope helper. Every tool in the registry
  // returns { ok: true, data: ... } / { ok: false, error: ... }; this
  // helper unwraps to data or throws. Used by apiDemoMethods.* below
  // when a twin would rather hit a named tool than send raw GraphQL.
  // -------------------------------------------------------------------
  async function callTool(name, args) {
    const r = await fetch("/api/tool/" + encodeURIComponent(name), {
      method:  "POST",
      headers: jsonHeaders(),
      body:    JSON.stringify({ args: args || {} }),
    });
    let env = {};
    try { env = await r.json(); } catch (_) {}
    if (!r.ok || !env.ok) {
      throw new Error(env.error || ("HTTP " + r.status));
    }
    return env.data;
  }

  // -------------------------------------------------------------------
  // apiDemoMethods — translation layer between Python's snake_case
  // /api/tool/<n> envelope and the camelCase shape the SMIP-bundled
  // JS SDK returns. Project-specific reads land here as twins are
  // ported. The generic helpers below cover any project that wants
  // to issue SMIP mutations.
  // -------------------------------------------------------------------
  window.apiDemoMethods = window.apiDemoMethods || {};

  // _buildPatchLiteral
  // ------------------
  // Helper used by updateAttribute / updateObject to turn a JS patch
  // object into the GraphQL `{ key: value, ... }` literal the mutation
  // body expects. Ported byte-for-byte from the SMIP-bundled
  // `smip_js_sdk.api_tools` so the rendered mutation strings are
  // identical between SMIP and local.
  //
  //   undefined  -> skipped (no key emitted)
  //   null       -> emitted as `key: null` (clears the column)
  //   number/bool-> emitted bare so floats stay floats
  //   anything   -> JSON.stringify -> quoted/escaped string
  function _buildPatchLiteral(patch) {
    const parts = [];
    for (const key of Object.keys(patch || {})) {
      const v = patch[key];
      if (v === undefined) continue;
      if (v === null) { parts.push(key + ": null"); continue; }
      if (typeof v === "number" || typeof v === "boolean") {
        parts.push(key + ": " + v);
      } else {
        parts.push(key + ": " + JSON.stringify(String(v)));
      }
    }
    return "{ " + parts.join(", ") + " }";
  }
  if (!window.apiDemoMethods._buildPatchLiteral) {
    window.apiDemoMethods._buildPatchLiteral = _buildPatchLiteral;
  }

  // updateAttribute
  // ---------------
  // Generic SMIP mutation. Args: { attributeId, patch }. patch is a
  // JS object with one or more AttributePatch fields:
  //   floatValue, datetimeValue, stringValue, enumerationValue,
  //   intValue (BigInt scalar — pass as a string), objectValue,
  //   boolValue. Pass null to clear; omit to skip.
  // Returns the full GraphQL response envelope so callers can read
  // `data.updateAttribute.clientMutationId` if they want.
  if (!window.apiDemoMethods.updateAttribute) {
    window.apiDemoMethods.updateAttribute = async function (args) {
      const attributeId = String((args && args.attributeId) || "").trim();
      const patch       = (args && args.patch) || {};
      if (!attributeId || !/^\d+$/.test(attributeId)) {
        throw new Error("updateAttribute: attributeId must be digits-only; got " + JSON.stringify(attributeId));
      }
      if (Object.keys(patch).length === 0) {
        throw new Error("updateAttribute: patch must contain at least one field");
      }
      const patchLit = _buildPatchLiteral(patch);
      const mutation = `
        mutation UpdateAttribute {
          updateAttribute(input: {
            id: "${attributeId}",
            patch: ${patchLit}
          }) { clientMutationId }
        }
      `;
      return await window.tiqJSHelper.invokeGraphQLAsync(mutation);
    };
  }

  // updateObject
  // ------------
  // Generic SMIP mutation. Args: { id, patch }. patch fields:
  //   importance (int), displayName (string), description (string).
  // Returns the GraphQL response envelope.
  if (!window.apiDemoMethods.updateObject) {
    window.apiDemoMethods.updateObject = async function (args) {
      const id    = String((args && args.id) || "").trim();
      const patch = (args && args.patch) || {};
      if (!id || !/^\d+$/.test(id)) {
        throw new Error("updateObject: id must be digits-only; got " + JSON.stringify(id));
      }
      if (Object.keys(patch).length === 0) {
        throw new Error("updateObject: patch must contain at least one field");
      }
      const patchLit = _buildPatchLiteral(patch);
      const mutation = `
        mutation UpdateObject {
          updateObject(input: {
            id: "${id}",
            patch: ${patchLit}
          }) {
            object { id importance displayName description }
          }
        }
      `;
      return await window.tiqJSHelper.invokeGraphQLAsync(mutation);
    };
  }

  // -------------------------------------------------------------------
  // tiq.components stubs — the SMIP runtime registers <wait-indicator>
  // and friends globally via tiq.components.min.js. Local twins that
  // reference them would render unknown-element warnings without a
  // shim. This hook registers no-op components on the active Vue
  // app once it's available — local twins call
  // window.__registerTiqComponentStubs(app) after createApp().
  // -------------------------------------------------------------------
  function registerTiqComponentStubs(app) {
    if (!app || typeof app.component !== "function") return;
    const noop = { template: "<span></span>" };
    if (!app.__tiqStubsRegistered) {
      app.component("wait-indicator", noop);
      app.__tiqStubsRegistered = true;
    }
  }
  window.__registerTiqComponentStubs = registerTiqComponentStubs;

  // -------------------------------------------------------------------
  // SMIP-only link interception.
  //
  // Display script bodies hardcode relative URLs like
  //   /applications/ide?node_ids=...
  //   /applications/model-explorer?...
  // that resolve correctly against the tenant origin on SMIP but
  // 404 (or worse, bounce through SMIP login + an error page) on
  // localhost. We don't modify the body to disable / hide them —
  // that breaks stickiness. Instead, the shim:
  //
  //   * Annotates every <a href^="/applications/"> link's `title`
  //     on first hover with the SMIP-equivalent URL.
  //   * Intercepts the click, prevents default, copies the
  //     SMIP-equivalent URL to the clipboard, and shows a toast
  //     ("Copied — paste in your SMIP browser tab").
  //
  // The result: the affordance stays visible in the local twin (so
  // the layout matches SMIP), the user always knows it's a SMIP-only
  // link, and one click puts them one paste away from using it on
  // SMIP. On SMIP itself the shim isn't loaded, so the link's
  // default behavior is restored and it works as authored.
  // -------------------------------------------------------------------
  let __smipOrigin = "";
  (async function () {
    try {
      const r = await fetch("/api/smip_origin");
      const env = await r.json();
      if (env && env.ok && env.data && env.data.origin) {
        __smipOrigin = String(env.data.origin);
      }
    } catch (_) { /* leave as "" — toast will still show the path */ }
  })();

  // Match any /applications/* path (covers /applications/ide,
  // /applications/model-explorer, and any future SMIP UI route).
  function isSmipOnlyHref(href) {
    return typeof href === "string" && href.indexOf("/applications/") === 0;
  }

  // Inject base + toast styling once.
  //
  // The base rule (html/body overflow-x: hidden) compensates for a
  // Bootstrap-without-container quirk in display scripts: `.row` uses
  // negative ±12px margins that are supposed to be cancelled by an
  // enclosing `.container[-fluid]`'s padding. Display-script HTML
  // tends to mount `.row` directly under `<div id="app">` without a
  // container, so the row spills 12px past each side of the body —
  // browser draws a horizontal scrollbar even when nothing meaningful
  // overflows. Clipping the empty-margin area is harmless (no real
  // content lives there) and saves us from editing every script.
  (function injectBaseStyle() {
    const style = document.createElement("style");
    style.textContent = `
      html, body { overflow-x: hidden; }
      .smip-toast {
        position: fixed;
        top: 16px;
        right: 16px;
        max-width: 380px;
        background: #126181;
        color: #fff;
        padding: 0.6rem 0.85rem;
        border-radius: 4px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.18);
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 0.82rem;
        line-height: 1.4;
        white-space: pre-wrap;
        word-break: break-all;
        z-index: 99999;
        opacity: 0;
        transform: translateY(-6px);
        transition: opacity 0.18s ease, transform 0.18s ease;
        pointer-events: none;
      }
      .smip-toast.show { opacity: 1; transform: translateY(0); }
      .smip-toast .smip-toast-title {
        display: block;
        font-weight: 600;
        font-size: 0.78rem;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        color: #b8d2de;
        margin-bottom: 0.25rem;
      }
    `;
    document.head.appendChild(style);
  })();

  function showToast(title, body) {
    const div = document.createElement("div");
    div.className = "smip-toast";
    const t = document.createElement("span");
    t.className = "smip-toast-title";
    t.textContent = title;
    div.appendChild(t);
    div.appendChild(document.createTextNode(body));
    document.body.appendChild(div);
    // Force reflow so the .show transition runs.
    void div.offsetWidth;
    div.classList.add("show");
    setTimeout(function () {
      div.classList.remove("show");
      setTimeout(function () { div.remove(); }, 250);
    }, 3500);
  }

  // Mouseover: enrich the link's native `title` tooltip with a clear
  // "SMIP-only" explanation + the destination URL. Done once per link
  // (data-attribute sentinel) so we don't re-set on every mouseover.
  document.addEventListener("mouseover", function (e) {
    const a = e.target.closest && e.target.closest("a");
    if (!a) return;
    const href = a.getAttribute("href") || "";
    if (!isSmipOnlyHref(href)) return;
    if (a.dataset && a.dataset.smipTooltipped) return;
    if (a.dataset) a.dataset.smipTooltipped = "1";
    const target = (__smipOrigin || "") + href;
    a.title = "SMIP-only link — click to copy the URL:\n" + target;
  });

  // Click: intercept, copy SMIP URL to clipboard, toast.
  document.addEventListener("click", function (e) {
    const a = e.target.closest && e.target.closest("a");
    if (!a) return;
    const href = a.getAttribute("href") || "";
    if (!isSmipOnlyHref(href)) return;
    e.preventDefault();
    e.stopPropagation();
    const target = (__smipOrigin || "") + href;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(target).then(
        function () {
          showToast("SMIP-only link — URL copied", "Paste in your SMIP browser tab:\n" + target);
        },
        function () {
          showToast("SMIP-only link — copy failed", target);
        }
      );
    } else {
      showToast("SMIP-only link", target);
    }
  });
})();
