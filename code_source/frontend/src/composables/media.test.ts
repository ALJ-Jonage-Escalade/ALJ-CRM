import { afterEach, describe, expect, it, vi } from "vitest";
import { effectScope } from "vue";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { useMediaQuery, WIDE_LAYOUT_QUERY } from "./media";

/** A MediaQueryList whose matching the test changes. */
function fakeMediaList(initial: boolean) {
  let listener: ((event: MediaQueryListEvent) => void) | null = null;
  const list = {
    matches: initial,
    addEventListener: vi.fn((_: string, callback: (event: MediaQueryListEvent) => void) => (listener = callback)),
    removeEventListener: vi.fn(() => (listener = null)),
  };
  return { list, change: (matches: boolean) => listener?.({ matches } as MediaQueryListEvent) };
}

describe("useMediaQuery", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is false without matchMedia", () => {
    vi.stubGlobal("matchMedia", undefined);
    const scope = effectScope();
    expect(scope.run(() => useMediaQuery("(min-width: 768px)"))!.value).toBe(false);
    scope.stop();
  });

  it("follows the query until its scope ends", () => {
    const media = fakeMediaList(true);
    const matchMedia = vi.fn(() => media.list);
    vi.stubGlobal("matchMedia", matchMedia);
    const scope = effectScope();
    const wide = scope.run(() => useMediaQuery("(min-width: 768px)"))!;
    expect(matchMedia).toHaveBeenCalledWith("(min-width: 768px)");
    expect(wide.value).toBe(true);
    media.change(false);
    expect(wide.value).toBe(false);
    scope.stop();
    expect(media.list.removeEventListener).toHaveBeenCalledOnce();
    media.change(true);
    expect(wide.value).toBe(false);
  });
});

it("uses the same phone/computer breakpoint as Tailwind's md in styles.css", () => {
  // Read from the disk: the tests do not load CSS (an import gives an empty text)
  const stylesCss = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../styles.css"), "utf8");
  expect(stylesCss).toContain(`@custom-variant md (@media ${WIDE_LAYOUT_QUERY});`);
});
