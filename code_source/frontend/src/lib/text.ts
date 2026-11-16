/* Text helpers shared by the pages (wording, plurals, comparison keys, contact links). */
/** Lower case, without accents nor surrounding spaces: the key of every comparison. */
export function normKey(text: string | null | undefined): string {
  return (text ?? "")
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
export function plural(count: number, many = "s", one = ""): string {
  return count > 1 ? many : one;
}

/** An e-mail template's text with its {variables} replaced, as the server sends it (domain/utils.apply_template_variables):
    names are not case sensitive, unknown ones are kept. */
export function fillTemplate(text: string, values: Readonly<Record<string, string>>): string {
  return text.replace(/\{([^{}]+)\}/g, (whole, name: string) => values[name.toLowerCase()] ?? whole);
}
