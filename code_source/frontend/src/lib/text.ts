/* Text helpers shared by the pages (wording, plurals, comparison keys, contact links). */
/** Lower case, without accents nor surrounding spaces: the key of every comparison. */
export function normKey(s: string | null | undefined): string {
  return (s ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

/** The tel: link of a formatted phone number. */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

/** French plural ending: `plural(n)` is "s" above one (0 and 1 stay singular in French), `plural(n, "ont", "a")` for other endings. */
export function plural(n: number, many = "s", one = ""): string {
  return n > 1 ? many : one;
}
