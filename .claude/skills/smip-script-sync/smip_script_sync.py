#!/usr/bin/env python3
"""smip_script_sync.py - move SMIP (ThinkIQ) platform scripts between a
project folder and a tenant, over GraphQL. Self-contained: needs `requests`
and a VibeCon-style `SMIP_IO/config.json` (or env vars). No project imports.

READ THIS FIRST
---------------
**A GraphQL write does not deploy a script.** Platform scripts EXECUTE as
files on disk in the Joomla host (`.../scripts/{relativeName}_{id}.php`);
`updateScript` only writes the Postgres row. Verified 2026-09-01 on
thermalworks.thinkiq.net: after a push the live page kept rendering the old
behaviour until the script was opened in the platform IDE and SAVED. The IDE
save is what manifests the row to disk.

**The stale state is undetectable from GraphQL.** The IDE save bumps
`updatedTimestamp` - the same field a push bumps - and nothing else moves.
No filename or disk field exists on `Script`. So `push` reports
"DB UPDATED - NOT YET LIVE", never "deployed", and `status` only INFERS from
write ordering (a later server write than ours means somebody saved).

What this tool is good for:
  * telling you which local files differ from the tenant, reliably;
  * staging a body so deploying is open-IDE-and-Save, not copy/paste;
  * pulling deployed scripts into a folder to bootstrap or round-trip;
  * binding local files to deployed scripts by id (sidecars) so pushes are
    deterministic and rename-proof.

COMMANDS
--------
  list                inventory of the tenant's scripts (id, host, type, name)
  pull   --dir D      write selected deployed scripts into D (+ sidecars)
  bind   --dir D      match unbound local files to deployed scripts by content
                      similarity and write `<file>.smip.json` sidecars (--apply)
  push   --dir D      diff local files against the tenant; --apply stages them
  status --dir D      which staged scripts still need an IDE Save

MATCHING
--------
A file is matched to a deployed script by its sidecar `<file>.smip.json`
(holds the script id) when present, else by content similarity. A content
match below --min-similarity is REFUSED: overwriting the wrong script with
the right file is the one unrecoverable mistake here. Run `bind --apply`
once to make matching deterministic.

SAFETY
------
- `push` is DRY RUN by default; `--apply` writes.
- Unified diff per script before anything is written.
- The deployed body is backed up to `<dir>/.smip_sync/backups/` before
  overwrite. There is no version history on the platform side.
- `pull` never overwrites a differing local file without `--force`, and
  backs up the local file first when it does.

CONFIG
------
First hit wins: --config PATH; $SMIP_CONFIG; ./SMIP_IO/config.json (walking
up to 3 parents); ./config.json. Shape (VibeCon):
  {"SMIP": {"graphQlEndpoint": ".../graphql", "clientId": "...",
            "clientSecret": "...", "role": "...", "userName": "..."}}
Env overrides: SMIP_GRAPHQL_ENDPOINT SMIP_CLIENT_ID SMIP_CLIENT_SECRET
SMIP_ROLE SMIP_USER_NAME, or SMIP_BEARER to skip the challenge flow.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("smip_script_sync needs the `requests` package: pip install requests")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LF = "\n"
CRLF = "\r\n"
SIDECAR_SUFFIX = ".smip.json"
STATE_DIRNAME = ".smip_sync"
SOURCE_EXTS = {".html", ".php", ".py", ".sql", ".js"}
DEFAULT_DIR = Path("___SMIP_SAAS_SIDE___") / "SMIP Display Scripts"

# A one-line marker injected after `<?php` when staging with --stamp, so the
# staged version is self-describing in the IDE. The old TW wording is kept in
# the regex so already-stamped tenant scripts still compare equal.
STAMP_PREFIX = "// staged by smip-script-sync "
STAMP_RE = re.compile(
    r"^\s*//\s*(staged by smip-script-sync|claude was here - staged) .*$")

ENV_KEYS = {
    "graphQlEndpoint": "SMIP_GRAPHQL_ENDPOINT",
    "clientId": "SMIP_CLIENT_ID",
    "clientSecret": "SMIP_CLIENT_SECRET",
    "role": "SMIP_ROLE",
    "userName": "SMIP_USER_NAME",
}


# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------

def load_config(path_arg: str | None) -> dict:
    cfg: dict = {}
    candidates: list[Path] = []
    if path_arg:
        candidates.append(Path(path_arg))
    if os.environ.get("SMIP_CONFIG"):
        candidates.append(Path(os.environ["SMIP_CONFIG"]))
    cwd = Path.cwd()
    for base in [cwd, *cwd.parents[:3]]:
        candidates.append(base / "SMIP_IO" / "config.json")
    candidates.append(cwd / "config.json")

    for cand in candidates:
        if cand.is_file():
            raw = json.loads(cand.read_text(encoding="utf-8-sig"))
            cfg = dict(raw.get("SMIP", raw))
            cfg["_source"] = str(cand)
            break

    for key, env in ENV_KEYS.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    if os.environ.get("SMIP_BEARER"):
        cfg["bearer"] = os.environ["SMIP_BEARER"]

    if not cfg.get("graphQlEndpoint"):
        sys.exit("No SMIP config found. Pass --config, set $SMIP_CONFIG, or run "
                 "from a project with SMIP_IO/config.json. Looked at:\n  "
                 + "\n  ".join(str(c) for c in candidates))
    if not cfg.get("bearer"):
        missing = [k for k in ENV_KEYS if not cfg.get(k)]
        if missing:
            sys.exit("Config is missing: " + ", ".join(missing))
    return cfg


class Smip:
    """Minimal SMIP GraphQL client with the challenge/response auth flow."""

    def __init__(self, cfg: dict):
        self.endpoint = cfg["graphQlEndpoint"]
        self.client_id = cfg.get("clientId")
        self.client_secret = cfg.get("clientSecret")
        self.role = cfg.get("role")
        self.user_name = cfg.get("userName")
        self._jwt = ("Bearer " + cfg["bearer"].removeprefix("Bearer ").strip()
                     if cfg.get("bearer") else None)
        self.source = cfg.get("_source", "env")

    @property
    def base_url(self) -> str:
        return re.sub(r"/graphql/?$", "", self.endpoint.rstrip("/"))

    def ide_url(self, script_id) -> str:
        return f"{self.base_url}/applications/ide?node_ids={script_id}&selected={script_id}"

    def _post(self, payload: dict, headers: dict) -> dict:
        r = requests.post(self.endpoint, json=payload, headers=headers, timeout=120)
        r.raise_for_status()
        return r.json()

    def _authenticate(self) -> str:
        req = self._post({"query": (
            'mutation { authenticationRequest(input: {authenticator: %s, role: %s, '
            'userName: %s}) { jwtRequest { challenge message } } }'
            % (json.dumps(self.client_id), json.dumps(self.role),
               json.dumps(self.user_name)))}, {})
        jwt_request = ((req.get("data") or {}).get("authenticationRequest") or {}).get("jwtRequest") or {}
        challenge = jwt_request.get("challenge")
        if not challenge:
            raise RuntimeError("authenticationRequest failed: " + json.dumps(req)[:500])
        signed = f"{challenge}|{self.client_secret}"
        val = self._post({"query": (
            'mutation { authenticationValidation(input: {authenticator: %s, '
            'signedChallenge: %s}) { jwtClaim } }'
            % (json.dumps(self.client_id), json.dumps(signed)))}, {})
        claim = ((val.get("data") or {}).get("authenticationValidation") or {}).get("jwtClaim")
        if not claim:
            raise RuntimeError("authenticationValidation failed: " + json.dumps(val)[:500])
        self._jwt = "Bearer " + claim
        return self._jwt

    def query(self, query: str, variables: dict | None = None) -> dict:
        if not self._jwt:
            self._authenticate()
        payload: dict = {"query": query}
        if variables is not None:
            payload["variables"] = variables
        resp = self._post(payload, {"Authorization": self._jwt})
        if resp.get("errors"):
            raise RuntimeError("GraphQL errors: " + json.dumps(resp["errors"])[:1000])
        return resp.get("data") or {}

    def scripts(self, with_source: bool = True) -> list[dict]:
        """Every script in the tenant, on libraries, types and objects alike.
        `tiqTypes { scripts }` would miss the instance-attached ones."""
        body = " script" if with_source else ""
        data = self.query(
            "query { scripts { id displayName relativeName fqn scriptType outputType "
            "updatedTimestamp" + body + " onType { displayName } onObject { displayName } "
            "onLibrary { displayName } } }")
        return data.get("scripts") or []

    def update_script(self, script_id: str, body: str) -> dict:
        """DESTRUCTIVE: replaces the body outright; the platform keeps no history."""
        data = self.query(
            "mutation UpdateScript($input: UpdateScriptInput!) { updateScript(input: $input) "
            "{ script { id displayName outputType scriptType updatedTimestamp } } }",
            {"input": {"id": str(script_id), "patch": {"script": body}}})
        script = (data.get("updateScript") or {}).get("script")
        if not script:
            raise RuntimeError("updateScript returned no script")
        return script


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def normalise(text: str | None) -> list[str]:
    """Compare on rstripped lines with normalised newlines, stamp removed."""
    return [line.rstrip()
            for line in (text or "").replace(CRLF, LF).strip().split(LF)
            if not STAMP_RE.match(line)]


def stamped(text: str, when: str) -> str:
    lines = [l for l in text.replace(CRLF, LF).split(LF) if not STAMP_RE.match(l)]
    for i, line in enumerate(lines):
        if line.strip().startswith("<?php"):
            lines.insert(i + 1, STAMP_PREFIX + when)
            return LF.join(lines)
    return LF.join(lines)  # no <?php line: nothing to stamp after


def host_of(s: dict) -> tuple[str, str]:
    for kind, key in (("library", "onLibrary"), ("type", "onType"), ("object", "onObject")):
        if s.get(key):
            return kind, s[key].get("displayName") or "?"
    return "?", "?"


def ext_for(s: dict) -> str:
    st = (s.get("scriptType") or "").upper()
    ot = (s.get("outputType") or "").upper()
    if st == "PHP":
        return ".html" if ot in ("DISPLAY", "BROWSER") else ".php"
    return {"PYTHON": ".py", "SQL": ".sql"}.get(st, ".txt")


def disk_name(s: dict) -> str:
    """Derived, not stored: the IDE tab shows `{relativeName}_{id}.php`."""
    return f"{s.get('relativeName')}_{s.get('id')}{'.php' if (s.get('scriptType') or '').upper() == 'PHP' else ext_for(s)}"


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "script"


def sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + SIDECAR_SUFFIX)


def read_sidecar(path: Path) -> dict | None:
    sc = sidecar_path(path)
    if sc.is_file():
        try:
            return json.loads(sc.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            print(f"  WARNING: unreadable sidecar {sc.name}")
    return None


def write_sidecar(path: Path, s: dict) -> None:
    kind, name = host_of(s)
    meta = {
        "id": str(s["id"]),
        "displayName": s.get("displayName"),
        "relativeName": s.get("relativeName"),
        "fqn": s.get("fqn"),
        "host": {"kind": kind, "displayName": name},
        "scriptType": s.get("scriptType"),
        "outputType": s.get("outputType"),
        "diskName": disk_name(s),
    }
    sidecar_path(path).write_text(json.dumps(meta, indent=2) + LF, encoding="utf-8")


def iter_sources(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in SOURCE_EXTS
                  and not p.name.endswith(SIDECAR_SUFFIX))


def state_dir(args) -> Path:
    return Path(args.state_dir) if args.state_dir else Path(args.dir) / STATE_DIRNAME


def load_state(args) -> dict:
    f = state_dir(args) / "staged.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_state(args, state: dict) -> None:
    d = state_dir(args)
    d.mkdir(parents=True, exist_ok=True)
    (d / "staged.json").write_text(json.dumps(state, indent=2) + LF, encoding="utf-8")


def backup(args, name: str, text: str) -> Path:
    d = state_dir(args) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    p = d / f"{name}_{stamp}"
    p.write_text(text or "", encoding="utf-8")
    return p


def best_match(local_lines: list[str], deployed: list[dict]) -> tuple[dict | None, float]:
    best, score = None, -1.0
    for s in deployed:
        ratio = difflib.SequenceMatcher(None, local_lines, normalise(s.get("script"))).quick_ratio()
        if ratio > score:
            best, score = s, ratio
    return best, score


def resolve(path: Path, local_lines: list[str], deployed: list[dict],
            by_id: dict[str, dict]) -> tuple[dict | None, float, str]:
    """(deployed script, confidence, how) - how is 'sidecar', 'content' or 'gone'."""
    meta = read_sidecar(path)
    if meta and meta.get("id"):
        s = by_id.get(str(meta["id"]))
        return (s, 1.0, "sidecar") if s else (None, 0.0, "gone")
    s, score = best_match(local_lines, deployed)
    return s, score, "content"


def print_diff(remote: list[str], local: list[str], n: int, width: int = 150) -> int:
    diff = list(difflib.unified_diff(remote, local, "deployed", "local", lineterm="", n=n))
    for line in diff:
        print("    " + line[:width])
    return sum(1 for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))


def add_scope_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", action="append", default=[], help="Script id. Repeatable.")
    p.add_argument("--name", action="append", default=[],
                   help="Deployed displayName (case-insensitive). Repeatable.")
    p.add_argument("--library", action="append", default=[],
                   help="Scripts hosted on this library (displayName). Repeatable.")
    p.add_argument("--type", action="append", default=[],
                   help="Scripts hosted on this type (displayName). Repeatable.")
    p.add_argument("--object", action="append", default=[],
                   help="Scripts hosted on this object (displayName). Repeatable.")
    p.add_argument("--all", action="store_true", help="Every script in the tenant.")


def select(deployed: list[dict], args, require: bool) -> list[dict]:
    if args.all:
        return deployed
    ids = set(args.id)
    names = {n.lower() for n in args.name}
    hosts = {("library", n.lower()) for n in args.library} | \
            {("type", n.lower()) for n in args.type} | \
            {("object", n.lower()) for n in args.object}
    if not (ids or names or hosts):
        if require:
            sys.exit("Say what to select: --id/--name/--library/--type/--object, or --all.")
        return deployed
    out = []
    for s in deployed:
        kind, host = host_of(s)
        if (str(s["id"]) in ids or (s.get("displayName") or "").lower() in names
                or (kind, host.lower()) in hosts):
            out.append(s)
    return out


def folder(args) -> Path:
    d = Path(args.dir)
    if not d.is_dir():
        sys.exit(f"--dir {d} is not a directory")
    return d


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_list(smip: Smip, args) -> int:
    deployed = select(smip.scripts(with_source=False), args, require=False)
    if args.json:
        print(json.dumps(deployed, indent=2))
        return 0
    deployed.sort(key=lambda s: (host_of(s), (s.get("displayName") or "").lower()))
    print(f"{len(deployed)} script(s) on {smip.base_url}\n")
    print("%-9s %-8s %-30s %-7s %-9s %-19s %s" % ("id", "host", "hosted on", "type", "output", "updated", "displayName"))
    print("-" * 120)
    for s in deployed:
        kind, host = host_of(s)
        print("%-9s %-8s %-30s %-7s %-9s %-19s %s" % (
            s["id"], kind, host[:30], s.get("scriptType") or "", s.get("outputType") or "",
            (s.get("updatedTimestamp") or "")[:19], s.get("displayName")))
    return 0


def cmd_pull(smip: Smip, args) -> int:
    d = folder(args)
    deployed = select(smip.scripts(with_source=True), args, require=True)
    if not deployed:
        print("Nothing matched the selection.")
        return 0

    bound: dict[str, Path] = {}
    existing: dict[str, Path] = {}
    for p in iter_sources(d):
        existing[p.name.lower()] = p  # case-insensitive, so Windows and Linux behave alike
        meta = read_sidecar(p)
        if meta and meta.get("id"):
            bound[str(meta["id"])] = p

    written = kept = same = 0
    for s in sorted(deployed, key=lambda s: (s.get("displayName") or "").lower()):
        candidate = safe_name(s.get("displayName") or str(s["id"])) + ext_for(s)
        target = bound.get(str(s["id"])) or existing.get(candidate.lower()) or d / candidate
        remote_text = (s.get("script") or "").replace(CRLF, LF)
        label = f"{s['displayName']!s:<32} (id {s['id']}) -> {target.name}"
        if target.exists():
            local_text = target.read_text(encoding="utf-8-sig")
            if normalise(local_text) == normalise(remote_text):
                print(f"{label}  up to date")
                same += 1
                if not args.dry_run and not sidecar_path(target).exists():
                    write_sidecar(target, s)
                continue
            changed = print_diff(normalise(local_text), normalise(remote_text), args.context) \
                if args.show_diff else None
            if not args.force:
                print(f"{label}  LOCAL DIFFERS - kept"
                      + (f" ({changed} changed line(s))" if changed is not None else "")
                      + ". Use --force to overwrite, or `push` if local is the truth.")
                kept += 1
                continue
            if not args.dry_run:
                b = backup(args, f"local_{s['id']}{target.suffix}", local_text)
                print(f"{label}  OVERWRITTEN (local backup {b.name})")
        else:
            print(f"{label}  {'would write' if args.dry_run else 'written'}")
        if not args.dry_run:
            target.write_text(remote_text, encoding="utf-8")
            write_sidecar(target, s)
        written += 1

    print(f"\n{written} {'would be ' if args.dry_run else ''}written, {same} up to date, {kept} kept (differ)")
    return 0


def cmd_bind(smip: Smip, args) -> int:
    d = folder(args)
    deployed = smip.scripts(with_source=True)
    by_id = {str(s["id"]): s for s in deployed}
    claimed: dict[str, str] = {}
    bound = pending = refused = 0

    for p in iter_sources(d):
        local_lines = normalise(p.read_text(encoding="utf-8-sig"))
        meta = read_sidecar(p)
        if meta and not args.rebind:
            s = by_id.get(str(meta.get("id")))
            if s:
                print(f"{p.name:<36} bound to \"{s['displayName']}\" (id {s['id']})")
                claimed.setdefault(str(s["id"]), p.name)
                bound += 1
            else:
                print(f"{p.name:<36} sidecar points at id {meta.get('id')} which is GONE from the tenant")
            continue
        s, score = best_match(local_lines, deployed)
        if not s:
            print(f"{p.name:<36} nothing to match")
            continue
        kind, host = host_of(s)
        verdict = "ok" if score >= args.min_similarity else "REFUSED (below --min-similarity)"
        print(f"{p.name:<36} ~ \"{s['displayName']}\" (id {s['id']}, on {host}) "
              f"confidence {score:.2f}  {verdict}")
        if score < args.min_similarity:
            refused += 1
            continue
        if str(s["id"]) in claimed:
            print(f"   WARNING: id {s['id']} already claimed by {claimed[str(s['id'])]}; not binding")
            refused += 1
            continue
        claimed[str(s["id"])] = p.name
        if args.apply:
            write_sidecar(p, s)
            bound += 1
        else:
            pending += 1

    print(f"\n{bound} bound, {pending} would bind, {refused} refused")
    if pending and not args.apply:
        print("DRY RUN - re-run with --apply to write the sidecars.")
    return 0


def cmd_push(smip: Smip, args) -> int:
    d = folder(args)
    deployed = smip.scripts(with_source=True)
    by_id = {str(s["id"]): s for s in deployed}
    state = load_state(args)
    names = {n.lower() for n in args.name}
    print(f"{len(deployed)} script(s) in the tenant ({smip.base_url})\n")

    pushed = skipped = failed = 0
    staged: list[tuple[str, str]] = []
    for p in iter_sources(d):
        local_text = p.read_text(encoding="utf-8-sig")
        local = normalise(local_text)
        s, score, how = resolve(p, local, deployed, by_id)
        if how == "gone":
            print(f"{p.name}: sidecar points at a script that is GONE from the tenant. SKIPPED\n")
            skipped += 1
            continue
        if not s:
            print(f"{p.name}: no deployed script to match. SKIPPED\n")
            skipped += 1
            continue
        if names and (s.get("displayName") or "").lower() not in names:
            continue

        kind, host = host_of(s)
        remote = normalise(s.get("script"))
        if remote == local and not args.force:
            print(f"{p.name:<36} -> {s['displayName']:<30} up to date")
            continue

        print(f"{p.name}  ->  \"{s['displayName']}\"  (id {s['id']}, on {host}, "
              f"{s.get('outputType')}, disk {disk_name(s)})")
        if how == "content":
            print(f"  matched by CONTENT, confidence {score:.2f} - run `bind --apply` to pin this")
        if how == "content" and score < args.min_similarity:
            print(f"  REFUSED: below --min-similarity {args.min_similarity}. "
                  f"Overwriting the wrong script is unrecoverable.\n")
            skipped += 1
            continue
        changed = print_diff(remote, local, args.context)
        print(f"  {changed} changed line(s)")
        if not args.apply:
            print()
            continue

        try:
            b = backup(args, f"{s['id']}{p.suffix}", s.get("script") or "")
            when = datetime.now(timezone.utc).isoformat(timespec="seconds")
            body = stamped(local_text, when) if args.stamp else local_text
            result = smip.update_script(str(s["id"]), body)
            # Record the SERVER's timestamp: status compares server to server,
            # so a skewed local clock cannot fake a deploy.
            state[str(s["id"])] = {
                "name": s["displayName"],
                "file": p.name,
                "stagedAt": result.get("updatedTimestamp"),
                "stampedWith": when if args.stamp else None,
            }
            save_state(args, state)
            pushed += 1
            staged.append((str(s["id"]), s["displayName"]))
            print(f"  DB UPDATED - NOT YET LIVE (backup {b.name})")
            print(f"  deploy: open and Save -> {smip.ide_url(s['id'])}\n")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAILED: {exc}\n")

    verb = "staged" if args.apply else "would stage"
    print(f"{pushed if args.apply else '-'} {verb}, {skipped} skipped, {failed} failed")
    if staged:
        print("\nNOT LIVE YET. Scripts execute from disk; a database write does not "
              "manifest them.\nOpen each in the IDE and press Save:")
        for sid, name in staged:
            print(f"   {name:<30} {smip.ide_url(sid)}")
    if not args.apply:
        print("\nDRY RUN - nothing was written. Re-run with --apply.")
    return 1 if failed else 0


def cmd_status(smip: Smip, args) -> int:
    folder(args)
    state = load_state(args)
    if not state:
        print("Nothing staged. `push --apply` records what it stages.")
        return 0
    by_id = {str(s["id"]): s for s in smip.scripts(with_source=False)}
    pending = []
    print("%-30s %-26s %-26s %s" % ("script", "staged at", "tenant now", "state"))
    print("-" * 100)
    for sid, rec in sorted(state.items(), key=lambda kv: kv[1]["name"]):
        live = by_id.get(sid)
        if not live:
            print("%-30s GONE from the tenant" % rec["name"])
            continue
        now = live.get("updatedTimestamp") or ""
        saved = now > (rec.get("stagedAt") or "")
        if not saved:
            pending.append((sid, rec["name"]))
        print("%-30s %-26s %-26s %s" % (rec["name"], (rec.get("stagedAt") or "")[:26],
                                        now[:26], "live (inferred)" if saved else "NEEDS IDE SAVE"))
    if pending:
        print(f"\n{len(pending)} script(s) staged but NOT live. Open each and press Save:")
        for sid, name in pending:
            print(f"   {name:<30} {smip.ide_url(sid)}")
    else:
        print("\nAll staged scripts have been written since staging (inferred from write order).")
    return 0


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="smip_script_sync",
        description="Sync SMIP platform scripts between a project folder and a tenant.",
        epilog="A GraphQL write is NOT a deploy: open the script in the IDE and Save.")
    ap.add_argument("--config", help="Path to a VibeCon-style config.json.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, with_dir=True):
        if with_dir:
            p.add_argument("--dir", default=str(DEFAULT_DIR),
                           help=f"Local script folder (default {DEFAULT_DIR}).")
            p.add_argument("--state-dir", help=f"Where backups/state go (default <dir>/{STATE_DIRNAME}).")
        p.add_argument("--context", type=int, default=2, help="Diff context lines (default 2).")

    p = sub.add_parser("list", help="Inventory of the tenant's scripts.")
    add_scope_args(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("pull", help="Write deployed scripts into --dir with sidecars.")
    add_scope_args(p)
    common(p)
    p.add_argument("--force", action="store_true", help="Overwrite differing local files (backed up first).")
    p.add_argument("--dry-run", action="store_true", help="Show what would be written.")
    p.add_argument("--show-diff", action="store_true", help="Print the diff for differing files.")
    p.set_defaults(fn=cmd_pull)

    p = sub.add_parser("bind", help="Write <file>.smip.json sidecars by content match.")
    common(p)
    p.add_argument("--apply", action="store_true", help="Write sidecars. Default is dry run.")
    p.add_argument("--rebind", action="store_true", help="Re-match files that already have a sidecar.")
    p.add_argument("--min-similarity", type=float, default=0.60)
    p.set_defaults(fn=cmd_bind)

    p = sub.add_parser("push", help="Diff local files against the tenant; --apply stages them.")
    common(p)
    p.add_argument("--apply", action="store_true", help="Write to the tenant DB. Default is dry run.")
    p.add_argument("--name", action="append", default=[], help="Only this deployed displayName. Repeatable.")
    p.add_argument("--force", action="store_true", help="Stage even when bodies already match.")
    p.add_argument("--stamp", action="store_true", help="Inject a staging marker after <?php.")
    p.add_argument("--min-similarity", type=float, default=0.60,
                   help="Refuse content matches below this (default 0.60). Sidecar-bound files are exempt.")
    p.set_defaults(fn=cmd_push)

    p = sub.add_parser("status", help="Which staged scripts still need an IDE Save.")
    common(p)
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    smip = Smip(load_config(args.config))
    return args.fn(smip, args)


if __name__ == "__main__":
    raise SystemExit(main())
