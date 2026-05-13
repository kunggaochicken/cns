import { useState } from "react";
import { postCapture } from "../api/client";

export function CaptureBar() {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await postCapture(trimmed);
      setValue("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-t border-neutral-800 bg-neutral-900 p-3">
      <input
        type="text"
        placeholder="Capture a thought…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void submit();
          }
        }}
        disabled={busy}
        className="w-full bg-neutral-800 text-neutral-100 placeholder-neutral-500 px-3 py-2 rounded outline-none focus:ring-2 focus:ring-violet-500"
      />
    </div>
  );
}
