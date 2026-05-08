import { useEffect } from "react";

export type StreamEvent =
  | { event: "graph.changed"; change_type: string; node_id?: string; edge_id?: string }
  | { event: "gate.created"; gate_item_id: string; thought_id: string; urgency: string }
  | { event: "fire.neuron"; thought_id: string; agent_role: string; task_summary: string };

export function useEventStream(url: string, onEvent: (e: StreamEvent) => void) {
  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as StreamEvent;
        onEvent(parsed);
      } catch {
        // Ignore non-JSON keepalive comments
      }
    };
    es.onerror = () => {
      // Browser auto-reconnects; nothing special needed
    };
    return () => es.close();
  }, [url, onEvent]);
}
