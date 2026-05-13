import type { NodeType } from "../api/types";
import { NODE_TAILWIND_BG } from "../lib/colors";

export function NodeBadge({ type }: { type: NodeType }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-medium text-neutral-900 ${NODE_TAILWIND_BG[type]}`}
    >
      {type.replace("_", " ")}
    </span>
  );
}
