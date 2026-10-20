import type { BuiltInTrajectoryFormat } from "molstar/lib/mol-plugin-state/formats/trajectory";

type MolecularFileFormat = BuiltInTrajectoryFormat | "cif";

const MOLECULAR_FORMATS: Readonly<Record<string, MolecularFileFormat>> = {
  xyz: "xyz",
  cif: "cif",
  mmcif: "mmcif",
  mcif: "mmcif",
  pdb: "pdb",
  ent: "pdb",
  mol: "mol",
  sdf: "sdf",
  sd: "sdf",
  mol2: "mol2",
};

export function getMolecularFileFormat(
  path: string,
): MolecularFileFormat | null {
  const name = path.split(/[/\\]/).pop() ?? "";
  const extension = name.includes(".")
    ? name.split(".").pop()!.toLowerCase()
    : "";
  return MOLECULAR_FORMATS[extension] ?? null;
}
