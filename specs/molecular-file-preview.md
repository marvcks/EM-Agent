# Workspace Molecular Preview

### MOL-001: Molecular structure view

- Files offers Molecular structure beside Rich and Plain; existing conversations default to Rich.
- The existing conversation-scoped view preference accepts and restores `molecular`.
- Structure mode reads the selected file through the existing workspace-content query on Local and Cloud; it introduces no backend API or file upload to a third party.
- Mol* loads only when viewing a supported text structure in molecular mode. Supported extensions are XYZ, CIF, mmCIF / MCIF, PDB / ENT, MOL, SDF / SD and MOL2, case-insensitively.
- Unsupported and binary files show supported formats and explain switching back to Rich / Plain. Text modes retain their existing behavior.

### MOL-002: Viewer ownership and interaction

- Use a ball-and-stick representation colored by chemical element, with drag rotation, scroll zoom, right-drag pan, and Reset view.
- Show localized loading and failure states. Initialization/parse failure offers Retry and suggests inspecting Plain text or checking WebGL.
- Recreate the viewer when the path or file contents change. Resize the canvas with the panel, and dispose owned resources on switching modes/files or unmount.
- Ignore stale async completion/failure after the previous file is abandoned. Detach its canvas immediately and dispose its state after in-flight initialization/parsing settles.

### MOL-003: Scientific format handling

- Parse the actual file bytes with Mol*; reject empty structures and non-finite atomic coordinates.
- Detect crystal CIF versus mmCIF from its contents. Convert fractional coordinates through Mol*, expand crystal symmetry in one unit cell, and draw the unit-cell outline.
- Molecular files preserve the first model's coordinates. Multi-model files show the first structure only, explicitly indicated in the viewer footer.
- Do not enable remote annotation or download behaviors for workspace previews.
