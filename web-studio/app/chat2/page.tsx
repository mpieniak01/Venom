import { StudioShell } from "@/components/chat/studio-shell";

export default function StudioChatPage() {
  const lightNormal = process.env.NEXT_PUBLIC_STUDIO_LIGHT_NORMAL !== "0";
  return <StudioShell showLegacyLink={false} lightNormal={lightNormal} />;
}
