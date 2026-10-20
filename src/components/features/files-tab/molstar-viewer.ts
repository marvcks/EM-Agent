import { PluginContext } from "molstar/lib/mol-plugin/context";
import { Color } from "molstar/lib/mol-util/color";
import { loadMolecularStructure } from "./molstar-structure";

export interface MolecularViewerController {
  ready: Promise<void>;
  reset: () => void;
  resize: () => void;
  dispose: () => void;
}

// @spec MOL-002 — Each preview owns its canvas, tasks, and WebGL resources
export function createMolstarViewer(
  container: HTMLDivElement,
  path: string,
  text: string,
): MolecularViewerController {
  // Canvas controls provide rotation/zoom/pan without the full Mol* UI or its
  // global CSS. No download or remote annotation behaviors are registered.
  const plugin = new PluginContext({
    behaviors: [],
    canvas3d: { renderer: { backgroundColor: Color(0xf8fafc) } },
    layout: { initial: { isExpanded: false, showControls: false } },
  });
  // Mol* exposes these separately from init()/initViewerAsync(); consume their
  // rejected mirrors too so unavailable WebGL stays a local preview error.
  void plugin.initialized.catch(() => undefined);
  void plugin.canvas3dInitialized.catch(() => undefined);
  // Keep the canvas attached to its own parent through disposal: Mol*'s
  // input observer unobserves canvas.parentElement while releasing WebGL.
  const viewport = document.createElement("div");
  viewport.className = "absolute inset-0 overflow-hidden";
  const canvas = document.createElement("canvas");
  canvas.className = "absolute inset-0 h-full w-full";
  viewport.appendChild(canvas);
  container.appendChild(viewport);
  let disposed = false;
  const ready = (async () => {
    await plugin.init();
    if (disposed) return;
    if (!(await plugin.initViewerAsync(canvas, viewport))) {
      throw new Error("WebGL initialization failed");
    }
    if (disposed) return;
    const { model, structure, isCrystal } = await loadMolecularStructure(
      plugin,
      path,
      text,
    );
    if (disposed) return;
    await plugin.builders.structure.representation.addRepresentation(
      structure,
      {
        type: "ball-and-stick",
        typeParams: { sizeFactor: 0.3 },
        color: "element-symbol",
        colorParams: { carbonColor: { name: "element-symbol", params: {} } },
      },
    );
    if (disposed) return;
    if (isCrystal) await plugin.builders.structure.tryCreateUnitcell(model);
    if (!disposed) plugin.managers.camera.reset();
  })();
  // Let an active parser finish before disposing its state tree. The detached
  // canvas belongs only to this controller, so a newer preview is unaffected.
  const settled = ready.then(
    () => undefined,
    () => undefined,
  );
  return {
    ready,
    reset: () => {
      if (!disposed) plugin.managers.camera.reset();
    },
    resize: () => {
      if (!disposed) plugin.handleResize();
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      viewport.remove();
      void settled.then(() => {
        plugin.dispose();
        canvas.remove();
      });
    },
  };
}
