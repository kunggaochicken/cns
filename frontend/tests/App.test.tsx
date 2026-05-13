import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import App from "../src/App";

describe("App", () => {
  it("renders the GigaBrain shell", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/GigaBrain/i)).toBeInTheDocument();
  });
});
