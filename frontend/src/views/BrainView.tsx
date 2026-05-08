import TopBar from "./TopBar";

export default function BrainView() {
  return (
    <div className="flex h-screen flex-col bg-gray-950">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 bg-gray-950 p-4 text-gray-500">
          (graph canvas placeholder — Task 11)
        </main>
        <aside className="w-80 border-l border-gray-800 bg-gray-900 p-4 text-gray-500">
          (node detail placeholder — Task 12)
        </aside>
      </div>
      <div className="border-t border-gray-800 bg-gray-900 p-2 text-gray-500">
        (capture bar placeholder — Task 15)
      </div>
    </div>
  );
}
