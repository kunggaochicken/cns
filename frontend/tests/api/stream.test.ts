import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useEventStream } from "@/api/stream";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
}

describe("useEventStream", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    (globalThis as any).EventSource = MockEventSource;
  });

  it("opens an EventSource on mount and closes on unmount", () => {
    const { unmount } = renderHook(() => useEventStream("/stream", () => {}));
    expect(MockEventSource.instances).toHaveLength(1);
    unmount();
    expect(MockEventSource.instances[0].closed).toBe(true);
  });

  it("delivers parsed JSON payloads to the callback", () => {
    const handler = vi.fn();
    renderHook(() => useEventStream("/stream", handler));
    const es = MockEventSource.instances[0];
    act(() => {
      es.onmessage?.(new MessageEvent("message", { data: '{"event":"graph.changed","node_id":"t_1"}' }));
    });
    expect(handler).toHaveBeenCalledWith({ event: "graph.changed", node_id: "t_1" });
  });
});
