import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import GateItemList from "@/views/GateItemList";
import { GraphContext } from "@/state/GraphProvider";
import { api } from "@/api/client";

vi.mock("@/api/client", () => ({
  api: { resolveGateItem: vi.fn().mockResolvedValue({}) },
}));

const ctx = {
  nodes: [],
  edges: [],
  hotspots: [],
  gateItems: [
    { id: "g_1", prompt: "ship preview?", urgency: "high", created_at: "" },
  ],
  refresh: vi.fn().mockResolvedValue(undefined),
  selectionRequest: null,
  requestSelect: vi.fn(),
  clearSelectionRequest: vi.fn(),
};

describe("GateItemList", () => {
  it("calls resolveGateItem on Approve click", async () => {
    render(
      <GraphContext.Provider value={ctx as any}>
        <GateItemList />
      </GraphContext.Provider>,
    );
    fireEvent.click(screen.getByText("approve"));
    expect(api.resolveGateItem).toHaveBeenCalledWith("g_1", "approved", "");
  });
});
