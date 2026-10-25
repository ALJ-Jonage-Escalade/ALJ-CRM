/* Short message at the bottom of the screen (same as the former #toast of web/shared/alj.css). */
import { readonly, ref, type Ref } from "vue";

export interface Toast {
  message: Readonly<Ref<string>>;
  show(message: string, ms?: number): void;
}

export function useToast(): Toast {
  const message = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined;
  return {
    message: readonly(message),
    show(text, ms = 4000) {
      message.value = text;
      clearTimeout(timer);
      timer = setTimeout(() => (message.value = ""), ms);
    },
  };
}
