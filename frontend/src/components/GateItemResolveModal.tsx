import { useState } from "react";
import type { GateDecision } from "@/api/types";

interface Props {
  decision: GateDecision;
  onSubmit: (reasoning: string) => Promise<void>;
  onClose: () => void;
}

export default function GateItemResolveModal({ decision, onSubmit, onClose }: Props) {
  const [reasoning, setReasoning] = useState("");
  const [submitting, setSubmitting] = useState(false);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-96 rounded border border-gray-700 bg-gray-900 p-4">
        <h2 className="mb-2 text-sm font-semibold text-gray-200">
          {decision.toUpperCase()} — reasoning
        </h2>
        <textarea
          className="h-24 w-full rounded border border-gray-700 bg-gray-800 p-2 text-sm text-gray-100"
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value)}
          placeholder="why?"
        />
        <div className="mt-3 flex justify-end gap-2 text-sm">
          <button onClick={onClose} className="rounded bg-gray-700 px-3 py-1 text-gray-100">
            cancel
          </button>
          <button
            onClick={async () => {
              setSubmitting(true);
              try {
                await onSubmit(reasoning);
                onClose();
              } finally {
                setSubmitting(false);
              }
            }}
            disabled={submitting}
            className="rounded bg-purple-500 px-3 py-1 text-white disabled:opacity-50"
          >
            confirm
          </button>
        </div>
      </div>
    </div>
  );
}
