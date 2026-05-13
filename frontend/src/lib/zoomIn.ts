import type { AnyNode } from "../api/types";

export type ZoomDestination =
  | { kind: "external"; href: string }
  | { kind: "panel"; panel: "gate" | "conflict" | "detail"; nodeId: string };

export function resolveZoomIn(node: AnyNode): ZoomDestination {
  switch (node.node_type) {
    case "bet":
      return {
        kind: "external",
        href: `obsidian://open?path=${encodeURIComponent(node.vault_path)}`,
      };
    case "task":
      return {
        kind: "external",
        href: `https://linear.app/gigaflow/issue/${node.linear_id}`,
      };
    case "code_change":
      return {
        kind: "external",
        href: `https://github.com/${node.repo}/commit/${node.sha}`,
      };
    case "gate_item":
      return { kind: "panel", panel: "gate", nodeId: node.id };
    case "conflict":
      return { kind: "panel", panel: "conflict", nodeId: node.id };
    default:
      return { kind: "panel", panel: "detail", nodeId: node.id };
  }
}
