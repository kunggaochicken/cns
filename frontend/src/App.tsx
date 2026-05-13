import { useState } from "react";
import { Routes, Route, Link } from "react-router-dom";
import { GraphProvider, useGraph } from "./state/GraphProvider";
import { TopBar } from "./components/TopBar";
import { CaptureBar } from "./components/CaptureBar";
import { DesktopGraphView } from "./views/DesktopGraphView";
import { MobileInboxView } from "./views/MobileInboxView";
import { NodeDetailPanel } from "./views/NodeDetailPanel";
import type { AnyNode } from "./api/types";

function DesktopShell() {
  const { state } = useGraph();
  const [selected, setSelected] = useState<AnyNode | null>(null);

  return (
    <div className="flex flex-col h-full">
      <TopBar state={state} />
      <div className="flex flex-1 overflow-hidden">
        <DesktopGraphView state={state} onNodeSelect={setSelected} />
        <NodeDetailPanel
          node={selected}
          onClose={() => setSelected(null)}
          onResolved={() => setSelected(null)}
        />
      </div>
      <CaptureBar />
    </div>
  );
}

function MobileShell() {
  const { state } = useGraph();
  const [selected, setSelected] = useState<AnyNode | null>(null);

  function onZoom(id: string) {
    setSelected(state.nodes.find((n) => n.id === id) ?? null);
  }

  return (
    <div className="flex flex-col h-full">
      <TopBar state={state} />
      <div className="flex flex-1 overflow-hidden">
        <MobileInboxView state={state} onZoom={onZoom} />
        <NodeDetailPanel
          node={selected}
          onClose={() => setSelected(null)}
          onResolved={() => setSelected(null)}
        />
      </div>
      <nav className="flex border-t border-neutral-800 bg-neutral-900">
        <Link to="/inbox" className="flex-1 py-3 text-center text-sm">
          inbox
        </Link>
        <Link to="/" className="flex-1 py-3 text-center text-sm">
          brain
        </Link>
      </nav>
      <CaptureBar />
    </div>
  );
}

export default function App() {
  return (
    <GraphProvider>
      <Routes>
        <Route path="/" element={<DesktopShell />} />
        <Route path="/inbox" element={<MobileShell />} />
      </Routes>
    </GraphProvider>
  );
}
