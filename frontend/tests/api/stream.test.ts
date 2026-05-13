import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { subscribeToStream } from "../../src/api/stream";
import type { StreamEvent } from "../../src/api/types";

class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;
  closed = false;
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }
  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
  close() {
    this.closed = true;
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  // @ts-expect-error — install mock
  globalThis.EventSource = MockEventSource;
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("api/stream", () => {
  it("subscribeToStream opens an EventSource at /stream", () => {
    subscribeToStream(() => {});
    expect(MockEventSource.instances[0].url).toBe("/stream");
  });

  it("dispatches parsed StreamEvents to the handler", () => {
    const handler = vi.fn();
    subscribeToStream(handler);
    const event: StreamEvent = {
      event: "graph.changed",
      change_type: "node_created",
      node_id: "t_abc",
    };
    MockEventSource.instances[0].emit(event);
    expect(handler).toHaveBeenCalledWith(event);
  });

  it("returns a disposer that closes the source", () => {
    const dispose = subscribeToStream(() => {});
    dispose();
    expect(MockEventSource.instances[0].closed).toBe(true);
  });

  it("ignores keepalive comments (non-JSON messages)", () => {
    const handler = vi.fn();
    subscribeToStream(handler);
    MockEventSource.instances[0].onmessage?.(
      new MessageEvent("message", { data: ": keepalive" }),
    );
    expect(handler).not.toHaveBeenCalled();
  });
});
