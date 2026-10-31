import { notFound } from "next/navigation";
import { StudioShell } from "@/components/chat/studio-shell";
export const metadata = { title: "Venom Chat 2.0" };
export default function Chat2Page() {
  if (process.env.NEXT_PUBLIC_FEATURE_CHAT2 !== "true") notFound();
  return <StudioShell />;
}
