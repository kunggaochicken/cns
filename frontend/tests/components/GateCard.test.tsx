import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GateCard } from "../../src/components/GateCard";
import type { GateItemNode } from "../../src/api/types";

const gate: GateItemNode = {
  node_type: "gate_item",
  id: "g_1",
  prompt: "Approve dispatch?",
  urgency: "urgent",
  resolved_at: null,
  decision: null,
  reasoning: "",
  created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
};

describe("GateCard", () => {
  it("shows the prompt and urgency", () => {
    render(<GateCard gate={gate} onZoom={() => {}} />);
    expect(screen.getByText("Approve dispatch?")).toBeInTheDocument();
    expect(screen.getByText(/urgent/i)).toBeInTheDocument();
  });

  it("zoom button fires onZoom with gate id", async () => {
    const onZoom = vi.fn();
    const user = userEvent.setup();
    render(<GateCard gate={gate} onZoom={onZoom} />);
    await user.click(screen.getByRole("button", { name: /zoom/i }));
    expect(onZoom).toHaveBeenCalledWith("g_1");
  });
});
