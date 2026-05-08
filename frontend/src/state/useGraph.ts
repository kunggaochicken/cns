import { useContext } from "react";
import { GraphContext } from "./GraphProvider";

export function useGraph() {
  const ctx = useContext(GraphContext);
  if (!ctx) throw new Error("useGraph must be used inside <GraphProvider>");
  return ctx;
}
