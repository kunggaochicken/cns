import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { NodeDetail as NodeDetailT, NodeType } from "@/api/types";

interface Props {
  table: NodeType | null;
  nodeId: string | null;
}

export default function NodeDetail({ table, nodeId }: Props) {
  const [data, setData] = useState<NodeDetailT | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!table || !nodeId) {
      setData(null);
      return;
    }
    setError(null);
    setData(null);
    api
      .getNode(table, nodeId)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, [table, nodeId]);

  if (!table || !nodeId) return <div className="text-xs text-gray-500">(select a node)</div>;
  if (error) return <div className="text-xs text-red-400">{error}</div>;
  if (!data) return <div className="text-xs text-gray-500">loading…</div>;

  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <span className="rounded bg-gray-800 px-1.5 py-0.5 text-gray-300">{data.type}</span>
        <span className="text-gray-500">{data.id}</span>
      </div>
      <pre className="whitespace-pre-wrap break-words rounded bg-gray-950 p-2 text-gray-300">
        {JSON.stringify(data.props, null, 2)}
      </pre>
      {data.outgoing_edges.length > 0 && (
        <div>
          <div className="mb-1 text-gray-400 uppercase">→ outgoing</div>
          {data.outgoing_edges.map((e, i) => (
            <div key={i} className="font-mono text-gray-300">
              [{e.edge_type}] → {e.to_id}
            </div>
          ))}
        </div>
      )}
      {data.incoming_edges.length > 0 && (
        <div>
          <div className="mb-1 text-gray-400 uppercase">← incoming</div>
          {data.incoming_edges.map((e, i) => (
            <div key={i} className="font-mono text-gray-300">
              {e.from_id} → [{e.edge_type}]
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
