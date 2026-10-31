import { VoiceChatScreen } from "@/components/voice/voice-chat-screen";
import { isVoiceDevModeEnabled } from "@/lib/voice-dev-mode";

type VoicePageProps = Readonly<{
  searchParams?: Promise<{
    dev?: string | string[];
  }>;
}>;

export default async function VoicePage({ searchParams }: VoicePageProps) {
  const resolvedSearchParams = await searchParams;
  return <VoiceChatScreen isDevMode={isVoiceDevModeEnabled(resolvedSearchParams?.dev)} />;
}
