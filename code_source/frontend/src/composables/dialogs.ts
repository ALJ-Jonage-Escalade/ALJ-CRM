/* Confirmation and text-entry dialogs of the club theme, instead of the browser's confirm() and prompt(). One request
   at a time, shown by UiDialogHost (mounted once in App.vue) and answered through a promise: a new request cancels
   the one still open. Tests replace the answer with vi.spyOn(dialogs, "confirm"). */
import { shallowRef } from "vue";

export interface ConfirmRequest {
  title: string;
  /** Line breaks are kept (bulleted lists of changes, of competitions…) */
  message?: string;
  /** Label of the main button, « Confirmer » by default */
  confirmLabel?: string;
  /** danger: a deletion; warning: an action to think twice about */
  variant?: "primary" | "warning" | "danger";
}

export interface PromptRequest extends ConfirmRequest {
  label: string;
  value?: string;
}

export type PendingDialog =
  | { kind: "confirm"; request: ConfirmRequest; answer(ok: boolean): void }
  | { kind: "prompt"; request: PromptRequest; answer(value: string | null): void };

export const pendingDialog = shallowRef<PendingDialog | null>(null);

/** Cancels the open request, if any (its promise gets false or null). */
export function cancelDialog(): void {
  const open = pendingDialog.value;
  if (open?.kind === "confirm") {
    open.answer(false);
  } else if (open?.kind === "prompt") {
    open.answer(null);
  }
}

function settle<T>(resolve: (value: T) => void): (value: T) => void {
  return (value) => {
    pendingDialog.value = null;
    resolve(value);
  };
}

export const dialogs = {
  /** true once the main button is chosen; false on « Annuler », Escape or a click outside. */
  confirm(request: ConfirmRequest): Promise<boolean> {
    cancelDialog();
    return new Promise((resolve) => (pendingDialog.value = { kind: "confirm", request, answer: settle(resolve) }));
  },
  /** The text entered, or null when cancelled. */
  prompt(request: PromptRequest): Promise<string | null> {
    cancelDialog();
    return new Promise((resolve) => (pendingDialog.value = { kind: "prompt", request, answer: settle(resolve) }));
  },
};
