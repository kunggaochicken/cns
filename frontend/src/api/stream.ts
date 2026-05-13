import type { StreamEvent } from "./types";

export type StreamHandler = (event: StreamEvent) => void;

export function subscribeToStream(handler: StreamHandler): () => void {
  const source = new EventSource("/stream");

  source.onmessage = (e) => {
    const raw = e.data;
    if (typeof raw !== "string" || !raw.trim().startsWith("{")) {
      return;
    }
    try {
      handler(JSON.parse(raw) as StreamEvent);
    } catch {
      return;
    }
  };

  return () => source.close();
}
