import { describe, it, expect } from "vitest";
import { computeHotSpots, HOT_SPOT_WEIGHTS } from "../../src/state/hotSpots";
import type { AnyNode, Edge, GraphState } from "../../src/api/types";

function mkConflict(id: string): AnyNode {
  return {
    node_type: "conflict",
    id,
    summary: "x",
    severity: "high",
    created_at: "2026-05-12T00:00:00Z",
  };
}

function mkGate(id: string, urgency = "urgent"): AnyNode {
  return {
    node_type: "gate_item",
    id,
    prompt: "x",
    urgency,
    resolved_at: null,
    decision: null,
    reasoning: "",
    created_at: "2026-05-12T00:00:00Z",
  };
}

describe("hotSpots", () => {
  it("conflicts contribute by severity", () => {
    const state: GraphState = { nodes: [mkConflict("c_1")], edges: [] };
    const map = computeHotSpots(state);
    expect(map.get("c_1")).toBeGreaterThan(0);
  });

  it("urgent gate items score higher than novel gate items", () => {
    const state: GraphState = {
      nodes: [mkGate("g_urgent", "urgent"), mkGate("g_novel", "novel")],
      edges: [],
    };
    const map = computeHotSpots(state);
    expect(map.get("g_urgent")!).toBeGreaterThan(map.get("g_novel")!);
  });

  it("higher-degree nodes get a connectivity bonus", () => {
    const a = mkConflict("c_a");
    const b = mkConflict("c_b");
    const edges: Edge[] = [
      { from_id: "c_a", from_type: "conflict", to_id: "t_x", to_type: "thought", edge_type: "x", created_at: "", confidence: 1 },
      { from_id: "c_a", from_type: "conflict", to_id: "t_y", to_type: "thought", edge_type: "x", created_at: "", confidence: 1 },
    ];
    const map = computeHotSpots({ nodes: [a, b], edges });
    expect(map.get("c_a")!).toBeGreaterThan(map.get("c_b")!);
  });

  it("resolved gate items are not scored", () => {
    const open = mkGate("g_open", "urgent");
    const resolved = mkGate("g_resolved", "urgent");
    (resolved as { resolved_at: string | null }).resolved_at =
      "2026-05-12T01:00:00Z";
    const map = computeHotSpots({ nodes: [open, resolved], edges: [] });
    expect(map.has("g_open")).toBe(true);
    expect(map.has("g_resolved")).toBe(false);
  });

  it("weights table is exported and matches expected keys", () => {
    expect(HOT_SPOT_WEIGHTS).toMatchObject({
      conflict: expect.any(Number),
      gate_urgent: expect.any(Number),
      gate_medium: expect.any(Number),
      gate_novel: expect.any(Number),
      degree: expect.any(Number),
    });
  });
});
