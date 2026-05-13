import "@testing-library/jest-dom/vitest";

class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver ??= MockResizeObserver;
