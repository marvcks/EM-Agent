import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../../../test-utils";
import { ScienceAppsPage } from "#/components/features/science-apps/science-apps-page";
import {
  scienceAppsService,
  SCIENCE_EXAMPLE_XYZ,
  SCIENCE_MAGUS_EXAMPLE_XYZ,
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
  ...(["aizynthfinder", "lcms2yield"] as const).map((id) => ({
    id,
    name: id,
    category: "reaction" as const,
    available: true,
    methods: [id === "aizynthfinder" ? "USPTO" : "UV-CF 20250721"],
    bases: [],
    max_cores: 8,
    max_memory_mb: 8192,
    timeout_seconds: 900,
  })),
  {
    id: "magus",
    name: "MAGUS",
    category: "crystal",
    available: true,
    methods: ["MACE-OFF23"],
    bases: [],
    max_cores: 8,
    max_memory_mb: 8192,
    timeout_seconds: 900,
  },
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
  it.each(["aizynthfinder", "lcms2yield"] as const)(
    "submits %s SMILES with its own task and shows typed results",
    async (appId) => {
      const user = userEvent.setup();
      vi.mocked(scienceAppsService.job).mockResolvedValue({
        ...job,
        app_id: appId,
        status: "succeeded",
        result:
          appId === "aizynthfinder"
            ? { route_count: 2, solved_count: 1 }
            : { correction_factors: [{ smiles: "c1ccccc1", cf: 1.1300693 }] },
      });
      renderWithProviders(
        <ScienceAppsPage appId={appId} jobId="abc" onSelectJob={vi.fn()} />,
      );
      await screen.findByTestId("science-submit");
      expect(screen.queryByLabelText("SCIENCE$CHARGE")).not.toBeInTheDocument();
      expect(
        screen.queryByLabelText("SCIENCE$UPLOAD_XYZ"),
      ).not.toBeInTheDocument();
      await user.click(
        screen.getByRole("button", { name: "SCIENCE$SMILES_EXAMPLE" }),
      );
      await user.click(screen.getByTestId("science-submit"));
      await waitFor(() =>
        expect(scienceAppsService.submit).toHaveBeenCalledWith(
          expect.objectContaining({
            app_id: appId,
            task:
              appId === "aizynthfinder"
                ? "retrosynthesis"
                : "correction_factor",
            xyz: "",
            smiles: expect.any(String),
          }),
          expect.anything(),
        ),
      );
      if (appId === "lcms2yield") {
        expect(screen.getByText("1.130069")).toBeInTheDocument();
        expect(screen.getByText("SCIENCE$CF_RESULT_NOTE")).toBeInTheDocument();
      } else {
        expect(screen.getByText("SCIENCE$ROUTE_COUNTS")).toBeInTheDocument();
      }
    },
  );

  it("submits a bounded molecular crystal search and shows energies in eV", async () => {
    const user = userEvent.setup();
    vi.mocked(scienceAppsService.job).mockResolvedValue({
      ...job,
      app_id: "magus",
      status: "succeeded",
      energy_ev: -123.5,
    });
    renderWithProviders(
      <ScienceAppsPage appId="magus" jobId="abc" onSelectJob={vi.fn()} />,
    );
    await screen.findByTestId("science-submit");
    expect(screen.queryByLabelText("SCIENCE$CHARGE")).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "SCIENCE$USE_METHANE_EXAMPLE" }),
    );
    fireEvent.change(screen.getByLabelText("SCIENCE$GENERATIONS"), {
      target: { value: "2" },
    });
    await user.click(screen.getByTestId("science-submit"));
    await waitFor(() =>
      expect(scienceAppsService.submit).toHaveBeenCalledWith(
        expect.objectContaining({
          app_id: "magus",
          task: "search",
          xyz: SCIENCE_MAGUS_EXAMPLE_XYZ,
          model_size: "medium",
          molecules_per_cell: 4,
          generations: 2,
          population_size: 6,
          volume_min: 180,
          volume_max: 400,
          charge: 0,
          multiplicity: 1,
        }),
        expect.anything(),
      ),
    );
    expect(screen.getByText("SCIENCE$ENERGY_EV_VALUE")).toBeInTheDocument();
  });

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
