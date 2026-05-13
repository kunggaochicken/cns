import { createContext, useContext, useEffect, useReducer } from "react";
import type { ReactNode } from "react";
import { fetchGraphState, fetchNodeDetail } from "../api/client";
import { subscribeToStream } from "../api/stream";
import {
  graphReducer,
  initialGraphState,
  type GraphAction,
} from "./graph";
import type { GraphState, AnyNode } from "../api/types";

interface GraphContextValue {
  state: GraphState;
  dispatch: React.Dispatch<GraphAction>;
}

const GraphContext = createContext<GraphContextValue | null>(null);

export function GraphProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(graphReducer, initialGraphState);

  useEffect(() => {
    let cancelled = false;
    fetchGraphState().then((snapshot) => {
      if (!cancelled) dispatch({ type: "HYDRATE", state: snapshot });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const dispose = subscribeToStream(async (event) => {
      if (event.event !== "graph.changed") return;
      if (event.change_type === "node_created" && event.node_id) {
        const node = (await fetchNodeDetail(event.node_id)) as AnyNode;
        dispatch({ type: "ADD_NODE", node });
      } else if (event.change_type === "node_updated" && event.node_id) {
        const node = (await fetchNodeDetail(event.node_id)) as AnyNode;
        dispatch({ type: "UPDATE_NODE", node });
      }
    });
    return dispose;
  }, []);

  return (
    <GraphContext.Provider value={{ state, dispatch }}>
      {children}
    </GraphContext.Provider>
  );
}

export function useGraph(): GraphContextValue {
  const ctx = useContext(GraphContext);
  if (!ctx) throw new Error("useGraph must be used inside GraphProvider");
  return ctx;
}
