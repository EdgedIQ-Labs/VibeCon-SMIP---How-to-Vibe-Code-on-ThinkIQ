"""Shared tool definitions consumed by every SMIP agent / doc surface.

Single source of truth for:
  * MCP tool descriptions    (smip_mcp_server.py)
  * OpenAI tool schemas      (SMIP_API/smip_flask_api.py /api/chat)
  * Generic HTTP dispatch    (SMIP_API/smip_flask_api.py /api/tool/<name>)
  * Python IDE docstrings    (SMIP_IO/smip_methods.py)

Adding a new SMIPMethods tool:
1. Add an entry to TOOL_REGISTRY below.
2. Add a typed @mcp.tool() wrapper in smip_mcp_server.py (3 lines).
Everything else is derived.
"""

from __future__ import annotations


TOOL_REGISTRY = [
    {
        "name": "get_libraries",
        "summary": "Return every library as a {id, displayName} row. No parameters. Smoke-test query.",
        "description": (
            "Return every library in the SoR as a flat list of "
            "{id, displayName} dicts.\n\n"
            "Smoke-test tool. One GraphQL round-trip:\n"
            "  query GetLibraries { libraries { id displayName } }\n\n"
            "Returns: list of {id, displayName}."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
        "ui": {"inputs": []},
        "fn": lambda m, a: m.get_libraries(),
    },
    {
        "name": "get_object_subtree",
        "summary": (
            "Return root object + flat descendants list. "
            "Pass root_fqn (e.g. 'thinkiq_system') or root_id."
        ),
        "description": (
            "Return the root object + a flat list of every descendant "
            "under it. Either root_id (digits) OR root_fqn (dot-separated, "
            "e.g. 'thinkiq_system') must be supplied; root_id wins if both "
            "are passed.\n\n"
            "The flat descendant list carries partOfId on every row so "
            "callers can rebuild the tree client-side in one pass.\n\n"
            "Returns: {root: {...}, descendants: [...]}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "root_id":  {"type": "string", "description": "SMIP object id (digits)."},
                "root_fqn": {"type": "string", "description": "Dot-separated FQN."},
            },
            "required": [],
        },
        "ui": {
            "inputs": [
                {"param": "root_fqn", "kind": "text", "label": "Root FQN",
                 "placeholder": "thinkiq_system"},
                {"param": "root_id",  "kind": "text", "label": "Root id (alternative)"},
            ],
        },
        "fn": lambda m, a: m.get_object_subtree(
            root_id=a.get("root_id", ""),
            root_fqn=a.get("root_fqn", ""),
        ),
        "llm_exposed": False,
    },
    {
        "name": "update_attribute",
        "summary": (
            "Update one attribute by id. Pass attribute_id plus at least "
            "one of string_value / enumeration_value. DESTRUCTIVE."
        ),
        "description": (
            "DESTRUCTIVE - overwrites the attribute's existing value(s).\n\n"
            "Pass attribute_id (digits) and at least one of string_value / "
            "enumeration_value. Empty string is a real value (clears the "
            "field); None means leave the field alone.\n\n"
            "Returns: {id, displayName, stringValue, enumerationName} or None."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "attribute_id":      {"type": "string", "description": "Attribute id (digits)."},
                "string_value":      {"type": "string", "description": "New stringValue."},
                "enumeration_value": {"type": "string", "description": "New enumerationValue."},
            },
            "required": ["attribute_id"],
        },
        "ui": {
            "inputs": [
                {"param": "attribute_id",      "kind": "text", "label": "Attribute id"},
                {"param": "string_value",      "kind": "text", "label": "String value"},
                {"param": "enumeration_value", "kind": "text", "label": "Enumeration value"},
            ],
        },
        "fn": lambda m, a: m.update_attribute(
            attribute_id=a.get("attribute_id", ""),
            string_value=a.get("string_value"),
            enumeration_value=a.get("enumeration_value"),
        ),
        "llm_exposed": False,
    },
    {
        "name": "export_type_to_smip_exports",
        "summary": (
            "Export one tiqType to ___SMIP_SAAS_SIDE___/SMIP Exports/<fqn>.json. "
            "Writes a local file; does NOT mutate the SoR."
        ),
        "description": (
            "Pull a tiqType's payload via GraphQL and write it as JSON to "
            "___SMIP_SAAS_SIDE___/SMIP Exports/<fqn>.json.\n\n"
            "Pragmatic dump, not byte-faithful to SMIP's multi-type export.\n\n"
            "Returns: {path, fqn, bytes}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type_id": {"type": "string", "description": "tiqType id (digits)."},
            },
            "required": ["type_id"],
        },
        "ui": {
            "inputs": [
                {"param": "type_id", "kind": "text", "label": "Type id (digits)"},
            ],
        },
        "fn": lambda m, a: m.export_type_to_smip_exports(
            type_id=a.get("type_id", ""),
        ),
        "llm_exposed": False,
    },
]


def _pascal(snake: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in snake.split("_") if p)


OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["parameters"],
        },
    }
    for t in TOOL_REGISTRY
    if t.get("llm_exposed", True)
]


TOOL_REGISTRY_PUBLIC = [
    {
        "name": t["name"],
        "display_name": _pascal(t["name"]),
        "summary": t["summary"],
        "description": t["description"],
        "parameters": t["parameters"],
        "ui": t["ui"],
        "llm_exposed": t.get("llm_exposed", True),
    }
    for t in TOOL_REGISTRY
]


def make_dispatch(methods: object) -> dict:
    return {
        t["name"]: (lambda args, fn=t["fn"]: fn(methods, args))
        for t in TOOL_REGISTRY
    }


def attach_docstrings_to(cls: type) -> None:
    for t in TOOL_REGISTRY:
        method = getattr(cls, t["name"], None)
        if callable(method):
            try:
                method.__doc__ = t["description"]
            except (AttributeError, TypeError):
                pass


__all__ = [
    "TOOL_REGISTRY",
    "TOOL_REGISTRY_PUBLIC",
    "OPENAI_TOOLS",
    "make_dispatch",
    "attach_docstrings_to",
]
