import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import CaptureBar from "@/views/CaptureBar";
import { api } from "@/api/client";

vi.mock("@/api/client", () => ({
  api: { capture: vi.fn() },
}));

describe("CaptureBar", () => {
  beforeEach(() => { vi.mocked(api.capture).mockReset(); });

  it("submits content on Enter", async () => {
    vi.mocked(api.capture).mockResolvedValueOnce({ node_id: "t_1", status: "sparring" });
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/dump a thought/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "ship oauth" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(api.capture).toHaveBeenCalledWith({ content: "ship oauth", source: "web" });
  });

  it("clears input on success", async () => {
    vi.mocked(api.capture).mockResolvedValueOnce({ node_id: "t_1", status: "sparring" });
    render(<CaptureBar />);
    const input = screen.getByPlaceholderText(/dump a thought/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "x" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(input.value).toBe(""));
  });
});
