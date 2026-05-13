# SMIP Exports

A drop folder for SMIP export JSON files. These exports are authoritative — they're what the SMIP database actually contains, in the format the SMIP itself reads back. Read them to ground claims about types, attributes, scripts, and instance shape rather than guessing from prose.

## Three ways to export

The SMIP IDE lets you export at three different levels of the model, each useful for a different workflow:

- **Instance-tree export** (off any node in the SoR). Captures the knowledge graph — how stuff actually sits in the system of record: parent/child containment, names and ids of the concrete instances under the chosen root, and the relationships between them. The ontology isn't directly stated (no subtype trees, no attribute-type definitions) but can be inferred from a well-populated instance tree. Worth noting that the types themselves don't constrain instance placement — there's no "PDUs may only live inside a PDU Collector" rule at the type level — so the instance tree is the only authoritative source for how a tenant has actually composed the model.
- **Library export.** A whole library at once — types (each with its display script), browser scripts, enumeration types, measurement units, and quantities. A library can also be entirely script-only: the `smip_js_sdk` library in the sibling folder is exactly that, no types, just scripts. That's the degenerate case of the same export, not a different file shape.
- **Single-type export.** One type on its own. The round-trip shortcut when you've just created or edited a type in the SMIP and want it back in the automation template — feed it to the Python class generator and the display-script scaffolder without re-exporting (or re-importing) the whole library.

All three use the same top-level JSON envelope; which sections come back populated depends on what was exported.