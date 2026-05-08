import { useGraph } from "@/state/useGraph";

export default function TopBar() {
  const { gateItems, hotspots } = useGraph();
  return (
    <div className="flex items-center justify-between border-b border-gray-800 bg-gray-900 px-4 py-2">
      <div className="text-sm font-bold text-purple-300">🧠 GigaBrain</div>
      <div className="flex gap-2 text-xs">
        <span className="rounded-full border border-yellow-400 bg-yellow-900/30 px-2 py-0.5 text-yellow-300">
          ⚡ {gateItems.length} gate items
        </span>
        <span className="rounded-full border border-orange-400 bg-orange-900/30 px-2 py-0.5 text-orange-300">
          🔥 {hotspots.length} hot spots
        </span>
      </div>
    </div>
  );
}
