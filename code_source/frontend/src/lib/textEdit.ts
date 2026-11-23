/* Edits of a text field at its selection: inserting text, wrapping it in tags, links. */

/** A text field after an edit, with the selection to restore. */
export interface Edit {
  value: string;
  start: number;
  end: number;
}

/** Replaces the selection with the text; the cursor goes after it. */
export function insertText(value: string, start: number, end: number, text: string): Edit {
  const at = start + text.length;
  return { value: value.slice(0, start) + text + value.slice(end), start: at, end: at };
}

/** Puts the tags around the selection ("texte" when nothing is selected), which stays selected. */
export function wrapSelection(value: string, start: number, end: number, open: string, close: string): Edit {
  const selected = value.slice(start, end) || "texte";
  const from = start + open.length;
  return { value: value.slice(0, start) + open + selected + close + value.slice(end), start: from, end: from + selected.length };
}

/** The link's address, or null for an empty answer (the prompt starts with "https://"). */
export function linkTarget(answer: string | null): string | null {
  const url = answer?.trim() ?? "";
  return url && url !== "https://" ? url : null;
}

/** Escapes the address for the href attribute. */
export function linkTags(url: string): [string, string] {
  return [`<a href="${url.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}">`, "</a>"];
}
