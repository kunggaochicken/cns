import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TopBar } from "../../src/components/TopBar";
import type { GraphState, GateItemNode, ConflictNode } from "../../src/api/types";

const gate = (id: string, resolved = false): GateItemNode => ({
  node_type: "gate_item",
  id,
  prompt: "?",
  urgency: "urgent",
  resolved_at: resolved ? "2026-05-12T01:00:00Z" : null,
  decision: resolved ? "approved" : null,
  reasoning: "",
  created_at: "2026-05-12T00:00:00Z",
});

const conflict = (id: string): ConflictNode => ({
  node_type: "conflict",
  id,
  summary: "x",
  severity: "high",
  created_at: "2026-05-12T00:00:00Z",
});

describe("TopBar", () => {
  it("renders only unresolved gate item count", () => {
    const state: GraphState = {
      nodes: [gate("g_1"), gate("g_2", true)],
      edges: [],
    };
    render(<TopBar state={state} />);
    expect(screen.getByText(/1 gate/i)).toBeInTheDocument();
  });

  it("renders hot spot count from scored nodes", () => {
    const state: GraphState = {
      nodes: [conflict("c_1"), conflict("c_2"), gate("g_1")],
      edges: [],
    };
    render(<TopBar state={state} />);
    expect(screen.getByText(/3 hot/i)).toBeInTheDocument();
  });
});
