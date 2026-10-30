import assert from "node:assert/strict";
import { it } from "node:test";
import { ApiError } from "../lib/api-client";
import { runtimeControlErrorHint } from "../lib/runtime-control-error";
import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";

for (const locale of [pl, en, de]) {
  const t = (key: string) => key.split(".").reduce<unknown>((value, part) => (value as Record<string, unknown>)[part], locale) as string;
  it("explains quarantine recovery separately from live busy and provider disablement", () => {
    const recovery = runtimeControlErrorHint(new ApiError("Request failed: 409", 409, { detail: { code: "runtime_recovery_required" } }), t);
    assert.equal(recovery, locale.cockpit.modelActivation.recoveryRequired);
    assert.equal(runtimeControlErrorHint(new ApiError("409", 409, { detail: { code: "runtime_busy" } }), t), locale.cockpit.modelActivation.runtimeBusy);
    assert.equal(runtimeControlErrorHint(new ApiError("503", 503, { detail: { code: "remote_provider_disabled" } }), t), locale.cockpit.modelActivation.providerDisabled);
    assert.equal(runtimeControlErrorHint(new Error("other"), t), null);
  });
}
