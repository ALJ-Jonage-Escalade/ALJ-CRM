import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useToast } from "./toast";

describe("useToast", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("shows a message for 4 seconds by default, or the time asked", () => {
    const toast = useToast();
    toast.show("✅ Enregistré.");
    expect(toast.message.value).toBe("✅ Enregistré.");
    vi.advanceTimersByTime(3999);
    expect(toast.message.value).toBe("✅ Enregistré.");
    vi.advanceTimersByTime(1);
    expect(toast.message.value).toBe("");
    toast.show("⏳ Long", 10_000);
    vi.advanceTimersByTime(9999);
    expect(toast.message.value).toBe("⏳ Long");
  });

  it("replaces the message shown, with its own time", () => {
    const toast = useToast();
    toast.show("first", 1000);
    vi.advanceTimersByTime(900);
    toast.show("second", 1000);
    vi.advanceTimersByTime(900);
    expect(toast.message.value).toBe("second");
    vi.advanceTimersByTime(100);
    expect(toast.message.value).toBe("");
  });
});
