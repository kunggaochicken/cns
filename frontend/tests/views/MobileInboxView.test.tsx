import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MobileInboxView } from "../../src/views/MobileInboxView";
import type { GraphState, GateItemNode, ConflictNode } from "../../src/api/types";

const gate = (id: string): GateItemNode => ({
  node_type: "gate_item", id, prompt: `prompt ${id}`, urgency: "urgent",
  resolved_at: null, decision: null, reasoning: "",
  created_at: "2026-05-12T00:00:00Z",
});
const conflict = (id: string): ConflictNode => ({
  node_type: "conflict", id, summary: `c ${id}`, severity: "high",
  created_at: "2026-05-12T00:00:00Z",
});

const state: GraphState = {
  nodes: [gate("g_1"), gate("g_2"), conflict("c_1")],
  edges: [],
};

describe("MobileInboxView", () => {
  it("default tab is Gate and lists gate items", () => {
    render(<MobileInboxView state={state} onZoom={() => {}} />);
    expect(screen.getByText("prompt g_1")).toBeInTheDocument();
    expect(screen.getByText("prompt g_2")).toBeInTheDocument();
  });

  it("Hot tab lists hot-spot nodes", async () => {
    const user = userEvent.setup();
    render(<MobileInboxView state={state} onZoom={() => {}} />);
    await user.click(screen.getByRole("tab", { name: /hot/i }));
    expect(screen.getByText(/c c_1/)).toBeInTheDocument();
  });

  it("Recent tab lists most recently created nodes", async () => {
    const user = userEvent.setup();
    render(<MobileInboxView state={state} onZoom={() => {}} />);
    await user.click(screen.getByRole("tab", { name: /recent/i }));
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(1);
  });
});
