import { useState } from "react";
import type { GateItemNode } from "../api/types";
import { postGateResolve } from "../api/client";

type Decision = "approved" | "vetoed" | "resteered";

export function GateResolvePanel({
  gate,
  onResolved,
}: {
  gate: GateItemNode;
  onResolved: () => void;
}) {
  const [reasoning, setReasoning] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(decision: Decision) {
    setBusy(true);
    try {
      await postGateResolve(gate.id, { decision, reasoning });
      onResolved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 space-y-3">
      <h2 className="text-lg font-semibold">{gate.prompt}</h2>
      <div className="text-xs uppercase tracking-wider text-yellow-300">
        urgency: {gate.urgency}
      </div>
      <textarea
        placeholder="reasoning…"
        value={reasoning}
        onChange={(e) => setReasoning(e.target.value)}
        className="w-full bg-neutral-800 text-neutral-100 placeholder-neutral-500 px-3 py-2 rounded outline-none focus:ring-2 focus:ring-violet-500 min-h-[6rem]"
      />
      <div className="flex gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("approved")}
          className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50"
        >
          approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("vetoed")}
          className="px-3 py-1.5 rounded bg-rose-600 hover:bg-rose-500 disabled:opacity-50"
        >
          veto
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => decide("resteered")}
          className="px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 disabled:opacity-50"
        >
          resteer
        </button>
      </div>
    </div>
  );
}
