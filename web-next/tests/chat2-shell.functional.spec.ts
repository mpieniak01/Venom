import { expect, test } from "@playwright/test";
import runChat2Acceptance from "./chat2-acceptance.mjs";

test.describe("Chat 2.0 Studio — fake API and audio acceptance", () => {
  test.skip(process.env.E2E_CHAT2 !== "1", "Opt in with E2E_CHAT2=1 and NEXT_PUBLIC_FEATURE_CHAT2=true on the tested UI.");

  test("isolated shell retains history, materials, Stop and shared voice context", async ({ page, baseURL }) => {
    test.setTimeout(180_000);
    const result = await runChat2Acceptance(page, baseURL || "http://127.0.0.1:3300");
    expect(result.fakeAPI).toBe(true);
    expect(result.realProviderCalls).toBe(0);
    expect(result.realMicrophoneCalls).toBe(0);
    expect(result.assertions.length).toBeGreaterThanOrEqual(30);
    expect(result.counters.externalAttempts).toBe(0);
    expect(result.counters.unexpectedWrites).toBe(0);
    expect(result.counters.tracksStopped).toBe(result.counters.tracksCreated);
    expect(result.counters.playbackActive).toBe(0);
    expect(result.counters.hydrationErrors).toBe(0);
  });
});
