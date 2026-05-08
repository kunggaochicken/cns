import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

// Cytoscape's canvas renderer crashes in jsdom ("Could not create canvas of
// type 2d"). The test only verifies the host div renders, so stub the module
// with a minimal API surface (init, on, json, layout, destroy).
vi.mock("cytoscape", () => {
  const fakeCy = {
    on: vi.fn(),
    json: vi.fn(),
    layout: vi.fn(() => ({ run: vi.fn() })),
    destroy: vi.fn(),
  };
  return { default: vi.fn(() => fakeCy) };
});

import GraphCanvas from "@/views/GraphCanvas";
import { GraphContext } from "@/state/GraphProvider";

const fakeContext = {
  nodes: [
    { id: "t_1", type: "Thought" as const, created_at: "" },
    { id: "b_1", type: "Bet" as const, created_at: "" },
  ],
  edges: [{ from_id: "t_1", to_id: "b_1", edge_type: "sparred-against", created_at: "" }],
  gateItems: [],
  hotspots: [],
  refresh: vi.fn(),
};

describe("GraphCanvas", () => {
  it("renders without crashing given nodes and edges", () => {
    const { container } = render(
      <GraphContext.Provider value={fakeContext}>
        <GraphCanvas onSelectNode={() => {}} />
      </GraphContext.Provider>
    );
    expect(container.querySelector("[data-testid='cy-host']")).toBeTruthy();
  });
});
