# Workspace Molecular Preview

### MOL-001: Molecular structure view

- Files offers Molecular structure beside Rich and Plain; existing conversations default to Rich.
- The existing conversation-scoped view preference accepts and restores `molecular`.
- Structure mode reads the selected file through the existing workspace-content query on Local and Cloud; opening a workspace structure introduces no backend API or upload to a third party.
- Mol* loads only when viewing a supported text structure in molecular mode. Supported extensions are XYZ, CIF, mmCIF / MCIF, PDB / ENT, MOL, SDF / SD and MOL2, case-insensitively.
- Unsupported and binary files show supported formats and explain switching back to Rich / Plain. Text modes retain their existing behavior.

### MOL-002: Viewer ownership and interaction

- Start with a ball-and-stick representation colored by chemical element, with native drag rotation, scroll zoom, right-drag pan and camera controls.
- Show localized loading and failure states. Initialization/parse failure offers Retry and suggests inspecting Plain text or checking WebGL.
- Recreate the viewer when the path or file contents change. Resize the canvas with the panel, and dispose owned resources on switching modes/files or unmount.
- Ignore stale async completion/failure after the previous file is abandoned. Detach its owned viewport immediately and dispose after in-flight tasks settle; retain each canvas's parent through Mol* input cleanup.
- Unmount the owned Mol* React root and restore page styles/fullscreen state before disposing an expanded viewer.
- Expanded mode moves the same viewport into a body-level CSS-scoped host, outside transformed file panels. Native collapse and Escape return it to its original pane; cleanup removes the host.

### MOL-003: Scientific format handling

- Parse actual file bytes with Mol*; reject empty structures and non-finite atomic coordinates.
- Detect crystal CIF versus mmCIF from its contents. Convert fractional coordinates through Mol*, expand crystal symmetry in one unit cell, and draw the unit-cell outline.
- Preserve the parsed trajectory and register an all-atoms component with the structure hierarchy. Molecular files initially show the first model; Mol* trajectory controls can switch frames without combining them.
- Opening a workspace structure does not require downloading it or its coordinates from external sources. The full Viewer's explicit external-data tools remain available.

### MOL-004: Full Mol* Viewer

- Use the official Viewer spec, default behaviors, animations and extensions, including the structure tools, selection, measurements, representations/colors, sequence view, trajectory controls, snapshots, screenshots, and model/animation/geometry exports.
- Keep controls interactive and accessible inside a named region, rather than exposing the whole interactive viewer as an image.
- Scope the upstream Mol* stylesheet inside the Canvas shell and preserve lazy loading. Keep the cyclic Mol* modules in the existing `vendor-molstar` chunk.
- Use the portrait layout in narrow embedded panes and the landscape layout in sufficiently wide panes. Native expansion opens the full-page layout; returning restores a usable embedded layout.
- Let the native Viewer occupy the preview area without an additional EM-Agent toolbar or footer note; reset and expansion use the native controls.
- Native Mol* controls retain their upstream labels; EM-Agent wrapper labels and errors use the application's locale.
