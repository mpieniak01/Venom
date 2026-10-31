import type { Metadata } from "next";

// Share language/theme bootstrap, local fonts, providers and styles, without
// importing the Full console layout, its routes or telemetry subscriptions.
export { default } from "@/app/layout";

export const metadata: Metadata = {
  title: "Venom Studio",
  description: "Venom Chat 2.0: text, materials and on-demand voice.",
};
