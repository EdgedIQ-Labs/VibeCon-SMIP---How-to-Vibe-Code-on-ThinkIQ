#!/usr/bin/env python3
"""Build smip_js_sdk_library_export.json from the local source files.

Run from inside the SMIP JS SDK folder:

    python3 makeExportJson.py

Reads the four script templates from disk (`00 Guzzle Client.php`,
`01 API Template.php`, `02 API Tools.html`, `03 API Documentation.html`),
wraps them in the SMIP library export envelope (CRLF-encoded script
bodies, fixed metadata, neutral timestamps), and writes
`smip_js_sdk_library_export.json` next to them.

Use this when the on-disk script bodies have evolved and you want a
refreshed library export to import into a SMIP. The output is
byte-deterministic given identical input files, so all three project
copies of the SMIP JS SDK folder end up with the same JSON when the
sources are in sync.

This is a substitute for re-exporting from the SMIP IDE — useful for
git-friendly workflows where the JSON is checked in and you want the
embedded script bodies to track what's on disk without a SMIP
round-trip. The IDE re-export is still authoritative when SMIP
metadata (file_version, schema_version, owner) drifts; refresh the
constants below to match a fresh IDE export when that happens.
"""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# relative_name → on-disk filename. The numeric prefixes on disk keep
# the files in alphabetical view order; the SMIP relative_name is
# unprefixed and uses underscores.
SCRIPTS = {
    "guzzle_client":     "00 Guzzle Client.php",
    "api_template":      "01 API Template.php",
    "api_tools":         "02 API Tools.html",
    "api_documentation": "03 API Documentation.html",
}

# Per-script metadata. Values match what the SMIP IDE writes when you
# export a freshly-imported library. Refresh if the IDE shape changes.
SCRIPT_META = {
    "guzzle_client": {
        "display_name": "Guzzle Client",
        "script_type":  "php",
        "output_type":  "headless",
    },
    "api_template": {
        "display_name": "API Template",
        "script_type":  "php",
        "output_type":  "headless",
    },
    "api_tools": {
        "display_name": "API Tools",
        "script_type":  "php",
        "output_type":  "browser",
    },
    "api_documentation": {
        "display_name": "API Documentation",
        "script_type":  "php",
        "output_type":  "browser",
    },
}

# Stable neutral timestamp. Same value for every rebuild so the output
# is byte-deterministic across the three project copies when sources
# match. Bump when you want a new "version" of the export.
NEUTRAL_TS = "2026-05-08T00:00:00.000000+00:00"

# Library version. Bump on substantive API changes (added / removed
# methods, signature changes, etc.) so a SMIP that's already imported
# the library can tell something changed.
LIBRARY_VERSION = "1.1.0"

LIBRARY_DESCRIPTION = (
    "SMIP JS SDK - generic, tenant-agnostic apiDemoMethods helpers + "
    "descriptors. Two mutations (updateAttribute, updateObject) and "
    "three queries (getTypes, getObject, getEnumTypes) wrap the common "
    "SMIP / PostGraphile surface. Common code; tenant-agnostic. See "
    "README.md for full docs."
)


def crlf(text: str) -> str:
    """Normalize to LF then encode as CRLF — matches SMIP's export format."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def build_script_template(rel_name: str) -> dict:
    body = (HERE / SCRIPTS[rel_name]).read_text(encoding="utf-8")
    meta = SCRIPT_META[rel_name]
    return {
        "fqn": ["smip_js_sdk", rel_name],
        "run": False,
        "owner": "smip-advanced-topics",
        "script": crlf(body),
        "document": {"template": False},
        "importance": None,
        "description": None,
        "edit_status": 1,
        "output_type": meta["output_type"],
        "script_type": meta["script_type"],
        "display_name": meta["display_name"],
        "relative_name": rel_name,
        "initial_inputs": {
            "start_timestamp": "2026-05-04T00:00:00.000000+00:00",
            "interval_seconds": "60",
        },
        "cron_expression": "0 * * * * ? *",
        "exec_on_derived": False,
        "updated_timestamp": NEUTRAL_TS,
        "max_acceptable_run_secs": 0,
        "use_outputs_from_last_run": False,
    }


def build_envelope() -> dict:
    return {
        "meta": {
            "file_version": "4.0.2",
            "database_name": "smip_js_sdk",
            "export_timestamp": NEUTRAL_TS,
            "export_library_fqn": ["smip_js_sdk"],
            "database_schema_version": "4.16.5",
        },
        "types": [],
        "objects": [],
        "libraries": [
            {
                "fqn": ["smip_js_sdk"],
                "locked": False,
                "models": None,
                "aliases": None,
                "version": LIBRARY_VERSION,
                "document": None,
                "licensing": None,
                "extensions": None,
                "importance": None,
                "description": LIBRARY_DESCRIPTION,
                "edit_status": 1,
                "server_uris": None,
                "display_name": "SMIP JS SDK",
                "relative_name": "smip_js_sdk",
                "namespace_uris": None,
                "updated_timestamp": NEUTRAL_TS,
                "unlink_relative_name": False,
            }
        ],
        "quantities": [],
        "relationships": [],
        "opcua_variables": [],
        "opcua_data_types": [],
        "script_templates": [
            build_script_template(rn) for rn in sorted(SCRIPTS.keys())
        ],
        "enumeration_types": [],
        "measurement_units": [],
        "relationship_types": [],
        "opcua_variable_types": [],
        "opcua_reference_types": [],
        "md5_checksum": None,
    }


def main() -> int:
    missing = [fn for rn, fn in SCRIPTS.items() if not (HERE / fn).is_file()]
    if missing:
        sys.stderr.write(f"Missing source files in {HERE}:\n")
        for fn in missing:
            sys.stderr.write(f"  - {fn}\n")
        return 1

    envelope = build_envelope()
    serialized = json.dumps(envelope, indent=4, ensure_ascii=False)
    out_path = HERE / "smip_js_sdk_library_export.json"
    out_path.write_text(serialized, encoding="utf-8", newline="\n")

    md5 = hashlib.md5(serialized.encode("utf-8")).hexdigest()
    print(f"Wrote {out_path}")
    print(f"  bytes: {len(serialized)}")
    print(f"  md5:   {md5}")
    print(f"  scripts embedded: {', '.join(sorted(SCRIPTS.keys()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
