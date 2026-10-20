import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "test-utils";
import { HomeHeaderTitle } from "#/components/features/home/home-header/home-header-title";

describe("HomeHeaderTitle", () => {
  it("renders a welcome heading followed by supporting copy", () => {
    renderWithProviders(<HomeHeaderTitle />);

    expect(
      screen.getByRole("heading", { level: 1, name: "HOME$WHAT_TO_WORK_ON" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("home-header-subtitle")).toHaveTextContent(
      "HOME$ENGINEERING_TASKS_SUBHEADER",
    );
  });
});
