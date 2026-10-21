import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { PluginCommands } from "molstar/lib/mol-plugin/commands";
import { PluginUIContext } from "molstar/lib/mol-plugin-ui/context";
import { Plugin } from "molstar/lib/mol-plugin-ui/plugin";
import { createViewerSpec } from "molstar/lib/apps/viewer/plugin-spec";
import { ViewerAutoPreset } from "molstar/lib/apps/viewer/presets";
import { AGENT_SERVER_UI_SCOPE_ATTRIBUTE } from "#/styles/agent-server-ui-style-scope";
import { loadMolecularStructure } from "./molstar-structure";
import "molstar/build/viewer/molstar.css";

export interface MolecularViewerController {
  ready: Promise<void>;
  resize: () => void;
  dispose: () => void;
}

const LANDSCAPE_VIEWER_MIN_WIDTH = 900;
const EXPANDED_VIEWER_TEST_ID = "molecular-viewer-expanded";

// @spec MOL-004 — Official Viewer UI, behaviors, animations and extensions
export function createMolstarViewer(
  container: HTMLDivElement,
  path: string,
  text: string,
): MolecularViewerController {
  let embeddedDisplay: "landscape" | "portrait" =
    container.clientWidth >= LANDSCAPE_VIEWER_MIN_WIDTH
      ? "landscape"
      : "portrait";
  const plugin = new PluginUIContext(
    createViewerSpec({
      layoutIsExpanded: false,
      layoutControlsDisplay: embeddedDisplay,
      collapseLeftPanel: true,
      collapseRightPanel: false,
    }),
  );
  // Consume the library's mirrored initialization promises as well as ready.
  void plugin.initialized.catch(() => undefined);
  void plugin.canvas3dInitialized.catch(() => undefined);
  const viewport = document.createElement("div");
  viewport.className = "absolute inset-0";
  container.appendChild(viewport);
  const root = createRoot(viewport);
  let disposed = false;
  let wasExpanded = false;
  let expandedHost: HTMLDivElement | undefined;
  let previousFocus: HTMLElement | null = null;
  const restoreEmbeddedHost = () => {
    if (!expandedHost) return;
    viewport.className = "absolute inset-0";
    container.appendChild(viewport);
    expandedHost.remove();
    expandedHost = undefined;
    previousFocus?.focus();
    previousFocus = null;
  };
  const exitExpanded = (event: KeyboardEvent) => {
    if (event.key !== "Escape" || !plugin.layout.state.isExpanded) return;
    void PluginCommands.Layout.Update(plugin, {
      state: { isExpanded: false, expandToFullscreen: false },
    });
  };
  window.addEventListener("keydown", exitExpanded);
  const updateEmbeddedLayout = () => {
    if (disposed) return;
    if (plugin.layout.state.isExpanded) {
      if (!expandedHost) {
        // Fixed descendants inside Canvas's transformed panels are constrained
        // to that panel. Move the same root above it, retaining CSS isolation.
        previousFocus = document.activeElement as HTMLElement | null;
        expandedHost = document.createElement("div");
        expandedHost.setAttribute(AGENT_SERVER_UI_SCOPE_ATTRIBUTE, "");
        expandedHost.setAttribute("data-testid", EXPANDED_VIEWER_TEST_ID);
        expandedHost.setAttribute("role", "region");
        expandedHost.setAttribute(
          "aria-label",
          container.getAttribute("aria-label") ?? "",
        );
        expandedHost.tabIndex = -1;
        document.body.appendChild(expandedHost);
        viewport.className = "fixed inset-0 z-[10000]";
        expandedHost.appendChild(viewport);
        expandedHost.focus();
      }
      wasExpanded = true;
      return;
    }
    restoreEmbeddedHost();
    const next =
      container.clientWidth >= LANDSCAPE_VIEWER_MIN_WIDTH
        ? "landscape"
        : "portrait";
    const returning = wasExpanded;
    wasExpanded = false;
    if (returning || next !== embeddedDisplay) {
      embeddedDisplay = next;
      void PluginCommands.Layout.Update(plugin, {
        state: {
          controlsDisplay: next,
          ...(returning
            ? {
                regionState: {
                  ...plugin.layout.state.regionState,
                  left: "collapsed",
                  right: "full",
                },
              }
            : {}),
        },
      });
    }
  };
  const layoutSubscription =
    plugin.layout.events.updated.subscribe(updateEmbeddedLayout);
  const ready = (async () => {
    // Establish the canvas before registering UI extensions, so unsupported
    // WebGL fails locally before extensions subscribe to initialization.
    if (!(await plugin.initContainerAsync()))
      throw new Error("WebGL initialization failed");
    if (disposed) return;
    await plugin.init();
    if (disposed) return;
    // Match the official Viewer bootstrap, while owning the React root so its
    // subscriptions and controls are unmounted on file/mode changes too.
    plugin.builders.structure.representation.registerPreset(ViewerAutoPreset);
    root.render(createElement(Plugin, { plugin }));
    await plugin.canvas3dInitialized;
    if (!plugin.canvas3d) throw new Error("WebGL initialization failed");
    if (disposed) return;
    const { model, component, isCrystal } = await loadMolecularStructure(
      plugin,
      path,
      text,
    );
    if (disposed) return;
    await plugin.builders.structure.representation.addRepresentation(
      component,
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
  const settled = ready.then(
    () => undefined,
    () => undefined,
  );
  return {
    ready,
    resize: () => {
      if (disposed) return;
      updateEmbeddedLayout();
      plugin.handleResize();
    },
    dispose: () => {
      if (disposed) return;
      disposed = true;
      window.removeEventListener("keydown", exitExpanded);
      // Mol* does not restore expanded-page body styles in layout.dispose().
      if (
        plugin.layout.state.isExpanded ||
        plugin.layout.state.expandToFullscreen
      ) {
        void PluginCommands.Layout.Update(plugin, {
          state: {
            isExpanded: false,
            expandToFullscreen: false,
          },
        });
      }
      viewport.remove();
      expandedHost?.remove();
      expandedHost = undefined;
      void settled.then(() => {
        layoutSubscription.unsubscribe();
        // Keep the library-owned canvas in its parent until input cleanup.
        plugin.dispose();
        root.unmount();
      });
    },
  };
}
