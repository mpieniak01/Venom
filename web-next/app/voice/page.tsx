import { VoiceChatScreen } from "@/components/voice/voice-chat-screen";

type VoicePageProps = Readonly<{
  searchParams?: Promise<{
    dev?: string | string[];
  }> | {
    dev?: string | string[];
  };
}>;

export function isVoiceDevModeEnabled(devFlag: string | string[] | undefined): boolean {
  return Array.isArray(devFlag) ? devFlag.includes("1") : devFlag === "1";
}

export default async function VoicePage({ searchParams }: VoicePageProps) {
  const resolvedSearchParams = await searchParams;
  return <VoiceChatScreen isDevMode={isVoiceDevModeEnabled(resolvedSearchParams?.dev)} />;
}
