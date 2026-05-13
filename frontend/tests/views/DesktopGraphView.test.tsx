import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import { DesktopGraphView } from "../../src/views/DesktopGraphView";
import type { GraphState, ThoughtNode, BetNode } from "../../src/api/types";

vi.mock("react-force-graph-2d", () => ({
  __esModule: true,
  default: (props: any) => (
    <div
      data-testid="force-graph"
      data-width={String(props.width)}
      data-height={String(props.height)}
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

let triggerResize: (() => void) | null = null;

class MockResizeObserver {
  cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
    triggerResize = () => this.cb([], this as unknown as ResizeObserver);
  }
  observe() {}
  unobserve() {}
  disconnect() {
    triggerResize = null;
  }
}

beforeEach(() => {
  (globalThis as any).ResizeObserver = MockResizeObserver;
});
afterEach(() => {
  triggerResize = null;
});

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

  it("updates width/height when the container is resized", () => {
    const widths: number[] = [];
    const origGet = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientWidth",
    );
    const origGetH = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientHeight",
    );
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get() {
        return widths.length ? widths[widths.length - 1] : 1200;
      },
    });
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return widths.length ? widths[widths.length - 1] / 2 : 900;
      },
    });

    try {
      render(<DesktopGraphView state={state} onNodeSelect={() => {}} />);
      const fg = screen.getByTestId("force-graph");
      expect(fg.dataset.width).toBe("1200");
      expect(fg.dataset.height).toBe("900");

      widths.push(640);
      act(() => {
        triggerResize?.();
      });
      expect(fg.dataset.width).toBe("640");
      expect(fg.dataset.height).toBe("320");
    } finally {
      if (origGet) Object.defineProperty(HTMLElement.prototype, "clientWidth", origGet);
      if (origGetH) Object.defineProperty(HTMLElement.prototype, "clientHeight", origGetH);
    }
  });
});
