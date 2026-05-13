import type { AnyNode } from "../api/types";
import { resolveZoomIn } from "../lib/zoomIn";
import { NodeBadge } from "../components/NodeBadge";
import { GateResolvePanel } from "./GateResolvePanel";

export function NodeDetailPanel({
  node,
  onClose,
  onResolved,
}: {
  node: AnyNode | null;
  onClose: () => void;
  onResolved: () => void;
}) {
  if (!node) return null;

  const zoom = resolveZoomIn(node);
  const title = headline(node);

  return (
    <aside className="w-96 h-full bg-neutral-900 border-l border-neutral-800 overflow-y-auto">
      <header className="flex items-center justify-between p-3 border-b border-neutral-800">
        <NodeBadge type={node.node_type} />
        <button
          type="button"
          onClick={onClose}
          aria-label="close"
          className="text-neutral-400 hover:text-neutral-100"
        >
          ✕
        </button>
      </header>

      {node.node_type === "gate_item" ? (
        <GateResolvePanel gate={node} onResolved={onResolved} />
      ) : (
        <div className="p-4 space-y-3">
          <h2 className="text-lg font-semibold">{title}</h2>
          <pre className="text-xs bg-neutral-950 p-3 rounded whitespace-pre-wrap break-words">
            {JSON.stringify(node, null, 2)}
          </pre>
          {zoom.kind === "external" && (
            <a
              href={zoom.href}
              target="_blank"
              rel="noreferrer"
              className="inline-block px-3 py-1.5 rounded bg-violet-600 hover:bg-violet-500"
            >
              open in {externalLabel(node)}
            </a>
          )}
        </div>
      )}
    </aside>
  );
}

function headline(node: AnyNode): string {
  switch (node.node_type) {
    case "bet": return node.title;
    case "task": return node.title;
    case "thought": return node.content.slice(0, 80);
    case "decision": return node.content.slice(0, 80);
    case "conflict": return node.summary;
    case "outcome": return node.summary;
    case "code_change": return node.summary;
    case "conversation": return node.summary;
    case "doc": return node.title;
    case "gate_item": return node.prompt;
    case "agent_firing": return `firing ${node.id}`;
    case "agent": return node.role;
  }
}

function externalLabel(node: AnyNode): string {
  switch (node.node_type) {
    case "bet": return "Obsidian";
    case "task": return "Linear";
    case "code_change": return "GitHub";
    default: return "external";
  }
}
