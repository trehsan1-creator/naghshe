import "@testing-library/jest-dom/vitest";

// jsdom has no ResizeObserver; deck.gl/maplibre style components rely on it.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!("ResizeObserver" in globalThis)) {
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver = ResizeObserverStub;
}

if (typeof window !== "undefined" && !window.URL.createObjectURL) {
  Object.defineProperty(window.URL, "createObjectURL", { value: () => "blob:mock" });
}
