import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AgentServerUIRoot } from "#/components/providers/agent-server-ui-root";

it("does not apply a stored Canvas preference to an uninitialized library root", () => {
  localStorage.setItem("em-agent-color-theme", "openhands-neutral");
  try {
    render(
      <AgentServerUIRoot data-testid="embedded">
        Embedded Canvas
      </AgentServerUIRoot>,
    );
    expect(screen.getByTestId("embedded").firstElementChild).toHaveAttribute(
      "data-theme",
      "light",
    );
  } finally {
    localStorage.removeItem("em-agent-color-theme");
  }
});
