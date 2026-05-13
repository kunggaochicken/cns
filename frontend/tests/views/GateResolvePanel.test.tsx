import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GateResolvePanel } from "../../src/views/GateResolvePanel";
import type { GateItemNode } from "../../src/api/types";

const gate: GateItemNode = {
  node_type: "gate_item",
  id: "g_1",
  prompt: "Approve dispatch?",
  urgency: "urgent",
  resolved_at: null,
  decision: null,
  reasoning: "",
  created_at: "2026-05-12T00:00:00Z",
};

beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "ok" }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("GateResolvePanel", () => {
  it("renders the prompt", () => {
    render(<GateResolvePanel gate={gate} onResolved={() => {}} />);
    expect(screen.getByText("Approve dispatch?")).toBeInTheDocument();
  });

  it("approve POSTs decision and calls onResolved", async () => {
    const onResolved = vi.fn();
    const user = userEvent.setup();
    render(<GateResolvePanel gate={gate} onResolved={onResolved} />);
    await user.type(screen.getByPlaceholderText(/reasoning/i), "looks fine");
    await user.click(screen.getByRole("button", { name: /approve/i }));
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/gate/g_1/resolve",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse((globalThis.fetch as any).mock.calls[0][1].body);
    expect(body).toMatchObject({ decision: "approved", reasoning: "looks fine" });
    expect(onResolved).toHaveBeenCalled();
  });

  it("veto button sends decision=vetoed", async () => {
    const user = userEvent.setup();
    render(<GateResolvePanel gate={gate} onResolved={() => {}} />);
    await user.click(screen.getByRole("button", { name: /veto/i }));
    const body = JSON.parse((globalThis.fetch as any).mock.calls[0][1].body);
    expect(body.decision).toBe("vetoed");
  });
});
