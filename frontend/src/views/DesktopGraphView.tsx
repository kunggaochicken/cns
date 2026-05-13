import { useMemo, useRef, useEffect } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { AnyNode, GraphState } from "../api/types";
import { NODE_HEX } from "../lib/colors";
import { computeHotSpots } from "../state/hotSpots";

interface ForceNode {
  id: string;
  node_type: string;
  raw: AnyNode;
  val: number;
  color: string;
}

interface ForceLink {
  source: string;
  target: string;
}

export function DesktopGraphView({
  state,
  onNodeSelect,
}: {
  state: GraphState;
  onNodeSelect: (node: AnyNode) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  const graphData = useMemo(() => {
    const scores = computeHotSpots(state);
    const nodes: ForceNode[] = state.nodes.map((n) => ({
      id: n.id,
      node_type: n.node_type,
      raw: n,
      val: 1 + (scores.get(n.id) ?? 0) * 2,
      color: NODE_HEX[n.node_type],
    }));
    const links: ForceLink[] = state.edges.map((e) => ({
      source: e.from_id,
      target: e.to_id,
    }));
    return { nodes, links };
  }, [state]);

  const dimsRef = useRef({ width: 800, height: 600 });
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const resize = () => {
      dimsRef.current = { width: el.clientWidth, height: el.clientHeight };
    };
    resize();
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  return (
    <div ref={containerRef} className="flex-1 relative bg-neutral-950">
      <ForceGraph2D
        graphData={graphData}
        width={dimsRef.current.width}
        height={dimsRef.current.height}
        nodeRelSize={5}
        nodeColor={(n: any) => n.color}
        nodeVal={(n: any) => n.val}
        linkColor={() => "#525252"}
        backgroundColor="#0a0a0a"
        onNodeClick={(n: any) => onNodeSelect(n.raw as AnyNode)}
      />
    </div>
  );
}
