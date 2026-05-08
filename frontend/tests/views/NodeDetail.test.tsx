import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import NodeDetail from "@/views/NodeDetail";

vi.mock("@/api/client", () => ({
  api: {
    getNode: vi.fn(async (_table: string, id: string) => ({
      id,
      type: "Bet",
      props: { title: "Hello" },
      outgoing_edges: [{ edge_type: "led-to", to_id: "x_2", confidence: 0.9 }],
      incoming_edges: [],
    })),
  },
}));

describe("NodeDetail", () => {
  it("shows '(select a node)' when nothing selected", () => {
    render(<NodeDetail table={null} nodeId={null} />);
    expect(screen.getByText("(select a node)")).toBeInTheDocument();
  });

  it("fetches and renders the node detail when selection is provided", async () => {
    render(<NodeDetail table="Bet" nodeId="b_1" />);
    await waitFor(() => expect(screen.getByText("Bet")).toBeInTheDocument());
    expect(screen.getByText(/Hello/)).toBeInTheDocument();
    expect(screen.getByText(/led-to/)).toBeInTheDocument();
  });
});
