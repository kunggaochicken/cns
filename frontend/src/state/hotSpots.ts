import type { GraphState } from "../api/types";

export const HOT_SPOT_WEIGHTS = {
  conflict: 2.5,
  gate_urgent: 3.0,
  gate_medium: 1.5,
  gate_novel: 0.5,
  degree: 0.2,
} as const;

export function computeHotSpots(state: GraphState): Map<string, number> {
  const degree = new Map<string, number>();
  for (const e of state.edges) {
    degree.set(e.from_id, (degree.get(e.from_id) ?? 0) + 1);
    degree.set(e.to_id, (degree.get(e.to_id) ?? 0) + 1);
  }

  const scores = new Map<string, number>();
  for (const node of state.nodes) {
    let score = 0;
    if (node.node_type === "conflict") {
      score += HOT_SPOT_WEIGHTS.conflict;
      if (node.severity === "high") score += 1;
    } else if (node.node_type === "gate_item") {
      if (node.resolved_at !== null) continue;
      if (node.urgency === "urgent") score += HOT_SPOT_WEIGHTS.gate_urgent;
      else if (node.urgency === "medium") score += HOT_SPOT_WEIGHTS.gate_medium;
      else score += HOT_SPOT_WEIGHTS.gate_novel;
    } else {
      continue;
    }
    score += (degree.get(node.id) ?? 0) * HOT_SPOT_WEIGHTS.degree;
    scores.set(node.id, score);
  }
  return scores;
}
