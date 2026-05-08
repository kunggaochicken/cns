import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { GraphProvider } from "@/state/GraphProvider";
import { useGraph } from "@/state/useGraph";

vi.mock("@/api/client", () => ({
  api: {
    getGraph: vi.fn(async () => ({
      nodes: [{ id: "b_1", type: "Bet", created_at: "" }],
      edges: [],
    })),
    getGateItems: vi.fn(async () => []),
    getHotspots: vi.fn(async () => []),
  },
}));

vi.mock("@/api/stream", () => ({ useEventStream: () => {} }));

function Probe() {
  const { nodes } = useGraph();
  return <div data-testid="count">{nodes.length}</div>;
}

describe("GraphProvider", () => {
  it("loads initial graph and exposes nodes via useGraph", async () => {
    render(
      <GraphProvider>
        <Probe />
      </GraphProvider>
    );
    await waitFor(() =>
      expect(screen.getByTestId("count").textContent).toBe("1")
    );
  });
});
