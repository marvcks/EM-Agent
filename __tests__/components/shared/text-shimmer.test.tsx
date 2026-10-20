import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TextShimmer } from "#/components/shared/text-shimmer";

describe("TextShimmer", () => {
  // @spec TSH-001 — Disabling shimmer restores the same text element
  it("stops and restarts on the same accessible text element", () => {
    const { rerender } = render(
      <TextShimmer as="span" role="status" title="Agent status">
        Working
      </TextShimmer>,
    );
    const label = screen.getByRole("status");
    expect(label).toHaveAttribute("data-shimmer-active", "true");

    rerender(
      <TextShimmer as="span" role="status" title="Agent status" active={false}>
        Finished
      </TextShimmer>,
    );

    expect(screen.getByRole("status")).toBe(label);
    expect(label).toHaveTextContent("Finished");
    expect(label).toHaveAttribute("title", "Agent status");
    expect(label).toHaveAttribute("data-shimmer-active", "false");

    rerender(
      <TextShimmer as="span" role="status" active>
        Working again
      </TextShimmer>,
    );

    expect(screen.getByRole("status")).toBe(label);
    expect(label).toHaveAttribute("data-shimmer-active", "true");
  });
});
