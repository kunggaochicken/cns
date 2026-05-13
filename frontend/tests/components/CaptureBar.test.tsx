import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CaptureBar } from "../../src/components/CaptureBar";

beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ node_id: "t_x", status: "ok" }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("CaptureBar", () => {
  it("POSTs the input value when Enter is pressed", async () => {
    const user = userEvent.setup();
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/capture a thought/i);
    await user.type(input, "build the brain view{Enter}");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/capture",
      expect.objectContaining({ method: "POST" }),
    );
    const callBody = JSON.parse((globalThis.fetch as any).mock.calls[0][1].body);
    expect(callBody).toEqual({ content: "build the brain view", source: "web" });
  });

  it("clears the input after a successful submit", async () => {
    const user = userEvent.setup();
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/capture a thought/i) as HTMLInputElement;
    await user.type(input, "hi{Enter}");
    expect(input.value).toBe("");
  });

  it("does not POST empty input", async () => {
    const user = userEvent.setup();
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/capture a thought/i);
    await user.type(input, "   {Enter}");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
