import { useState, useMemo } from "react";
import type { GraphState, AnyNode } from "../api/types";
import { GateCard } from "../components/GateCard";
import { computeHotSpots } from "../state/hotSpots";

type Tab = "gate" | "hot" | "recent";

export function MobileInboxView({
  state,
  onZoom,
}: {
  state: GraphState;
  onZoom: (nodeId: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("gate");

  const gateItems = useMemo(
    () =>
      state.nodes.filter(
        (n) => n.node_type === "gate_item" && n.resolved_at === null,
      ),
    [state.nodes],
  );

  const hotItems = useMemo(() => {
    const scores = computeHotSpots(state);
    return [...scores.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => state.nodes.find((n) => n.id === id))
      .filter((n): n is AnyNode => Boolean(n));
  }, [state]);

  const recentItems = useMemo(
    () =>
      [...state.nodes].sort(
        (a, b) => +new Date(b.created_at) - +new Date(a.created_at),
      ).slice(0, 30),
    [state.nodes],
  );

  return (
    <div className="flex flex-col h-full">
      <div role="tablist" className="flex border-b border-neutral-800">
        {(["gate", "hot", "recent"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`flex-1 py-2 text-sm capitalize ${
              tab === t
                ? "border-b-2 border-violet-500 text-violet-300"
                : "text-neutral-400"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <ul className="flex-1 overflow-y-auto p-3 space-y-2">
        {tab === "gate" &&
          gateItems.map((g) =>
            g.node_type === "gate_item" ? (
              <li key={g.id}>
                <GateCard gate={g} onZoom={onZoom} />
              </li>
            ) : null,
          )}

        {tab === "hot" &&
          hotItems.map((n) => (
            <li key={n.id}>
              <SimpleRow node={n} onZoom={onZoom} />
            </li>
          ))}

        {tab === "recent" &&
          recentItems.map((n) => (
            <li key={n.id}>
              <SimpleRow node={n} onZoom={onZoom} />
            </li>
          ))}
      </ul>
    </div>
  );
}

function SimpleRow({
  node,
  onZoom,
}: {
  node: AnyNode;
  onZoom: (id: string) => void;
}) {
  const label =
    "title" in node ? node.title
    : "summary" in node ? node.summary
    : "content" in node ? node.content.slice(0, 60)
    : "prompt" in node ? node.prompt
    : node.id;
  return (
    <button
      type="button"
      onClick={() => onZoom(node.id)}
      className="w-full text-left border border-neutral-800 bg-neutral-900 rounded p-3 hover:bg-neutral-800"
    >
      <div className="text-xs text-neutral-400 uppercase">{node.node_type}</div>
      <div className="text-sm">{label}</div>
    </button>
  );
}
