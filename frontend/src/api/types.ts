export type NodeType =
  | "Thought"
  | "Bet"
  | "Task"
  | "Decision"
  | "Conflict"
  | "Outcome"
  | "AgentFiring"
  | "CodeChange"
  | "Conversation"
  | "Doc"
  | "GateItem";

export interface NodeRow {
  id: string;
  type: NodeType;
  created_at: string;
}

export interface EdgeRow {
  from_id: string;
  to_id: string;
  edge_type: string;
  created_at: string;
}

export interface NodeDetail {
  id: string;
  type: NodeType;
  props: Record<string, unknown>;
  outgoing_edges: { edge_type: string; to_id: string; confidence: number }[];
  incoming_edges: { edge_type: string; from_id: string; confidence: number }[];
}

export interface GateItem {
  id: string;
  prompt: string;
  urgency: "urgent" | "high" | "medium" | "novel" | "low" | string;
  created_at: string;
}

export interface HotSpot {
  id: string;
  type: NodeType;
  edge_count: number;
}

export type GateDecision = "approved" | "vetoed" | "resteered";
