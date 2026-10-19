import { afterEach, expect, it, vi } from "vitest";
import { ScienceApiError, scienceAppsService } from "./science-apps-service";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

// @spec MINERU-004 — Document bytes and credentials stay on the served origin
it("uploads document bytes with encoded options and the runtime session key", async () => {
  vi.stubEnv("VITE_SESSION_API_KEY", "local-key");
  vi.stubEnv(
    "VITE_BACKEND_BASE_URL",
    "https://other-conversation-host.example",
  );
  const fetch = vi.fn();
  fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ id: "document-job" }),
  });
  vi.stubGlobal("fetch", fetch);
  const file = new File(["pdf bytes"], "文档 & result.pdf");
  const result = await scienceAppsService.submitDocument(file, {
    title: "Test & parse",
    method: "vlm",
    language: "ch",
    enable_formula: true,
    enable_table: false,
  });
  expect(result.id).toBe("document-job");
  const [path, options] = fetch.mock.calls[0];
  const url = new URL(path, "https://served-origin.example");
  expect(url.origin).toBe("https://served-origin.example");
  expect(url.pathname).toBe("/api/science/documents");
  expect(url.searchParams.get("filename")).toBe(file.name);
  expect(url.searchParams.get("enable_table")).toBe("false");
  expect(options).toEqual({
    method: "POST",
    body: file,
    headers: {
      "Content-Type": "application/octet-stream",
      "X-Session-API-Key": "local-key",
    },
  });
});

it("surfaces an upload rejection as a typed science error", async () => {
  const fetch = vi.fn();
  fetch.mockResolvedValue({
    ok: false,
    json: async () => ({ detail: "input_too_large" }),
  });
  vi.stubGlobal("fetch", fetch);
  await expect(
    scienceAppsService.submitDocument(new File(["x"], "paper.pdf"), {
      title: "",
      method: "vlm",
      language: "ch",
      enable_formula: true,
      enable_table: true,
    }),
  ).rejects.toEqual(new ScienceApiError("input_too_large"));
});
