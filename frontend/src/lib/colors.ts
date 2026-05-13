import type { NodeType } from "../api/types";

export const NODE_HEX: Record<NodeType, string> = {
  thought: "#34d399",
  bet: "#a78bfa",
  task: "#fb923c",
  decision: "#94a3b8",
  conflict: "#ef4444",
  outcome: "#22c55e",
  agent_firing: "#c084fc",
  code_change: "#60a5fa",
  conversation: "#fde68a",
  doc: "#93c5fd",
  gate_item: "#facc15",
  agent: "#f472b6",
};

export const NODE_TAILWIND_BG: Record<NodeType, string> = {
  thought: "bg-thought",
  bet: "bg-bet",
  task: "bg-orange-400",
  decision: "bg-slate-400",
  conflict: "bg-conflict",
  outcome: "bg-green-500",
  agent_firing: "bg-firing",
  code_change: "bg-codechange",
  conversation: "bg-yellow-200",
  doc: "bg-doc",
  gate_item: "bg-gate",
  agent: "bg-pink-400",
};
