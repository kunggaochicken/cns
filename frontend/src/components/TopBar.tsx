import type { GraphState } from "../api/types";
import { computeHotSpots } from "../state/hotSpots";

export function TopBar({ state }: { state: GraphState }) {
  const openGateCount = state.nodes.filter(
    (n) => n.node_type === "gate_item" && n.resolved_at === null,
  ).length;
  const hotSpotCount = computeHotSpots(state).size;
  return (
    <div className="flex items-center gap-6 px-4 h-12 border-b border-neutral-800 bg-neutral-900">
      <span className="font-semibold">GigaBrain</span>
      <span className="text-yellow-300">⚡ {openGateCount} gate items</span>
      <span className="text-red-300">🔥 {hotSpotCount} hot spots</span>
    </div>
  );
}
