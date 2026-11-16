import { afterEach, describe, expect, it, vi } from "vitest";
import { effectScope } from "vue";
import { useNetworkUp } from "./network";

describe("useNetworkUp", () => {
  afterEach(() => vi.restoreAllMocks());

  it("follows navigator.onLine on the online and offline events until its scope ends", () => {
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
    const scope = effectScope();
    const up = scope.run(() => useNetworkUp())!;
    expect(up.value).toBe(true);
    onLine.mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    expect(up.value).toBe(false);
    onLine.mockReturnValue(true);
    window.dispatchEvent(new Event("online"));
    expect(up.value).toBe(true);
    scope.stop();
    onLine.mockReturnValue(false);
    window.dispatchEvent(new Event("offline"));
    expect(up.value).toBe(true);
  });
});
