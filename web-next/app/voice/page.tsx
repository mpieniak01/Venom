import { VoiceChatScreen } from "@/components/voice/voice-chat-screen";

type VoicePageProps = Readonly<{
  searchParams?: Promise<{
    dev?: string | string[];
  }> | {
    dev?: string | string[];
  };
}>;

export default async function VoicePage({ searchParams }: VoicePageProps) {
  const resolvedSearchParams = await searchParams;
  const devFlag = resolvedSearchParams?.dev;
  const isDevMode = Array.isArray(devFlag) ? devFlag.includes("1") : devFlag === "1";
  return <VoiceChatScreen isDevMode={isDevMode} />;
}
