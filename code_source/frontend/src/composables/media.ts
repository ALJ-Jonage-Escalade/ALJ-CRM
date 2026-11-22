/* Whether a CSS media query matches, kept up to date. For layouts that differ in their markup, not only their style
   (a table on wide screens, cards elsewhere): only one is rendered, so a test id is never found twice. False without
   matchMedia (unit tests). */
import { onScopeDispose, ref, type Ref } from "vue";

/** Tailwind's `md` as redefined in styles.css: 48rem wide, except a phone held sideways (touch screen under 500px
    tall), which keeps the phone layout. Keep both in step. */
export const WIDE_LAYOUT_QUERY = "(min-width: 48rem) and (not ((pointer: coarse) and (max-height: 500px)))";

export function useMediaQuery(query: string): Readonly<Ref<boolean>> {
  const list = typeof window.matchMedia === "function" ? window.matchMedia(query) : null;
  const matches = ref(list?.matches ?? false);
  if (list) {
    const onChange = (e: MediaQueryListEvent) => (matches.value = e.matches);
    list.addEventListener("change", onChange);
    onScopeDispose(() => list.removeEventListener("change", onChange));
  }
  return matches;
}
