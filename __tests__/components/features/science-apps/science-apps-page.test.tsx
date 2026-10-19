import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../../../test-utils";
import { ScienceAppsPage } from "#/components/features/science-apps/science-apps-page";
import {
  scienceAppsService,
  SCIENCE_EXAMPLE_XYZ,
  type ScienceApplication,
  type ScienceJobDetail,
} from "#/api/science-apps-service";

vi.mock("#/api/science-apps-service", async (importOriginal) => ({
  ...(await importOriginal<typeof import("#/api/science-apps-service")>()),
  scienceAppsService: {
    apps: vi.fn(),
    jobs: vi.fn(),
    job: vi.fn(),
    submit: vi.fn(),
    cancel: vi.fn(),
    download: vi.fn(),
  },
}));
const applications: ScienceApplication[] = [
  {
    id: "xtb",
    name: "xTB",
    category: "semiempirical",
    available: true,
    methods: ["GFN2-xTB"],
    bases: [],
    max_cores: 8,
    max_memory_mb: 8192,
    timeout_seconds: 900,
  },
  {
    id: "orca",
    name: "ORCA",
    category: "quantum",
    available: false,
    methods: ["HF"],
    bases: ["def2-SVP"],
    max_cores: 8,
    max_memory_mb: 8192,
    timeout_seconds: 900,
  },
];
const job: ScienceJobDetail = {
  id: "abc",
  app_id: "xtb",
  title: "Water",
  status: "running",
  created_at: "2026-10-19T10:00:00Z",
  started_at: null,
  finished_at: null,
  error: null,
  energy_hartree: null,
  exit_code: null,
  request: {
    app_id: "xtb",
    xyz: SCIENCE_EXAMPLE_XYZ,
    title: "Water",
    task: "energy",
    method: "GFN2-xTB",
    basis: "",
    charge: 0,
    multiplicity: 1,
    cores: 2,
    memory_mb: 2048,
  },
  log: "calculating",
  files: [{ name: "input.xyz", size: 100 }],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(scienceAppsService.apps).mockResolvedValue(applications);
  vi.mocked(scienceAppsService.jobs).mockResolvedValue([]);
  vi.mocked(scienceAppsService.job).mockResolvedValue(job);
  vi.mocked(scienceAppsService.submit).mockResolvedValue(job);
  vi.mocked(scienceAppsService.cancel).mockImplementation(async () => {
    const stopped: ScienceJobDetail = { ...job, status: "cancelled" };
    vi.mocked(scienceAppsService.job).mockResolvedValue(stopped);
    return stopped;
  });
});

describe("manual scientific applications", () => {
  it("filters deployed applications and links to the standalone workbench", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ScienceAppsPage jobId={null} onSelectJob={vi.fn()} />);
    expect(await screen.findByTestId("science-app-xtb")).toHaveAttribute(
      "href",
      "/science-apps/xtb",
    );
    await user.click(screen.getByRole("button", { name: "SCIENCE$QUANTUM" }));
    expect(screen.queryByTestId("science-app-xtb")).not.toBeInTheDocument();
    expect(screen.getByTestId("science-app-orca")).toHaveTextContent(
      "SCIENCE$UNAVAILABLE",
    );
  });

  it("uploads XYZ and submits parameters directly to the science service", async () => {
    const user = userEvent.setup();
    const onSelectJob = vi.fn();
    renderWithProviders(
      <ScienceAppsPage appId="xtb" jobId={null} onSelectJob={onSelectJob} />,
    );
    await screen.findByTestId("science-submit");
    const file = new File([SCIENCE_EXAMPLE_XYZ], "water.xyz", {
      type: "text/plain",
    });
    Object.defineProperty(file, "text", {
      value: async () => SCIENCE_EXAMPLE_XYZ,
    });
    await user.upload(screen.getByLabelText("SCIENCE$UPLOAD_XYZ"), file);
    await waitFor(() =>
      expect(screen.getByLabelText("SCIENCE$XYZ_CONTENT")).toHaveValue(
        SCIENCE_EXAMPLE_XYZ,
      ),
    );
    fireEvent.change(screen.getByLabelText("SCIENCE$CORES"), {
      target: { value: "4" },
    });
    await user.click(screen.getByTestId("science-submit"));
    await waitFor(() => expect(onSelectJob).toHaveBeenCalledWith("abc"));
    expect(scienceAppsService.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        app_id: "xtb",
        xyz: SCIENCE_EXAMPLE_XYZ,
        cores: 4,
      }),
      expect.anything(),
    );
  });

  it("disables unavailable tools and restores saved jobs with stop and download actions", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ScienceAppsPage appId="orca" jobId="abc" onSelectJob={vi.fn()} />,
    );
    expect(await screen.findByTestId("science-submit")).toBeDisabled();
    expect(await screen.findByLabelText("SCIENCE$LOG")).toHaveValue(
      "calculating",
    );
    await user.click(screen.getByRole("button", { name: /input\.xyz/ }));
    expect(scienceAppsService.download).toHaveBeenCalledWith(
      "abc",
      "input.xyz",
    );
    await user.click(screen.getByRole("button", { name: "SCIENCE$STOP" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("SCIENCE$CANCELLED"),
    );
  });
});
