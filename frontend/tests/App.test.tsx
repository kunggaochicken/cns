import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App";

class MockEventSource {
  static instance: MockEventSource | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    MockEventSource.instance = this;
  }
}

vi.mock("react-force-graph-2d", () => ({
  __esModule: true,
  default: () => <div data-testid="force-graph" />,
}));

beforeEach(() => {
  // @ts-expect-error mock
  globalThis.EventSource = MockEventSource;
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ nodes: [], edges: [] }),
  });
});
afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("renders TopBar with GigaBrain label", async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/GigaBrain/)).toBeInTheDocument());
  });

  it("renders the desktop graph + capture bar by default", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByTestId("force-graph")).toBeInTheDocument());
    expect(screen.getByPlaceholderText(/capture a thought/i)).toBeInTheDocument();
  });

  it("renders the mobile inbox at /inbox", async () => {
    render(
      <MemoryRouter initialEntries={["/inbox"]}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /gate/i })).toBeInTheDocument(),
    );
  });
});
