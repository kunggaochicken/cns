import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DesktopGraphView } from "../../src/views/DesktopGraphView";
import type { GraphState, ThoughtNode, BetNode } from "../../src/api/types";

vi.mock("react-force-graph-2d", () => ({
  __esModule: true,
  default: (props: any) => (
    <div
      data-testid="force-graph"
      data-nodes={JSON.stringify(props.graphData.nodes.map((n: any) => n.id))}
      data-links={JSON.stringify(
        props.graphData.links.map((l: any) => `${l.source}::${l.target}`),
      )}
      onClick={() =>
        props.onNodeClick?.(props.graphData.nodes[0])
      }
    />
  ),
}));

const thought: ThoughtNode = {
  node_type: "thought", id: "t_1", content: "hi", source: "web",
  created_at: "2026-05-12T00:00:00Z", metadata: {},
};
const bet: BetNode = {
  node_type: "bet", id: "b_1", slug: "x", title: "X", vault_path: "p",
  owner: "ceo", horizon: "Q", confidence: "medium", created_at: "",
};
const state: GraphState = {
  nodes: [thought, bet],
  edges: [
    { from_id: "t_1", from_type: "thought", to_id: "b_1", to_type: "bet",
      edge_type: "sparred-against", created_at: "", confidence: 1 },
  ],
};

describe("DesktopGraphView", () => {
  it("passes nodes and links to react-force-graph-2d", () => {
    render(<DesktopGraphView state={state} onNodeSelect={() => {}} />);
    const fg = screen.getByTestId("force-graph");
    expect(fg.dataset.nodes).toBe(JSON.stringify(["t_1", "b_1"]));
    expect(fg.dataset.links).toBe(JSON.stringify(["t_1::b_1"]));
  });

  it("onNodeClick calls onNodeSelect with the clicked node", async () => {
    const onSelect = vi.fn();
    render(<DesktopGraphView state={state} onNodeSelect={onSelect} />);
    screen.getByTestId("force-graph").click();
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "t_1" }));
  });
});
