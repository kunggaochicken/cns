import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "@/api/client";

describe("api client", () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it("getGraph fetches /graph and returns parsed body", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        nodes: [{ id: "t_1", type: "Thought", created_at: "" }],
        edges: [],
      }),
    });
    const res = await api.getGraph();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/^\/graph/),
      expect.anything(),
    );
    expect(res.nodes).toHaveLength(1);
  });

  it("capture posts to /capture with body", async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ node_id: "t_x", status: "sparring" }),
    });
    await api.capture({ content: "hi", source: "web" });
    const call = (fetch as any).mock.calls[0];
    expect(call[0]).toBe("/capture");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toMatchObject({
      content: "hi",
      source: "web",
    });
  });

  it("throws on non-ok response", async () => {
    (fetch as any).mockResolvedValueOnce({ ok: false, status: 500 });
    await expect(api.getGraph()).rejects.toThrow();
  });
});
