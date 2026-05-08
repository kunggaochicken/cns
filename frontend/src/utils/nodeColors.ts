import type { NodeType } from "@/api/types";

export const NODE_COLORS: Record<NodeType, string> = {
  Thought: "#4ade80",
  Bet: "#a855f7",
  Task: "#94a3b8",
  Decision: "#22c55e",
  Conflict: "#f87171",
  Outcome: "#34d399",
  AgentFiring: "#ec4899",
  CodeChange: "#60a5fa",
  Conversation: "#fbbf24",
  Doc: "#818cf8",
  GateItem: "#fbbf24",
};

export function colorForType(type: NodeType): string {
  return NODE_COLORS[type] ?? "#9ca3af";
}
