import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { NodeBadge } from "../../src/components/NodeBadge";

describe("NodeBadge", () => {
  it("renders the node type label", () => {
    render(<NodeBadge type="bet" />);
    expect(screen.getByText(/bet/i)).toBeInTheDocument();
  });

  it("uses a distinct background per node type", () => {
    const { rerender, container } = render(<NodeBadge type="bet" />);
    const betBg = container.firstElementChild!.className;
    rerender(<NodeBadge type="conflict" />);
    const conflictBg = container.firstElementChild!.className;
    expect(betBg).not.toBe(conflictBg);
  });
});
