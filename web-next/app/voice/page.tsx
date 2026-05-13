import { VoiceChatScreen } from "@/components/voice/voice-chat-screen";

type VoicePageProps = Readonly<{
  searchParams?: {
    dev?: string | string[];
  };
}>;

export default function VoicePage({ searchParams }: VoicePageProps) {
  const devFlag = searchParams?.dev;
  const isDevMode = Array.isArray(devFlag) ? devFlag.includes("1") : devFlag === "1";
  return <VoiceChatScreen isDevMode={isDevMode} />;
}
