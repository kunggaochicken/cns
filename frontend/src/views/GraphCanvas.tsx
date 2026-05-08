import { useEffect, useRef, useState } from "react";
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
  const {
    nodes,
    edges,
    hotspots,
    gateItems,
    selectionRequest,
    clearSelectionRequest,
  } = useGraph();
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const prevIdsRef = useRef<Set<string>>(new Set());

  // Track newly-arrived nodes across renders so we can briefly glow them.
  useEffect(() => {
    const currentIds = new Set(nodes.map((n) => n.id));
    const additions = nodes
      .filter((n) => !prevIdsRef.current.has(n.id))
      .map((n) => n.id);
    if (additions.length > 0) {
      setNewIds((s) => new Set([...s, ...additions]));
      window.setTimeout(() => {
        setNewIds((s) => {
          const next = new Set(s);
          for (const id of additions) next.delete(id);
          return next;
        });
      }, 2000);
    }
    prevIdsRef.current = currentIds;
  }, [nodes]);

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
          selector: "node[?new]",
          style: {
            "border-color": "#a855f7",
            "border-width": 6,
            "shadow-color": "#a855f7",
            "shadow-blur": 24,
            "shadow-opacity": 0.9,
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
          new: newIds.has(n.id) ? 1 : 0,
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
  }, [nodes, edges, hotspots, gateItems, newIds]);

  // React to cross-component selection requests (e.g. GateItemList click-through).
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !selectionRequest) return;
    const node = cy.getElementById(selectionRequest.id);
    if (node && node.length > 0) {
      cy.center(node);
      cy.animate({ fit: { eles: node, padding: 60 } }, { duration: 300 });
      onSelectNode(selectionRequest.table, selectionRequest.id);
    }
    clearSelectionRequest();
  }, [selectionRequest, clearSelectionRequest, onSelectNode]);

  // Pulse hot-node shadow opacity at 20fps for visual emphasis.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    let phase = 0;
    const id = window.setInterval(() => {
      phase = (phase + 1) % 60;
      const factor = 0.7 + 0.3 * Math.abs(Math.sin((phase / 60) * Math.PI * 2));
      cy.nodes("[?hot]").style({ "shadow-opacity": factor } as Record<string, unknown>);
    }, 50);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div
      ref={hostRef}
      data-testid="cy-host"
      className="h-full w-full"
    />
  );
}
