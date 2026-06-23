#!/usr/bin/env python3
"""
build_plugin.py — compile this repo's agent realm + operating guide into a
loadable Claude plugin (for Claude Code CLI or a Claude Desktop cowork session).

What it assembles, from the repo:
  .claude/agents/*.md   -> <plugin>/agents/*.md            (copied verbatim; the
                           frontmatter — name/description/tools/model — is already
                           plugin-compatible, so no transform is needed)
  CLAUDE.md             -> <plugin>/skills/operating-guide/SKILL.md
                           (plugins don't auto-load a CLAUDE.md memory file, so the
                           operating guide is shipped as a model-invocable skill)

It also emits a tiny marketplace wrapper so the plugin can be added straight into
Claude Desktop / Claude Code without publishing anything.

Output layout (under Artifacts/, which is gitignored):

    Artifacts/<marketplace>/
      .claude-plugin/marketplace.json          # lets `/plugin marketplace add` find it
      <plugin>/
        .claude-plugin/plugin.json             # the manifest (only `name` is required)
        agents/*.md                            # the four realm subagents
        skills/operating-guide/SKILL.md        # CLAUDE.md, as a skill

Load it (Claude Desktop or CLI):
    /plugin marketplace add <abs path to Artifacts/<marketplace>>
    /plugin install <plugin>@<marketplace>
Or, CLI dev loop, skip the marketplace:
    claude --plugin-dir <abs path to Artifacts/<marketplace>/<plugin>>

Run:
    python build_plugin.py                 # build into Artifacts/
    python build_plugin.py --zip           # also produce a .zip you can hand off
    python build_plugin.py --name foo --version 0.2.0
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent

# Defaults derived from the repo (see CLAUDE.md / README.md).
DEFAULT_PLUGIN_NAME = "vibecon-smip"
DEFAULT_MARKETPLACE = "vibecon-smip-marketplace"
DEFAULT_VERSION = "0.1.0"
DEFAULT_DESCRIPTION = (
    "VibeCon-SMIP realm agents + operating guide: a localhost-first automation "
    "template for the CESMII SMIP (ThinkIQ). One tool registry, four surfaces."
)

AGENTS_SRC = REPO / ".claude" / "agents"
CLAUDE_MD = REPO / "CLAUDE.md"


def git_author() -> dict:
    """Best-effort author block from git config; harmless if git is absent."""
    def cfg(key: str) -> str:
        try:
            out = subprocess.run(
                ["git", "config", "--get", key],
                cwd=REPO, capture_output=True, text=True, timeout=5,
            )
            return out.stdout.strip()
        except Exception:
            return ""

    author = {}
    if name := cfg("user.name"):
        author["name"] = name
    if email := cfg("user.email"):
        author["email"] = email
    return author or {"name": "VibeCon-SMIP"}


def collect_agents() -> list[Path]:
    if not AGENTS_SRC.is_dir():
        sys.exit(f"error: no agents directory at {AGENTS_SRC}")
    agents = sorted(AGENTS_SRC.glob("*.md"))
    if not agents:
        sys.exit(f"error: no agent .md files found in {AGENTS_SRC}")
    return agents


def write_agents(agents: list[Path], plugin_dir: Path) -> None:
    dst = plugin_dir / "agents"
    dst.mkdir(parents=True, exist_ok=True)
    for a in agents:
        # Verbatim copy — agent frontmatter is already plugin-compatible.
        shutil.copy2(a, dst / a.name)


def write_operating_guide(plugin_dir: Path, plugin_name: str) -> bool:
    """Wrap CLAUDE.md as a model-invocable skill. Returns False if CLAUDE.md absent."""
    if not CLAUDE_MD.is_file():
        return False
    body = CLAUDE_MD.read_text(encoding="utf-8")
    skill_dir = plugin_dir / "skills" / "operating-guide"
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = (
        "---\n"
        "name: operating-guide\n"
        "description: >-\n"
        f"  Operating guide and conventions for the {plugin_name} project (the repo's\n"
        "  CLAUDE.md): the realm map, run commands, and the safety rules for writing to\n"
        "  the SMIP system-of-record. Read this before working in this repo or routing\n"
        "  work to its realm agents.\n"
        "---\n\n"
    )
    (skill_dir / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")
    return True


def write_plugin_manifest(plugin_dir: Path, name: str, version: str,
                          description: str, author: dict) -> None:
    meta_dir = plugin_dir / ".claude-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "description": description,
        "author": author,
        "keywords": ["smip", "thinkiq", "cesmii", "automation", "agents"],
    }
    (meta_dir / "plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def write_marketplace(market_root: Path, marketplace_name: str, plugin_name: str,
                      description: str, author: dict) -> None:
    meta_dir = market_root / ".claude-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    marketplace = {
        "name": marketplace_name,
        "owner": author,
        "plugins": [
            {
                "name": plugin_name,
                "source": f"./{plugin_name}",
                "description": description,
            }
        ],
    }
    (meta_dir / "marketplace.json").write_text(
        json.dumps(marketplace, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", default=DEFAULT_PLUGIN_NAME, help="plugin name (kebab-case)")
    ap.add_argument("--marketplace", default=DEFAULT_MARKETPLACE, help="marketplace name")
    ap.add_argument("--version", default=DEFAULT_VERSION, help="plugin version")
    ap.add_argument("--description", default=DEFAULT_DESCRIPTION, help="plugin description")
    ap.add_argument("--out", default=str(REPO / "Artifacts"),
                    help="output base directory (default: Artifacts/)")
    ap.add_argument("--zip", action="store_true", help="also produce a .zip of the marketplace")
    args = ap.parse_args()

    out_base = Path(args.out).resolve()
    market_root = out_base / args.marketplace
    plugin_dir = market_root / args.name

    # Clean previous build of this marketplace, then rebuild.
    if market_root.exists():
        shutil.rmtree(market_root)
    plugin_dir.mkdir(parents=True, exist_ok=True)

    author = git_author()
    agents = collect_agents()
    write_agents(agents, plugin_dir)
    has_guide = write_operating_guide(plugin_dir, args.name)
    write_plugin_manifest(plugin_dir, args.name, args.version, args.description, author)
    write_marketplace(market_root, args.marketplace, args.name, args.description, author)

    print(f"Built plugin '{args.name}' -> {plugin_dir}")
    print(f"  agents : {len(agents)}  ({', '.join(a.stem for a in agents)})")
    print(f"  guide  : {'operating-guide skill (from CLAUDE.md)' if has_guide else 'SKIPPED — no CLAUDE.md'}")
    print(f"  market : {market_root / '.claude-plugin' / 'marketplace.json'}")

    if args.zip:
        zip_path = shutil.make_archive(str(market_root), "zip", root_dir=market_root)
        print(f"  zip    : {zip_path}")

    print("\nLoad it (Claude Desktop or Claude Code):")
    print(f'  /plugin marketplace add "{market_root}"')
    print(f"  /plugin install {args.name}@{args.marketplace}")
    print("Or, CLI dev loop:")
    print(f'  claude --plugin-dir "{plugin_dir}"')


if __name__ == "__main__":
    main()
