import { afterEach, describe, expect, it, vi } from "vitest";
import { localStorageOrNone } from "./localStorage";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("localStorageOrNone", () => {
  it("gives the browser's storage", () => {
    expect(localStorageOrNone()).toBe(globalThis.localStorage);
  });

  it("gives nothing when the storage is blocked", () => {
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    expect(localStorageOrNone()).toBeUndefined();
  });
});
