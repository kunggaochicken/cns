import type { GateItemNode } from "../api/types";
import { ageLabel } from "../lib/time";

export function GateCard({
  gate,
  onZoom,
}: {
  gate: GateItemNode;
  onZoom: (id: string) => void;
}) {
  return (
    <div className="border border-neutral-800 bg-neutral-900 rounded p-3 space-y-2">
      <div className="flex justify-between text-xs">
        <span className="uppercase tracking-wider text-yellow-300">
          {gate.urgency}
        </span>
        <span className="text-neutral-500">{ageLabel(gate.created_at)}</span>
      </div>
      <p className="text-sm">{gate.prompt}</p>
      <button
        type="button"
        onClick={() => onZoom(gate.id)}
        className="px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-xs"
      >
        zoom
      </button>
    </div>
  );
}
