import type { AnyNode, Edge, GraphState } from "../api/types";

export const initialGraphState: GraphState = { nodes: [], edges: [] };

export type GraphAction =
  | { type: "HYDRATE"; state: GraphState }
  | { type: "ADD_NODE"; node: AnyNode }
  | { type: "UPDATE_NODE"; node: AnyNode }
  | { type: "ADD_EDGE"; edge: Edge };

const edgeKey = (e: Edge) => `${e.from_id}::${e.to_id}::${e.edge_type}`;

export function graphReducer(state: GraphState, action: GraphAction): GraphState {
  switch (action.type) {
    case "HYDRATE":
      return action.state;
    case "ADD_NODE": {
      if (state.nodes.some((n) => n.id === action.node.id)) return state;
      return { ...state, nodes: [...state.nodes, action.node] };
    }
    case "UPDATE_NODE": {
      const idx = state.nodes.findIndex((n) => n.id === action.node.id);
      if (idx < 0) return state;
      const nodes = state.nodes.slice();
      nodes[idx] = action.node;
      return { ...state, nodes };
    }
    case "ADD_EDGE": {
      const key = edgeKey(action.edge);
      if (state.edges.some((e) => edgeKey(e) === key)) return state;
      return { ...state, edges: [...state.edges, action.edge] };
    }
    default:
      return state;
  }
}
