import { StudioShell } from "@/components/chat/studio-shell";

export default function StudioChatPage() {
  const autoIndexDirect = process.env.NEXT_PUBLIC_STUDIO_DIRECT_AUTO_INDEX !== "0";
  return <StudioShell showLegacyLink={false} autoIndexDirect={autoIndexDirect} />;
}
