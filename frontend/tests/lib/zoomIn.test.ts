import { describe, it, expect } from "vitest";
import { resolveZoomIn } from "../../src/lib/zoomIn";
import type {
  BetNode, TaskNode, CodeChangeNode, GateItemNode, ConflictNode, ThoughtNode,
} from "../../src/api/types";

const bet: BetNode = {
  node_type: "bet", id: "b_1", slug: "ship-v1", title: "Ship v1",
  vault_path: "Brain/Bets/bet_ship_v1.md", owner: "ceo", horizon: "Q",
  confidence: "medium", created_at: "",
};
const task: TaskNode = {
  node_type: "task", id: "k_1", linear_id: "GIG-100", title: "x", status: "todo",
  created_at: "",
};
const change: CodeChangeNode = {
  node_type: "code_change", id: "cc_1", repo: "kunggaochicken/GigaBrain",
  sha: "abc123", summary: "x", created_at: "",
};
const gate: GateItemNode = {
  node_type: "gate_item", id: "g_1", prompt: "?", urgency: "urgent",
  resolved_at: null, decision: null, reasoning: "", created_at: "",
};
const conflict: ConflictNode = {
  node_type: "conflict", id: "c_1", summary: "x", severity: "high", created_at: "",
};
const thought: ThoughtNode = {
  node_type: "thought", id: "t_1", content: "x", source: "web",
  created_at: "", metadata: {},
};

describe("resolveZoomIn", () => {
  it("bet → Obsidian URI", () => {
    expect(resolveZoomIn(bet)).toEqual({
      kind: "external",
      href: "obsidian://open?path=Brain%2FBets%2Fbet_ship_v1.md",
    });
  });

  it("task → Linear URL", () => {
    expect(resolveZoomIn(task)).toEqual({
      kind: "external",
      href: "https://linear.app/gigaflow/issue/GIG-100",
    });
  });

  it("code_change → GitHub commit URL", () => {
    expect(resolveZoomIn(change)).toEqual({
      kind: "external",
      href: "https://github.com/kunggaochicken/GigaBrain/commit/abc123",
    });
  });

  it("gate_item → in-place gate panel", () => {
    expect(resolveZoomIn(gate)).toEqual({ kind: "panel", panel: "gate", nodeId: "g_1" });
  });

  it("conflict → in-place conflict panel", () => {
    expect(resolveZoomIn(conflict)).toEqual({
      kind: "panel", panel: "conflict", nodeId: "c_1",
    });
  });

  it("thought → in-place detail panel", () => {
    expect(resolveZoomIn(thought)).toEqual({
      kind: "panel", panel: "detail", nodeId: "t_1",
    });
  });
});
