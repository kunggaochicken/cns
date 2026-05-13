import { describe, it, expect } from "vitest";
import { graphReducer, initialGraphState } from "../../src/state/graph";
import type { ThoughtNode, BetNode, Edge } from "../../src/api/types";

const thought: ThoughtNode = {
  node_type: "thought",
  id: "t_1",
  content: "hello",
  source: "web",
  created_at: "2026-05-12T00:00:00Z",
  metadata: {},
};
const bet: BetNode = {
  node_type: "bet",
  id: "b_1",
  slug: "x",
  title: "X",
  vault_path: "Brain/Bets/bet_x.md",
  owner: "ceo",
  horizon: "Q",
  confidence: "medium",
  created_at: "2026-05-12T00:00:00Z",
};
const edge: Edge = {
  from_id: "t_1",
  from_type: "thought",
  to_id: "b_1",
  to_type: "bet",
  edge_type: "sparred-against",
  created_at: "2026-05-12T00:00:00Z",
  confidence: 1.0,
};

describe("graph reducer", () => {
  it("HYDRATE replaces all state", () => {
    const next = graphReducer(initialGraphState, {
      type: "HYDRATE",
      state: { nodes: [thought, bet], edges: [edge] },
    });
    expect(next.nodes).toHaveLength(2);
    expect(next.edges).toHaveLength(1);
  });

  it("ADD_NODE appends a new node", () => {
    const next = graphReducer(initialGraphState, { type: "ADD_NODE", node: thought });
    expect(next.nodes).toEqual([thought]);
  });

  it("ADD_NODE is idempotent on existing id", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_NODE", node: thought });
    const next = graphReducer(state, { type: "ADD_NODE", node: thought });
    expect(next.nodes).toHaveLength(1);
  });

  it("UPDATE_NODE replaces a node by id", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_NODE", node: bet });
    const updated: BetNode = { ...bet, title: "X v2" };
    const next = graphReducer(state, { type: "UPDATE_NODE", node: updated });
    expect(next.nodes[0]).toEqual(updated);
  });

  it("UPDATE_NODE on unknown id is a no-op", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_NODE", node: bet });
    const ghost: ThoughtNode = { ...thought, id: "t_ghost" };
    const next = graphReducer(state, { type: "UPDATE_NODE", node: ghost });
    expect(next.nodes).toEqual([bet]);
  });

  it("ADD_EDGE appends and dedupes on from/to/edge_type", () => {
    const state = graphReducer(initialGraphState, { type: "ADD_EDGE", edge });
    const next = graphReducer(state, { type: "ADD_EDGE", edge });
    expect(next.edges).toHaveLength(1);
  });
});
