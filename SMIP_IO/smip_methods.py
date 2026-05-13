"""High-level SMIP operations (wraps a `SMIPClient`).

Keep transport/auth in `SMIPClient` and GraphQL operations here so the client
file can be reused as a template across projects.
"""

import json
import datetime
import re
from pathlib import Path

# SMIPClient is required for SMIPMethods to be useful at all, so import it
# eagerly. Try the package-mode path first, then the flat-mode fallback.
try:
    # Package-mode (e.g. `from SMIP_IO.smip_methods ...`)
    from .smip_client import SMIPClient
except ImportError:
    # Flat-mode (SMIP_IO itself on sys.path)
    from smip_client import SMIPClient                  # type: ignore


# Project root — used by file-writing tools like
# `export_type_to_smip_exports`. SMIP_IO/smip_methods.py lives one level
# below the repo root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _attribute_patch_parts(
    string_value=None,
    enumeration_value=None,
    object_value=None,
    bool_value=None,
    int_value=None,
    float_value=None,
    datetime_value=None,
):
    """Return a list of GraphQL patch field strings for updateAttribute.

    Raises TypeError if no value kwarg is supplied (mirrors the single-item
    update_attribute guard so callers catch it uniformly).
    """
    parts = []
    if string_value is not None:
        parts.append("stringValue: " + json.dumps(string_value))
    if enumeration_value is not None:
        parts.append("enumerationValue: " + json.dumps(enumeration_value))
    if object_value is not None:
        parts.append("objectValue: " + json.dumps(object_value))
    if bool_value is not None:
        parts.append("boolValue: " + json.dumps(bool_value))
    if int_value is not None:
        parts.append("intValue: " + json.dumps(int_value))
    if float_value is not None:
        parts.append("floatValue: " + json.dumps(float_value))
    if datetime_value is not None:
        parts.append("datetimeValue: " + json.dumps(datetime_value))
    if not parts:
        raise TypeError("at least one value kwarg is required")
    return parts


