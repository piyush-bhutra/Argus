import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Register the custom @theme scales (styles.css) so e.g. `text-display` is merged as a
// font size — otherwise it's mistaken for a color and dropped next to `text-mark-out`.
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: [
        "hero",
        "stamp-xl",
        "stamp",
        "stamp-sm",
        "display",
        "brand",
        "h2",
        "lead",
        "claim",
        "body",
        "body-sm",
        "data",
        "data-sm",
      ],
      tracking: ["data", "data-wide"],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
