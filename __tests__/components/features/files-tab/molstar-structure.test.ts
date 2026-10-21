import { afterEach, describe, expect, it, vi } from "vitest";
import { PluginContext } from "molstar/lib/mol-plugin/context";
import { loadMolecularStructure } from "#/components/features/files-tab/molstar-structure";

import { createMolstarViewer } from "#/components/features/files-tab/molstar-viewer";

// The video encoder installs Node process rejection handlers on import. It is
// a browser/WASM platform service; parser and WebGL-error tests do not encode.
vi.mock("h264-mp4-encoder", () => ({}));

const WATER_XYZ = "3\nwater\nO 0 0 0\nH 0.76 0 0.59\nH -0.76 0 0.59\n";
const WATER_MOL = `water
  EM-Agent

  3  2  0  0  0  0            999 V2000
    0.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    0.7600    0.0000    0.5900 H   0  0  0  0  0  0  0  0  0  0  0  0
   -0.7600    0.0000    0.5900 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0  0  0  0
  1  3  1  0  0  0  0
M  END
`;
const WATER_MOL2 = `@<TRIPOS>MOLECULE
water
3 2 1 0 0
SMALL
NO_CHARGES
@<TRIPOS>ATOM
1 O 0 0 0 O.3 1 WAT 0
2 H 0.76 0 0.59 H 1 WAT 0
3 H -0.76 0 0.59 H 1 WAT 0
@<TRIPOS>BOND
1 1 2 1
2 1 3 1
`;
const WATER_PDB = `HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O
HETATM    2  H1  HOH A   1       0.760   0.000   0.590  1.00  0.00           H
HETATM    3  H2  HOH A   1      -0.760   0.000   0.590  1.00  0.00           H
END
`;
const WATER_MMCIF = `data_water
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_entity_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.occupancy
_atom_site.auth_asym_id
_atom_site.auth_seq_id
HETATM 1 O O HOH A 1 1 0 0 0 1 A 1
HETATM 2 H H1 HOH A 1 1 0.76 0 0.59 1 A 1
HETATM 3 H H2 HOH A 1 1 -0.76 0 0.59 1 A 1
`;
const CRYSTAL_CIF = `data_crystal
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P -1'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
'-x,-y,-z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0.1 0.2 0.3
`;

const plugins: PluginContext[] = [];
async function parse(path: string, text: string) {
  const plugin = new PluginContext({ behaviors: [] });
  plugins.push(plugin);
  await plugin.init();
  return loadMolecularStructure(plugin, path, text);
}

afterEach(() => {
  plugins.splice(0).forEach((plugin) => plugin.dispose());
});

// @spec MOL-003 — Scientific file formats use real Mol* parsers, without WebGL
describe("workspace molecular structure parsing", () => {
  it.each([
    ["water.XYZ", WATER_XYZ],
    ["water.mol", WATER_MOL],
    ["water.sdf", WATER_MOL + "$$$$\n"],
    ["water.mol2", WATER_MOL2],
    ["water.pdb", WATER_PDB],
    ["water.mmcif", WATER_MMCIF],
    ["water.cif", WATER_MMCIF],
  ])("loads atoms and coordinates from %s", async (path, text) => {
    const result = await parse(path, text);
    expect(result.structure.obj?.data.elementCount).toBe(3);
    const coordinates = result.model.obj!.data.atomicConformation;
    expect(Array.from(coordinates.x)).toEqual(
      expect.arrayContaining([expect.closeTo(0.76), expect.closeTo(-0.76)]),
    );
    expect(result.isCrystal).toBe(false);
    expect(result.component?.obj?.data.elementCount).toBe(3);
    expect(
      plugins.at(-1)!.managers.structure.hierarchy.current.structures[0]
        .components,
    ).toHaveLength(1);
  });

  it("recognizes crystal CIF, converts fractional coordinates, and expands symmetry", async () => {
    const result = await parse("CRYSTAL.CIF", CRYSTAL_CIF);
    expect(result.isCrystal).toBe(true);
    expect(result.model.obj!.data.atomicConformation.x[0]).toBeCloseTo(1);
    expect(result.structure.obj!.data.elementCount).toBe(2);
  });

  it("retains a multi-frame XYZ trajectory and can switch the visible model", async () => {
    const result = await parse(
      "trajectory.xyz",
      WATER_XYZ + WATER_XYZ.replaceAll("0.76", "1.76"),
    );
    expect(result.structure.obj!.data.elementCount).toBe(3);
    expect(result.model.obj!.data.atomicConformation.x[1]).toBeCloseTo(0.76);
    expect(result.trajectory.obj!.data.frameCount).toBe(2);
    await plugins
      .at(-1)!
      .state.data.build()
      .to(result.model)
      .update({ modelIndex: 1 })
      .commit();
    expect(result.model.obj!.data.atomicConformation.x[1]).toBeCloseTo(1.76);
    expect(result.component!.obj!.data.elementCount).toBe(3);
  });

  it.each([
    ["empty.xyz", ""],
    ["bad.xyz", "1\nbad coordinates\nC invalid 0 0\n"],
    ["empty.pdb", "REMARK no atoms\nEND\n"],
    ["bad.cif", "data_invalid\n_cell_length_a 10\n"],
    ["notes.txt", WATER_XYZ],
  ])("rejects unusable structures in %s", async (path, text) => {
    await expect(parse(path, text)).rejects.toThrow();
  });
});

// @spec MOL-002 — Unsupported WebGL rejects locally without unhandled promises
it("releases a real Mol* context when WebGL is unavailable", async () => {
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  const container = document.createElement("div");
  document.body.append(container);
  const viewer = createMolstarViewer(container, "water.xyz", WATER_XYZ);
  try {
    await expect(viewer.ready).rejects.toThrow("WebGL");
  } finally {
    viewer.dispose();
    expect(container.querySelector("canvas")).toBeNull();
    container.remove();
    await new Promise((resolve) => setTimeout(resolve, 20));
    consoleError.mockRestore();
  }
});