class SMIPMethods:
    """Higher-level SMIP operations (wraps a `SMIPClient`)."""

    def __init__(self, client: SMIPClient):
        self.client = client

    # ---------------------------------------------------------------------
    # Libraries — minimal smoke-test query. One GraphQL round-trip; no
    # parameters. Returns the bare `libraries` root field with id +
    # displayName so we can verify the SMIPClient + TOOL_REGISTRY +
    # MCP / Flask wiring end-to-end before adding anything domain-specific.
    # ---------------------------------------------------------------------
    def get_libraries(self):
        """Return every library in the SoR as a flat list of `{id, displayName}`
        dicts.

        Stub / smoke-test method — the GraphQL field shape may need to be
        widened (e.g. `relativeName`, `description`, `idPath`) once the
        project's library workflows are defined. For now this is a single
        round-trip with the minimum fields needed to confirm the plumbing
        works.

        One GraphQL round-trip:
            query GetLibraries {
              libraries { id displayName }
            }

        Returns: list of {id, displayName}.
        """
        query = "query GetLibraries { libraries { id displayName } }"
        resp = self.client.query(query)
        return ((resp or {}).get("data") or {}).get("libraries") or []

    # ---------------------------------------------------------------------
    # get_object_subtree — generic subtree fetch used by the display-script
    # playground's tree pane and any "show me everything under this node"
    # caller. Two GraphQL round-trips when called with FQN, one when called
    # with `root_id`. Returns a flat descendants list with `partOfId` on
    # every row so callers can fold into a tree client-side in one pass.
    # ---------------------------------------------------------------------
    def get_object_subtree(
        self,
        root_id: str = "",
        root_fqn: str = "",
    ):
        """Return the root object + a flat list of every descendant under it.

        Either `root_id` (digit string) OR `root_fqn` (dot-separated FQN
        like "thinkiq_system" or "thinkiq_system.applications") must be
        supplied. If both are passed `root_id` wins.

        The flat descendant list carries `partOfId` on every row, so
        callers can rebuild the tree client-side in one pass without
        further round-trips.

        Parameters
        ----------
        root_id : str, optional
            SMIP object id (digits only). Empty string => use root_fqn.
        root_fqn : str, optional
            Dot-separated FQN. Empty string => use root_id.

        Returns
        -------
        dict
            {
              "root": {                                # the subtree's root
                "id":          "<digits>",
                "displayName": "<...>",
                "fqn":         ["thinkiq_system", ..., "<leaf>"],
                "typeId":      "<digits>",
                "typeName":    "<relativeName>",
                "description": "<... | null>",
              },
              "descendants": [                          # strict descendants only
                {
                  "id", "displayName", "fqn",
                  "partOfId",                           # parent in the tree
                  "typeId", "typeName", "description",
                  "importance",                          # SoR sort key
                }, ...
              ],
            }

        Raises ValueError if neither root_id nor root_fqn is supplied,
        if root_id is non-digit, or if root_fqn cannot be resolved.

        Two GraphQL round-trips when called with FQN, one when called
        with `root_id`.
        """
        root_id = (root_id or "").strip()
        root_fqn = (root_fqn or "").strip()

        if root_id and not root_id.isdigit():
            raise ValueError("root_id must be a digit string")
        if not root_id and not root_fqn:
            raise ValueError("either root_id or root_fqn is required")

        # ---- 1. Resolve FQN -> id when needed ---------------------------
        if not root_id:
            fqn_list = [seg for seg in root_fqn.split(".") if seg]
            if not fqn_list:
                raise ValueError(
                    f"root_fqn is empty after splitting: {root_fqn!r}"
                )
            resolve_query = (
                "query ResolveByFqn { "
                "  objects(filter: { fqn: { equalTo: "
                + json.dumps(fqn_list) +
                " } }, first: 1) { "
                "    id displayName fqn typeId typeName description "
                "  } "
                "}"
            )
            resp = self.client.query(resolve_query)
            rows = ((resp or {}).get("data") or {}).get("objects") or []
            if not rows:
                raise ValueError(f"No object resolves to fqn {fqn_list}")
            root_obj = rows[0]
            root_id = root_obj["id"]
        else:
            root_obj = None  # filled in from descendants response below

        # ---- 2. Pull root + descendants by idPath contains --------------
        subtree_query = (
            "query GetSubtree { "
            "  objects(filter: { idPath: { contains: "
            + json.dumps(root_id) +
            " } }) { "
            "    id displayName fqn partOfId typeId typeName description importance "
            "  } "
            "}"
        )
        resp = self.client.query(subtree_query)
        rows = ((resp or {}).get("data") or {}).get("objects") or []

        # idPath: contains rootId returns the root itself + every descendant.
        # Split them.
        descendants = []
        for r in rows:
            if r.get("id") == root_id:
                if root_obj is None:
                    # Caller passed root_id directly; fill root_obj from this row.
                    root_obj = {
                        "id":          r.get("id"),
                        "displayName": r.get("displayName"),
                        "fqn":         r.get("fqn"),
                        "typeId":      r.get("typeId"),
                        "typeName":    r.get("typeName"),
                        "description": r.get("description"),
                    }
            else:
                descendants.append(r)

        if root_obj is None:
            # Root wasn't in the descendants result — can happen if the
            # idPath of the root itself doesn't include its own id (rare,
            # but defend against it). Fetch root directly.
            root_only_query = (
                "query GetRoot { "
                "  objects(condition: { id: " + json.dumps(root_id) + " }, first: 1) { "
                "    id displayName fqn typeId typeName description "
                "  } "
                "}"
            )
            resp = self.client.query(root_only_query)
            root_rows = ((resp or {}).get("data") or {}).get("objects") or []
            if not root_rows:
                raise ValueError(
                    f"Resolved root id {root_id} but no object found"
                )
            root_obj = root_rows[0]

        return {"root": root_obj, "descendants": descendants}

    # =====================================================================
    # Internal / automation-only methods.
    # Intentionally NOT registered in SMIP_MCP/smip_tools.py — these are
    # direct-call only (scripts, notebooks, batch jobs). Do not add
    # TOOL_REGISTRY entries or @mcp.tool wrappers for anything below.
    # =====================================================================

    def get_enum_type_by_display_name(self, filter_string: str = ""):
        """Return enumeration types whose displayName exactly equals
        `filter_string` — e.g. "CMMS Available Status".

        Internal / automation-only: not exposed via Flask or MCP. Used by
        scripts that need to resolve an enum type by name to its id, full
        enum value list, color codes, default values, etc.

        `filter_string` is REQUIRED and matched exactly (PostGraphile's
        `condition: { displayName: ... }` is an equality test). Empty
        input raises ValueError to stop accidental "list everything" calls.

        Returns a list of dicts (typically 0 or 1 element):
            [{
              "id", "displayName", "relativeName", "description",
              "fqn", "idPath",
              "enumerationNames", "enumerationColorCodes",
              "enumerationDescriptions", "defaultEnumerationValues",
            }, ...]

        One GraphQL round-trip:
            enumerationTypes(condition: { displayName: "<filter_string>" }) {
              id displayName relativeName description fqn idPath
              enumerationNames enumerationColorCodes enumerationDescriptions
              defaultEnumerationValues
            }
        """
        filter_string = (filter_string or "").strip()
        if not filter_string:
            raise ValueError(
                "filter_string is required (exact-match displayName)"
            )

        query = (
            "query GetEnumTypeByDisplayName { "
            "  enumerationTypes(condition: { displayName: "
            + json.dumps(filter_string) +
            " }) { "
            "    id displayName relativeName description fqn idPath "
            "    enumerationNames enumerationColorCodes enumerationDescriptions "
            "    defaultEnumerationValues "
            "  } "
            "}"
        )
        resp = self.client.query(query)
        return ((resp or {}).get("data") or {}).get("enumerationTypes") or []

    def get_type_by_display_name(self, filter_string: str = ""):
        """Return TiQ types whose displayName exactly equals `filter_string`.

        Internal / automation-only: not exposed via Flask or MCP. Used by
        scripts that need to resolve a type to its id / fqn / idPath for
        further drill-in (e.g. listing every record of a given type), and
        to read the type's attribute schema (`typeToAttributeTypes`) for
        migration / replacement workflows.

        `filter_string` is REQUIRED and matched exactly. Empty input
        raises ValueError.

        Returns a list of dicts (typically 0 or 1 element):
            [{
              "id", "displayName", "relativeName", "description",
              "fqn", "idPath",
              "typeToAttributeTypes": [
                {"id", "displayName", "dataType", "importance"}, ...
              ],
            }, ...]

        `dataType` is the SMIP scalar kind for that attribute slot —
        commonly "STRING" or "ENUMERATION" (others exist). When writing
        instances:
          - dataType == "STRING"      -> set stringValue
          - dataType == "ENUMERATION" -> set enumerationValue (also a
                                         string, e.g. "1")
        update_attribute() takes both as separate kwargs; pick based on
        the source attribute's dataType.

        `importance` is the SMIP-defined sort key (lower = more
        important / shown first). The slots come back unordered from
        the server — sort by `importance` client-side when display
        order matters.

        One GraphQL round-trip:
            tiqTypes(condition: { displayName: "<filter_string>" }) {
              id displayName relativeName description fqn idPath
              typeToAttributeTypes { id displayName dataType importance }
            }
        """
        filter_string = (filter_string or "").strip()
        if not filter_string:
            raise ValueError(
                "filter_string is required (exact-match displayName)"
            )

        query = (
            "query GetTypeByDisplayName { "
            "  tiqTypes(condition: { displayName: "
            + json.dumps(filter_string) +
            " }) { "
            "    id displayName relativeName description fqn idPath "
            "    typeToAttributeTypes { id displayName dataType importance } "
            "  } "
            "}"
        )
        resp = self.client.query(query)
        return ((resp or {}).get("data") or {}).get("tiqTypes") or []

    # ---------------------------------------------------------------------
    # Mutating internal methods. DESTRUCTIVE — they create / delete / modify
    # records in the SoR. Same internal-only contract as the lookups above:
    # NO TOOL_REGISTRY entries, NO @mcp.tool wrappers, NO Flask routes.
    # Direct-call only (scripts, notebooks, batch jobs). Treat with care —
    # a typo in a part_of_id can land an object in the wrong subtree, and
    # delete_object has no undo.
    # ---------------------------------------------------------------------

    def create_object(
        self,
        display_name: str,
        type_id: str,
        part_of_id: str,
        description: str = "",
    ):
        """Create an object under a parent. Internal / automation-only.

        DESTRUCTIVE: writes a new row to the SoR. There is no dry-run mode
        here — call site is responsible for validating inputs.

        Parameters
            display_name : the new object's displayName (required, trimmed)
            type_id      : TiQ type id (digits-only string). Resolve from a
                           name with get_type_by_display_name first.
            part_of_id   : parent object id (digits-only string) — where in
                           the tree this object is mounted.
            description  : optional free-text description. Empty string is
                           sent through as-is so the SoR field is set.

        All three required fields must be non-empty. `type_id` and
        `part_of_id` must be digits — display names are NOT accepted.

        Returns the `object` payload of the mutation (id, displayName,
        typeId, partOfId, attributes), or None if the server returned no
        object (treat that as a failed create and inspect the response).

        One GraphQL round-trip:
            mutation CreateObject {
              createObject(input: { object: {
                displayName: "<display_name>"
                description: "<description>"
                typeId:      "<type_id>"
                partOfId:    "<part_of_id>"
              } }) {
                clientMutationId
                object {
                  id displayName typeId partOfId
                  attributes { id displayName }
                }
              }
            }
        """
        display_name = (display_name or "").strip()
        type_id      = (type_id or "").strip()
        part_of_id   = (part_of_id or "").strip()
        description  = description or ""   # allow empty; do NOT strip user spaces

        if not display_name:
            raise ValueError("display_name is required")
        if not type_id or not type_id.isdigit():
            raise ValueError(
                f"type_id must be a node id (digits only); got {type_id!r}"
            )
        if not part_of_id or not part_of_id.isdigit():
            raise ValueError(
                f"part_of_id must be a node id (digits only); got {part_of_id!r}"
            )

        mutation = (
            "mutation CreateObject { "
            "  createObject(input: { object: { "
            "    displayName: " + json.dumps(display_name) + " "
            "    description: " + json.dumps(description)  + " "
            "    typeId: \""    + type_id    + "\" "
            "    partOfId: \""  + part_of_id + "\" "
            "  } }) { "
            "    clientMutationId "
            "    object { "
            "      id displayName typeId partOfId "
            "      attributes { id displayName } "
            "    } "
            "  } "
            "}"
        )
        resp = self.client.query(mutation, op_type="mutation")
        payload = ((resp or {}).get("data") or {}).get("createObject") or {}
        return payload.get("object")

    def delete_object(self, object_id: str):
        """Delete an object by id. Internal / automation-only.

        DESTRUCTIVE and IRREVERSIBLE: the SoR row is removed. There is no
        soft-delete here. Verify the id before calling.

        `object_id` is REQUIRED and must be digits. Display names are NOT
        accepted.

        Returns the `deleteObject` payload (typically just
        `{"clientMutationId": null}`). Errors from the server propagate up
        as exceptions from SMIPClient.

        One GraphQL round-trip:
            mutation DeleteObject {
              deleteObject(input: { id: "<object_id>" }) {
                clientMutationId
              }
            }
        """
        object_id = (object_id or "").strip()
        if not object_id or not object_id.isdigit():
            raise ValueError(
                f"object_id must be a node id (digits only); got {object_id!r}"
            )

        mutation = (
            "mutation DeleteObject { "
            "  deleteObject(input: { id: \"" + object_id + "\" }) { "
            "    clientMutationId "
            "  } "
            "}"
        )
        resp = self.client.query(mutation, op_type="mutation")
        return ((resp or {}).get("data") or {}).get("deleteObject") or {}

    def update_attribute(
        self,
        attribute_id: str,
        string_value=None,
        enumeration_value=None,
    ):
        """Update an attribute by id. Internal / automation-only.

        DESTRUCTIVE: overwrites the attribute's existing value(s). At
        least one of `string_value` / `enumeration_value` must be supplied
        (None means "leave that field alone"; "" means "set the field to
        empty string").

        Parameters
            attribute_id      : attribute id (digits-only string).
            string_value      : new stringValue, or None to leave unchanged.
            enumeration_value : new enumerationValue, or None to leave
                                unchanged. THIS IS NOT AN ARRAY INDEX —
                                it's the stored value defined on the enum
                                type.

        Returns the `attribute` payload of the mutation (id, displayName,
        stringValue, enumerationName), or None if the server returned no
        attribute.

        One GraphQL round-trip:
            mutation UpdateAttribute {
              updateAttribute(input: {
                id: "<attribute_id>"
                patch: { stringValue: "...", enumerationValue: "..." }
              }) {
                clientMutationId
                attribute { id displayName stringValue enumerationName }
              }
            }
        """
        attribute_id = (attribute_id or "").strip()
        if not attribute_id or not attribute_id.isdigit():
            raise ValueError(
                f"attribute_id must be a node id (digits only); "
                f"got {attribute_id!r}"
            )
        if string_value is None and enumeration_value is None:
            raise ValueError(
                "at least one of string_value / enumeration_value is required"
            )

        patch_parts = []
        if string_value is not None:
            patch_parts.append("stringValue: " + json.dumps(string_value))
        if enumeration_value is not None:
            patch_parts.append("enumerationValue: " + json.dumps(enumeration_value))
        patch_str = "{ " + ", ".join(patch_parts) + " }"

        mutation = (
            "mutation UpdateAttribute { "
            "  updateAttribute(input: { "
            "    id: \"" + attribute_id + "\" "
            "    patch: " + patch_str + " "
            "  }) { "
            "    clientMutationId "
            "    attribute { "
            "      id displayName stringValue enumerationName "
            "    } "
            "  } "
            "}"
        )
        resp = self.client.query(mutation, op_type="mutation")
        payload = ((resp or {}).get("data") or {}).get("updateAttribute") or {}
        return payload.get("attribute")

    def update_attributes(self, items: list):
        """Batch update N attributes in a SINGLE GraphQL round-trip.

        DESTRUCTIVE: overwrites each attribute's existing value(s). There is
        no dry-run mode — validate inputs at the call site.

        Parameters
        ----------
        items : list of (attribute_id, kwargs) tuples
            Each entry is ``(attribute_id: str, value_kwargs: dict)`` where
            `value_kwargs` accepts the same kwargs as ``_attribute_patch_parts``:
            ``string_value``, ``enumeration_value``, ``object_value``,
            ``bool_value``, ``int_value``, ``float_value``, ``datetime_value``.
            At least one value kwarg must be non-None per item.

        Returns
        -------
        list
            One entry per input item (same order). Each entry is the
            ``attribute`` payload dict ``{id, displayName, stringValue,
            enumerationName, objectValue, boolValue, intValue, floatValue,
            datetimeValue}``, or ``None`` if the server returned no attribute
            for that alias.

        Raises ValueError on malformed items, non-digit attribute ids, or
        invalid kwargs.

        One GraphQL round-trip (N aliased updateAttribute operations):
            mutation UpdateAttributesBatch {
              m0: updateAttribute(input: { id: "…" patch: {…} }) { … }
              m1: updateAttribute(input: { id: "…" patch: {…} }) { … }
              …
            }
        """
        if not items:
            return []
        prepared = []
        for idx, item in enumerate(items):
            try:
                attribute_id, value_kwargs = item
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"items[{idx}] must be a (attribute_id, kwargs) tuple; got {item!r}"
                ) from exc
            if not isinstance(value_kwargs, dict):
                raise ValueError(f"items[{idx}] kwargs must be a dict; got {value_kwargs!r}")
            attribute_id = (str(attribute_id) or "").strip()
            if not attribute_id or not attribute_id.isdigit():
                raise ValueError(
                    f"items[{idx}].attribute_id must be a node id; got {attribute_id!r}"
                )
            try:
                patch_parts = _attribute_patch_parts(**value_kwargs)
            except TypeError as exc:
                raise ValueError(f"items[{idx}] kwargs invalid: {exc}") from exc
            patch_str = "{ " + ", ".join(patch_parts) + " }"
            prepared.append((attribute_id, patch_str))
        op_blocks = []
        for idx, (attribute_id, patch_str) in enumerate(prepared):
            op_blocks.append(
                f"  m{idx}: updateAttribute(input: {{ id: \"{attribute_id}\" patch: {patch_str} }}) {{ "
                f"clientMutationId attribute {{ id displayName "
                f"stringValue enumerationName objectValue "
                f"boolValue intValue floatValue datetimeValue }} }}"
            )
        mutation = "mutation UpdateAttributesBatch { " + " ".join(op_blocks) + " }"
        resp = self.client.query(mutation, op_type="mutation")
        data = (resp or {}).get("data") or {}
        results = []
        for idx in range(len(prepared)):
            alias_payload = data.get(f"m{idx}") or {}
            results.append(alias_payload.get("attribute"))
        return results

    # ---------------------------------------------------------------------
    # export_type_to_smip_exports — pull a tiqType's payload via GraphQL
    # and write it as JSON into ___SMIP_SAAS_SIDE___/SMIP Exports/<fqn>.json.
    # The playground's right-pane Export button calls this; the same tool
    # is useful from SCRIPTS/ for capturing type state into source control.
    #
    # This is a pragmatic dump, not a byte-faithful replica of SMIP's
    # native export format (which also pulls related libraries, relationship
    # types, etc.). For the round-trip use case — "I changed a type's
    # scripts in the IDE, drop the new state into source control" — this
    # captures the fields that matter and skips the rest. Extend the
    # `_EXPORT_TYPE_FIELDS` literal when more fidelity is needed.
    # ---------------------------------------------------------------------
    _EXPORT_TYPE_FIELDS = (
        "id displayName relativeName description importance fqn"
    )

    def export_type_to_smip_exports(self, type_id: str = ""):
        """Export a single tiqType's JSON into `___SMIP_SAAS_SIDE___/SMIP Exports/`.

        DESTRUCTIVE on the local filesystem only (overwrites the target file
        if it already exists). Does not mutate anything in the SoR.

        Parameters
        ----------
        type_id : str
            tiqType id (digits only). Resolve from a display name via
            `get_type_by_display_name` if needed.

        Returns
        -------
        dict
            {
              "path":    "<absolute path of the written file>",
              "fqn":     ["<library>", "<type>"],
              "bytes":   <int — file size after write>,
            }

        One GraphQL round-trip:
            tiqTypes(condition: { id: "<type_id>" }, first: 1) {
              <_EXPORT_TYPE_FIELDS>
            }

        Errors
        ------
        ValueError if type_id is missing / non-digit, or if no type
        resolves to the given id. RuntimeError if the
        ___SMIP_SAAS_SIDE___/SMIP Exports/ folder can't be created.
        """
        type_id = (type_id or "").strip()
        if not type_id or not type_id.isdigit():
            raise ValueError(
                f"type_id must be a node id (digits only); got {type_id!r}"
            )

        query = (
            "query ExportType { "
            "  tiqTypes(condition: { id: " + json.dumps(type_id) + " }, first: 1) { "
            "    " + self._EXPORT_TYPE_FIELDS + " "
            "  } "
            "}"
        )
        resp = self.client.query(query)
        rows = ((resp or {}).get("data") or {}).get("tiqTypes") or []
        if not rows:
            raise ValueError(f"No type resolves to id {type_id!r}")
        type_row = rows[0]

        fqn = type_row.get("fqn") or []
        # Filename: dot-joined fqn segments + .json. Sanitize for filesystem
        # safety (the SoR-side validator already rejects most exotic chars,
        # but a defensive substitution costs nothing).
        if fqn:
            stem = ".".join(fqn)
        else:
            stem = f"type_{type_id}"
        safe_stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem) or f"type_{type_id}"
        filename = safe_stem + ".json"

        exports_dir = _PROJECT_ROOT / "___SMIP_SAAS_SIDE___" / "SMIP Exports"
        try:
            exports_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Could not create exports dir: {e}") from e

        # Compose the file payload. Header `meta` borrows the shape of
        # SMIP's native export so anyone opening the file can tell at a
        # glance what it is, when it was written, and which type it
        # captures.
        payload = {
            "meta": {
                "file_version":   "0.1",
                "exporter":       "vibecon-smip / SMIPMethods.export_type_to_smip_exports",
                "export_node_fqn": fqn,
                "export_timestamp": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "note": (
                    "Pragmatic single-type export. Not byte-faithful to "
                    "SMIP's native multi-type / library export format. "
                    "Extend SMIPMethods._EXPORT_TYPE_FIELDS to widen."
                ),
            },
            "types": [type_row],
        }

        out_path = exports_dir / filename
        out_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        return {
            "path":  str(out_path),
            "fqn":   fqn,
            "bytes": out_path.stat().st_size,
        }


__all__ = ["SMIPMethods"]
