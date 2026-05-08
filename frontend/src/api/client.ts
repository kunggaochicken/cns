import type {
  NodeRow,
  EdgeRow,
  NodeDetail,
  GateItem,
  HotSpot,
  GateDecision,
  NodeType,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    throw new Error(`API ${path} returned ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  async getGraph(
    types?: NodeType[],
    limit = 2000,
  ): Promise<{ nodes: NodeRow[]; edges: EdgeRow[] }> {
    const params = new URLSearchParams();
    if (types?.length) params.set("types", types.join(","));
    params.set("limit", String(limit));
    return request(`/graph?${params}`);
  },

  async getNode(table: NodeType, id: string): Promise<NodeDetail> {
    return request(`/nodes/${table}/${encodeURIComponent(id)}`);
  },

  async getGateItems(): Promise<GateItem[]> {
    return request("/gate-items");
  },

  async resolveGateItem(
    id: string,
    decision: GateDecision,
    reasoning = "",
  ): Promise<{ id: string; decision: string; resolved_at: string }> {
    return request(`/gate-items/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ decision, reasoning }),
    });
  },

  async getHotspots(limit = 10, withinHours = 1): Promise<HotSpot[]> {
    const params = new URLSearchParams({
      limit: String(limit),
      within_hours: String(withinHours),
    });
    return request(`/hotspots?${params}`);
  },

  async capture(input: {
    content: string;
    source: string;
    metadata?: Record<string, unknown>;
  }): Promise<{ node_id: string; status: string }> {
    return request("/capture", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },
};
