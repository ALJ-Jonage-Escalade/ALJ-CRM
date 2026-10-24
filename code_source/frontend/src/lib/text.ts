/* Text helpers shared by the pages (wording, plurals). */
/** French plural ending: `plural(n)` is "s" above one (0 and 1 stay singular in French), `plural(n, "ont", "a")` for other endings. */
export function plural(n: number, many = "s", one = ""): string {
  return n > 1 ? many : one;
}
