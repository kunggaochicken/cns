import { useState } from "react";
import TopBar from "./TopBar";
import GraphCanvas from "./GraphCanvas";
import NodeDetail from "./NodeDetail";
import CaptureBar from "./CaptureBar";
import GateItemList from "./GateItemList";
import type { NodeType } from "@/api/types";

export default function BrainView() {
  const [selected, setSelected] = useState<{ table: NodeType; id: string } | null>(null);
  return (
    <div className="flex h-screen flex-col bg-gray-950">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1">
          <GraphCanvas onSelectNode={(table, id) => setSelected({ table, id })} />
        </main>
        <aside className="flex w-80 flex-col gap-4 overflow-y-auto border-l border-gray-800 bg-gray-900 p-4">
          <GateItemList />
          <hr className="border-gray-800" />
          <NodeDetail
            table={selected?.table ?? null}
            nodeId={selected?.id ?? null}
          />
        </aside>
      </div>
      <CaptureBar />
    </div>
  );
}
