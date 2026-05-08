import { useState } from "react";
import { api } from "@/api/client";

export default function CaptureBar() {
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmed = content.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await api.capture({ content: trimmed, source: "web" });
      setContent("");
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2 border-t border-gray-800 bg-gray-900 p-2">
      <span className="text-green-400">💭</span>
      <input
        className="flex-1 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-100 placeholder-gray-500 focus:border-purple-400 focus:outline-none"
        placeholder="dump a thought..."
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
        disabled={busy}
      />
      <button
        onClick={() => void submit()}
        disabled={busy}
        className="rounded bg-purple-500 px-3 py-1 text-sm text-white disabled:opacity-50"
      >
        spar →
      </button>
    </div>
  );
}
