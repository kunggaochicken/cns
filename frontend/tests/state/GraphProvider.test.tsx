import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { GraphProvider, useGraph } from "../../src/state/GraphProvider";
import type { ThoughtNode } from "../../src/api/types";

const thought: ThoughtNode = {
  node_type: "thought",
  id: "t_1",
  content: "hi",
  source: "web",
  created_at: "2026-05-12T00:00:00Z",
  metadata: {},
};

function Probe() {
  const { state } = useGraph();
  return <div data-testid="count">{state.nodes.length}</div>;
}

class MockEventSource {
  static instance: MockEventSource | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    MockEventSource.instance = this;
  }
}

beforeEach(() => {
  // @ts-expect-error mock
  globalThis.EventSource = MockEventSource;
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ nodes: [thought], edges: [] }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("GraphProvider", () => {
  it("hydrates from /graph/state on mount", async () => {
    render(
      <GraphProvider>
        <Probe />
      </GraphProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
  });

  it("appends nodes when stream emits graph.changed/node_created", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ nodes: [], edges: [] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => thought });

    render(
      <GraphProvider>
        <Probe />
      </GraphProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("0"));

    await act(async () => {
      MockEventSource.instance!.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            event: "graph.changed",
            change_type: "node_created",
            node_id: "t_1",
          }),
        }),
      );
    });

    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
  });
});
