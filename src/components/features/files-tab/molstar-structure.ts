import type { PluginContext } from "molstar/lib/mol-plugin/context";
import { guessCifVariant } from "molstar/lib/mol-plugin-state/formats/provider";
import { Vec3 } from "molstar/lib/mol-math/linear-algebra";
import { getFileNameInfo } from "molstar/lib/mol-util/file-info";
import { getMolecularFileFormat } from "./molecular-file-format";

// @spec MOL-003 — Parse real workspace structures, including crystal CIF
export async function loadMolecularStructure(
  plugin: PluginContext,
  path: string,
  text: string,
) {
  const detectedFormat = getMolecularFileFormat(path);
  if (!detectedFormat || !text.trim())
    throw new Error("Empty or unsupported structure");
  const format =
    detectedFormat === "cif"
      ? guessCifVariant(getFileNameInfo(path.toLowerCase()), text) === "coreCif"
        ? "cifCore"
        : "mmcif"
      : detectedFormat;
  const data = await plugin.builders.data.rawData({ data: text, label: path });
  const trajectory = await plugin.builders.structure.parseTrajectory(
    data,
    format,
  );
  if (!trajectory.obj?.data.frameCount) throw new Error("No structure models");
  const model = await plugin.builders.structure.createModel(trajectory, {
    modelIndex: 0,
  });
  const conformation = model.obj?.data.atomicConformation;
  if (!conformation?.x.length) throw new Error("No atoms in structure");
  for (let i = 0; i < conformation.x.length; i += 1) {
    if (
      ![conformation.x[i], conformation.y[i], conformation.z[i]].every(
        Number.isFinite,
      )
    ) {
      throw new Error("Invalid atomic coordinates");
    }
  }
  // Crystal CIF stores the asymmetric unit; expand its symmetry operators in
  // one cell. Molecular formats retain their original coordinates/model.
  const structure = await plugin.builders.structure.createStructure(
    model,
    format === "cifCore"
      ? {
          name: "symmetry",
          params: {
            ijkMin: Vec3.create(0, 0, 0),
            ijkMax: Vec3.create(0, 0, 0),
          },
        }
      : { name: "model", params: {} },
  );
  if (!structure.obj?.data.elementCount) throw new Error("Empty structure");
  const component = await plugin.builders.structure.tryCreateComponentStatic(
    structure,
    "all",
  );
  if (!component) throw new Error("No structure component");
  return {
    trajectory,
    model,
    structure,
    component,
    isCrystal: format === "cifCore",
  };
}
