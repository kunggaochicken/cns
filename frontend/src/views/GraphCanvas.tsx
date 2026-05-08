import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import { useGraph } from "@/state/useGraph";
import { colorForType } from "@/utils/nodeColors";
import type { NodeType } from "@/api/types";

interface Props {
  onSelectNode: (table: NodeType, id: string) => void;
}

export default function GraphCanvas({ onSelectNode }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const { nodes, edges, hotspots, gateItems } = useGraph();

  // Initialize once
  useEffect(() => {
    if (!hostRef.current) return;
    cyRef.current = cytoscape({
      container: hostRef.current,
      elements: [],
      layout: { name: "cose" },
      // Cast the style sheet because @types/cytoscape omits shadow-* keys that
      // the runtime canvas renderer supports.
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#e5e7eb",
            "font-size": 9,
            width: 20,
            height: 20,
          },
        },
        {
          selector: "node[?hot]",
          style: {
            "border-color": "#f97316",
            "border-width": 4,
            "shadow-color": "#f97316",
            "shadow-blur": 18,
            "shadow-opacity": 0.7,
          },
        },
        {
          selector: "node[?gate]",
          style: {
            "border-color": "#fbbf24",
            "border-width": 3,
          },
        },
        {
          selector: "edge",
          style: {
            "line-color": "#4b5563",
            "target-arrow-color": "#4b5563",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            width: 1,
          },
        },
      ] as cytoscape.StylesheetStyle[],
    });

    cyRef.current.on("tap", "node", (evt) => {
      const data = evt.target.data();
      onSelectNode(data.nodeType as NodeType, data.id);
    });

    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, [onSelectNode]);

  // Sync data when graph state changes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const hotIds = new Set(hotspots.map((h) => h.id));
    const gateIds = new Set(gateItems.map((g) => g.id));
    const cyElements = [
      ...nodes.map((n) => ({
        data: {
          id: n.id,
          label: `${n.type[0]} ${n.id.slice(-4)}`,
          color: colorForType(n.type),
          nodeType: n.type,
          hot: hotIds.has(n.id) ? 1 : 0,
          gate: gateIds.has(n.id) ? 1 : 0,
        },
      })),
      ...edges.map((e) => ({
        data: {
          id: `${e.from_id}->${e.to_id}->${e.edge_type}`,
          source: e.from_id,
          target: e.to_id,
        },
      })),
    ];
    cy.json({ elements: cyElements });
    cy.layout({ name: "cose", animate: false }).run();
  }, [nodes, edges, hotspots, gateItems]);

  return (
    <div
      ref={hostRef}
      data-testid="cy-host"
      className="h-full w-full"
    />
  );
}
