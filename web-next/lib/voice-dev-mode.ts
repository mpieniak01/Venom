export function isVoiceDevModeEnabled(
  devFlag: string | string[] | undefined,
): boolean {
  return Array.isArray(devFlag) ? devFlag.includes("1") : devFlag === "1";
}
