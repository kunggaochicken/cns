import type { AnyNode, GraphState } from "./types";

const BASE = "";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

export function fetchGraphState() {
  return getJSON<GraphState>("/graph/state");
}

export function fetchNodeDetail(id: string) {
  return getJSON<AnyNode & { edges_in: unknown[]; edges_out: unknown[] }>(
    `/graph/nodes/${id}`,
  );
}

export interface CaptureResponse {
  node_id: string;
  status: string;
}

export function postCapture(content: string, source: string = "web") {
  return postJSON<CaptureResponse>("/capture", { content, source });
}

export interface GateResolveRequest {
  decision: "approved" | "vetoed" | "resteered";
  reasoning: string;
  alternative?: string | null;
}

export function postGateResolve(gateId: string, body: GateResolveRequest) {
  return postJSON<{ status: string }>(`/gate/${gateId}/resolve`, body);
}
