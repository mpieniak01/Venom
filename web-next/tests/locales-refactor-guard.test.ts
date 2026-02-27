import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { en } from "../lib/i18n/locales/en";
import { pl } from "../lib/i18n/locales/pl";
import { de } from "../lib/i18n/locales/de";
import { serviceStatusLocale as serviceStatusEn } from "../lib/i18n/locales/service-status-card/en";
import { serviceStatusLocale as serviceStatusPl } from "../lib/i18n/locales/service-status-card/pl";
import { serviceStatusLocale as serviceStatusDe } from "../lib/i18n/locales/service-status-card/de";
import { queueCardLocale as queueCardEn } from "../lib/i18n/locales/queue-card/en";
import { queueCardLocale as queueCardPl } from "../lib/i18n/locales/queue-card/pl";
import { queueCardLocale as queueCardDe } from "../lib/i18n/locales/queue-card/de";
import { statusBarLocale as statusBarEn } from "../lib/i18n/locales/status-bar/en";
import { statusBarLocale as statusBarPl } from "../lib/i18n/locales/status-bar/pl";
import { statusBarLocale as statusBarDe } from "../lib/i18n/locales/status-bar/de";
import { configLocale as configEn } from "../lib/i18n/locales/config/en";
import { configLocale as configPl } from "../lib/i18n/locales/config/pl";
import { configLocale as configDe } from "../lib/i18n/locales/config/de";
import { providersLocale as providersEn } from "../lib/i18n/locales/providers/en";
import { providersLocale as providersPl } from "../lib/i18n/locales/providers/pl";
import { providersLocale as providersDe } from "../lib/i18n/locales/providers/de";
import { adminLocale as adminEn } from "../lib/i18n/locales/admin/en";
import { adminLocale as adminPl } from "../lib/i18n/locales/admin/pl";
import { adminLocale as adminDe } from "../lib/i18n/locales/admin/de";
import { logsLocale as logsEn } from "../lib/i18n/locales/logs/en";
import { logsLocale as logsPl } from "../lib/i18n/locales/logs/pl";
import { logsLocale as logsDe } from "../lib/i18n/locales/logs/de";
import { tasksLocale as tasksEn } from "../lib/i18n/locales/tasks/en";
import { tasksLocale as tasksPl } from "../lib/i18n/locales/tasks/pl";
import { tasksLocale as tasksDe } from "../lib/i18n/locales/tasks/de";

function collectLeafKeys(value: unknown, prefix = ""): string[] {
  if (!value || typeof value !== "object") {
    return [];
  }
  const keys: string[] = [];
  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (nested && typeof nested === "object") {
      keys.push(...collectLeafKeys(nested, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

function assertParity(name: string, enLocale: unknown, plLocale: unknown, deLocale: unknown): void {
  const enKeys = collectLeafKeys(enLocale).sort();
  const plKeys = collectLeafKeys(plLocale).sort();
  const deKeys = collectLeafKeys(deLocale).sort();
  assert.deepEqual(enKeys, plKeys, `${name} key drift: en vs pl`);
  assert.deepEqual(deKeys, plKeys, `${name} key drift: de vs pl`);
}

describe("locales refactor guard", () => {
  it("keeps extracted module keys synchronized across en/pl/de", () => {
    assertParity("serviceStatus", serviceStatusEn, serviceStatusPl, serviceStatusDe);
    assertParity("queueCard", queueCardEn, queueCardPl, queueCardDe);
    assertParity("statusBar", statusBarEn, statusBarPl, statusBarDe);
    assertParity("config", configEn, configPl, configDe);
    assertParity("providers", providersEn, providersPl, providersDe);
    assertParity("admin", adminEn, adminPl, adminDe);
    assertParity("logs", logsEn, logsPl, logsDe);
    assertParity("tasks", tasksEn, tasksPl, tasksDe);
  });

  it("uses top-level logs/tasks namespaces without cockpit shadowing", () => {
    assert.equal((en as Record<string, unknown>).logs, logsEn);
    assert.equal((pl as Record<string, unknown>).logs, logsPl);
    assert.equal((de as Record<string, unknown>).logs, logsDe);

    assert.equal((en as Record<string, unknown>).tasks, tasksEn);
    assert.equal((pl as Record<string, unknown>).tasks, tasksPl);
    assert.equal((de as Record<string, unknown>).tasks, tasksDe);

    const cockpitEn = (en as Record<string, unknown>).cockpit as Record<string, unknown>;
    const cockpitPl = (pl as Record<string, unknown>).cockpit as Record<string, unknown>;
    const cockpitDe = (de as Record<string, unknown>).cockpit as Record<string, unknown>;

    assert.equal("logs" in cockpitEn, false, "cockpit.en must not shadow top-level logs");
    assert.equal("logs" in cockpitPl, false, "cockpit.pl must not shadow top-level logs");
    assert.equal("logs" in cockpitDe, false, "cockpit.de must not shadow top-level logs");
    assert.equal("tasks" in cockpitEn, false, "cockpit.en must not shadow top-level tasks");
    assert.equal("tasks" in cockpitPl, false, "cockpit.pl must not shadow top-level tasks");
    assert.equal("tasks" in cockpitDe, false, "cockpit.de must not shadow top-level tasks");
  });
});
