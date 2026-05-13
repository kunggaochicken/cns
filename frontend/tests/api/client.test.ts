import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { fetchGraphState, fetchNodeDetail, postCapture } from "../../src/api/client";

const originalFetch = globalThis.fetch;

beforeEach(() => {
  globalThis.fetch = vi.fn();
});
afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe("api/client", () => {
  it("fetchGraphState GETs /api/graph/state", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [], edges: [] }),
    });
    const state = await fetchGraphState();
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/graph/state");
    expect(state).toEqual({ nodes: [], edges: [] });
  });

  it("fetchNodeDetail GETs /api/graph/nodes/:id", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ node_type: "bet", id: "b_x" }),
    });
    const node = await fetchNodeDetail("b_x");
    expect(globalThis.fetch).toHaveBeenCalledWith("/api/graph/nodes/b_x");
    expect(node.node_type).toBe("bet");
  });

  it("postCapture POSTs JSON to /api/capture", async () => {
    (globalThis.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ node_id: "t_x", status: "ok" }),
    });
    const res = await postCapture("a thought");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/capture",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(res.node_id).toBe("t_x");
  });

  it("throws on non-OK responses", async () => {
    (globalThis.fetch as any).mockResolvedValue({ ok: false, status: 500 });
    await expect(fetchGraphState()).rejects.toThrow(/500/);
  });
});
