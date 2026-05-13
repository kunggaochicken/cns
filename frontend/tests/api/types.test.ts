import { describe, it, expect } from "vitest";
import type {
  AnyNode,
  NodeType,
  GraphChangedEvent,
} from "../../src/api/types";

describe("api/types", () => {
  it("NodeType union covers every spec-defined node type", () => {
    const allTypes: NodeType[] = [
      "thought",
      "bet",
      "task",
      "decision",
      "conflict",
      "outcome",
      "agent_firing",
      "code_change",
      "conversation",
      "doc",
      "gate_item",
      "agent",
    ];
    expect(allTypes.length).toBe(12);
  });

  it("AnyNode discriminates by node_type", () => {
    const node: AnyNode = {
      node_type: "thought",
      id: "t_abc",
      content: "hello",
      source: "web",
      created_at: "2026-05-12T00:00:00Z",
      metadata: {},
    };
    if (node.node_type === "thought") {
      expect(node.content).toBe("hello");
    }
  });

  it("GraphChangedEvent shape matches backend", () => {
    const event: GraphChangedEvent = {
      event: "graph.changed",
      change_type: "node_created",
      node_id: "t_abc",
    };
    expect(event.event).toBe("graph.changed");
  });
});
