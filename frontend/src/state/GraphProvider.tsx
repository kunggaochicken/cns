import {
  createContext,
  ReactNode,
  useCallback,
  useEffect,
  useState,
} from "react";
import { api } from "@/api/client";
import { useEventStream, StreamEvent } from "@/api/stream";
import type { NodeRow, EdgeRow, GateItem, HotSpot, NodeType } from "@/api/types";

interface GraphState {
  nodes: NodeRow[];
  edges: EdgeRow[];
  gateItems: GateItem[];
  hotspots: HotSpot[];
  refresh: () => Promise<void>;
  selectionRequest: { table: NodeType; id: string } | null;
  requestSelect: (table: NodeType, id: string) => void;
  clearSelectionRequest: () => void;
}

export const GraphContext = createContext<GraphState | null>(null);

export function GraphProvider({ children }: { children: ReactNode }) {
  const [nodes, setNodes] = useState<NodeRow[]>([]);
  const [edges, setEdges] = useState<EdgeRow[]>([]);
  const [gateItems, setGateItems] = useState<GateItem[]>([]);
  const [hotspots, setHotspots] = useState<HotSpot[]>([]);
  const [selectionRequest, setSelectionRequest] = useState<{
    table: NodeType;
    id: string;
  } | null>(null);

  const requestSelect = useCallback(
    (table: NodeType, id: string) => setSelectionRequest({ table, id }),
    [],
  );
  const clearSelectionRequest = useCallback(
    () => setSelectionRequest(null),
    [],
  );

  const refresh = useCallback(async () => {
    const [g, gi, hs] = await Promise.all([
      api.getGraph(),
      api.getGateItems(),
      api.getHotspots(),
    ]);
    setNodes(g.nodes);
    setEdges(g.edges);
    setGateItems(gi);
    setHotspots(hs);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onEvent = useCallback(
    (event: StreamEvent) => {
      if (event.event === "graph.changed") {
        void refresh();
      } else if (event.event === "gate.created") {
        void api.getGateItems().then(setGateItems);
      }
    },
    [refresh],
  );
  useEventStream("/stream", onEvent);

  return (
    <GraphContext.Provider
      value={{
        nodes,
        edges,
        gateItems,
        hotspots,
        refresh,
        selectionRequest,
        requestSelect,
        clearSelectionRequest,
      }}
    >
      {children}
    </GraphContext.Provider>
  );
}
