import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NodeDetailPanel } from "../../src/views/NodeDetailPanel";
import type { BetNode, GateItemNode } from "../../src/api/types";

const bet: BetNode = {
  node_type: "bet", id: "b_1", slug: "ship-v1", title: "Ship v1",
  vault_path: "Brain/Bets/bet_ship_v1.md", owner: "ceo", horizon: "Q",
  confidence: "medium", created_at: "2026-05-12T00:00:00Z",
};

const gate: GateItemNode = {
  node_type: "gate_item", id: "g_1", prompt: "go?", urgency: "urgent",
  resolved_at: null, decision: null, reasoning: "", created_at: "2026-05-12T00:00:00Z",
};

describe("NodeDetailPanel", () => {
  it("renders nothing when node is null", () => {
    const { container } = render(<NodeDetailPanel node={null} onClose={() => {}} onResolved={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the bet title and an open-external link", () => {
    render(<NodeDetailPanel node={bet} onClose={() => {}} onResolved={() => {}} />);
    expect(screen.getByText("Ship v1")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /open in obsidian/i });
    expect(link).toHaveAttribute(
      "href",
      "obsidian://open?path=Brain%2FBets%2Fbet_ship_v1.md",
    );
  });

  it("renders the gate resolve panel for gate_item nodes", () => {
    render(<NodeDetailPanel node={gate} onClose={() => {}} onResolved={() => {}} />);
    expect(screen.getByText("go?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve/i })).toBeInTheDocument();
  });

  it("close button calls onClose", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<NodeDetailPanel node={bet} onClose={onClose} onResolved={() => {}} />);
    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
