/** @param {Record<string, string | undefined>} [env] */
export function configuredLanOrigins(env = process.env) {
  const origins = (env.VENOM_LAN_ORIGINS || "").split(",").map((value) => value.trim()).filter(Boolean);
  for (const origin of origins) {
    const url = new URL(origin);
    if (!["http:", "https:"].includes(url.protocol) || url.origin !== origin ||
        url.username || url.password || url.hostname.includes("*")) {
      throw new Error("VENOM_LAN_ORIGINS requires exact HTTP(S) origins");
    }
  }
  return origins;
}

/** Next's development origin allowlist accepts hostnames, without scheme/port.
 * @param {Record<string, string | undefined>} [env]
 */
export function trustedLanDevOrigins(env = process.env) {
  if (env.VENOM_OPERATOR_ACCESS !== "trusted_lan") return [];
  return [...new Set(configuredLanOrigins(env).map((origin) => new URL(origin).hostname))];
}
