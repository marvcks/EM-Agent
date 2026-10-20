import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MolecularStructureViewer from "#/components/features/files-tab/molecular-structure-viewer";
import { createMolstarViewer } from "#/components/features/files-tab/molstar-viewer";

vi.mock("#/components/features/files-tab/molstar-viewer", () => ({
  createMolstarViewer: vi.fn(),
}));

const createViewer = vi.mocked(createMolstarViewer);
const reset = vi.fn();
const dispose = vi.fn();
const resize = vi.fn();

// @spec MOL-002 — Own the WebGL viewer lifecycle and show actionable errors
describe("MolecularStructureViewer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createViewer.mockReturnValue({
      ready: Promise.resolve(),
      reset,
      resize,
      dispose,
    });
  });

  it("loads new contents, resets the camera, and releases each viewer", async () => {
    const { rerender, unmount } = render(
      <MolecularStructureViewer path="water.xyz" text="water" />,
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "FILES$MOLECULAR_RESET" }),
    );
    expect(reset).toHaveBeenCalledOnce();
    rerender(<MolecularStructureViewer path="crystal.cif" text="crystal" />);
    await waitFor(() =>
      expect(createViewer).toHaveBeenLastCalledWith(
        expect.any(HTMLDivElement),
        "crystal.cif",
        "crystal",
      ),
    );
    expect(dispose).toHaveBeenCalledOnce();
    rerender(
      <MolecularStructureViewer path="crystal.cif" text="updated crystal" />,
    );
    await waitFor(() =>
      expect(createViewer).toHaveBeenLastCalledWith(
        expect.any(HTMLDivElement),
        "crystal.cif",
        "updated crystal",
      ),
    );
    unmount();
    expect(dispose).toHaveBeenCalledTimes(3);
  });

  it("shows a readable failure and can retry initialization", async () => {
    createViewer.mockReturnValueOnce({
      ready: Promise.reject(new Error("no WebGL")),
      reset,
      resize,
      dispose,
    });
    render(<MolecularStructureViewer path="water.xyz" text="water" />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "FILES$MOLECULAR_ERROR",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "FILES$MOLECULAR_RETRY" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
    expect(dispose).toHaveBeenCalledOnce();
    expect(createViewer).toHaveBeenCalledTimes(2);
  });

  it("ignores a late failure after switching files", async () => {
    let reject!: (reason: Error) => void;
    createViewer.mockReturnValueOnce({
      ready: new Promise<void>((_, fail) => {
        reject = fail;
      }),
      reset,
      resize,
      dispose,
    });
    const { rerender } = render(
      <MolecularStructureViewer path="old.xyz" text="old" />,
    );
    rerender(<MolecularStructureViewer path="new.xyz" text="new" />);
    await act(async () => {
      reject(new Error("old file failed"));
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "FILES$MOLECULAR_RESET" }),
    ).toBeEnabled();
  });
});
