import { useState } from "react";
import { api } from "@/api/client";
import { useGraph } from "@/state/useGraph";
import GateItemResolveModal from "@/components/GateItemResolveModal";
import type { GateDecision } from "@/api/types";

export default function GateItemList() {
  const { gateItems, refresh } = useGraph();
  const [pendingDecision, setPendingDecision] = useState<{
    id: string;
    decision: GateDecision;
  } | null>(null);

  async function quickResolve(id: string, decision: GateDecision) {
    await api.resolveGateItem(id, decision, "");
    await refresh();
  }

  return (
    <div className="space-y-2">
      <div className="text-xs uppercase text-gray-400">
        ⚡ gate items ({gateItems.length})
      </div>
      {gateItems.length === 0 && (
        <div className="text-xs text-gray-500">(none pending)</div>
      )}
      {gateItems.map((g) => (
        <div
          key={g.id}
          className="rounded border border-yellow-500/30 bg-yellow-900/10 p-2"
        >
          <div className="text-xs text-gray-400">{g.urgency}</div>
          <div className="mb-2 text-sm text-gray-100">{g.prompt}</div>
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => quickResolve(g.id, "approved")}
              className="rounded border border-green-500 px-2 py-0.5 text-green-400"
            >
              approve
            </button>
            <button
              onClick={() => quickResolve(g.id, "vetoed")}
              className="rounded border border-red-500 px-2 py-0.5 text-red-400"
            >
              veto
            </button>
            <button
              onClick={() =>
                setPendingDecision({ id: g.id, decision: "resteered" })
              }
              className="rounded border border-gray-500 px-2 py-0.5 text-gray-300"
            >
              resteer
            </button>
          </div>
        </div>
      ))}
      {pendingDecision && (
        <GateItemResolveModal
          decision={pendingDecision.decision}
          onClose={() => setPendingDecision(null)}
          onSubmit={async (reasoning) => {
            await api.resolveGateItem(
              pendingDecision.id,
              pendingDecision.decision,
              reasoning,
            );
            await refresh();
          }}
        />
      )}
    </div>
  );
}
