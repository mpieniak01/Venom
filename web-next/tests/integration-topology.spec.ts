import type { Inventory } from "../lib/integration-inventory";
import { test, expect, type Page } from "@playwright/test";

/** Block write requests during browser acceptance and collect attempted writes and page errors. */
async function readOnly(page: Page) {
  const writes: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/api/**", async (route) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
      writes.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  return { writes, errors };
}

for (const viewport of [{ width: 1600, height: 1050 }, { width: 390, height: 844 }]) {
  test(`real inventory topology is accessible and read only at ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.emulateMedia({ reducedMotion: "reduce" });
    const evidence = await readOnly(page);
    const response = page.waitForResponse((item) => item.url().includes("/system/api-map") && item.ok());
    await page.goto("/config?tab=topology&visibility=all");
    const inventory: Inventory = await (await response).json();
    await expect(page.getByTestId("integration-topology-canvas")).toBeVisible();
    await expect(page.locator('.react-flow__node[data-id="venom:root"]')).toBeVisible();
    const rider = (inventory.integrations ?? []).find((entry) => entry.kind === "module" && entry.resources?.some((resource) => resource.kind === "robot"));
    if (rider) {
      const resources = (rider.resources ?? []).toSorted((a, b) => a.id.localeCompare(b.id));
      const row = page.getByTestId(`topology-entry-${rider.id}`);
      let visibleCount = Math.min(4, resources.length);
      for (const resource of resources.slice(0, visibleCount)) {
        const id = `resource:${encodeURIComponent(rider.id)}:${encodeURIComponent(resource.id)}`;
        await expect(page.getByTestId(`rf__node-${id}`)).toBeAttached();
      }
      while (visibleCount < resources.length) {
        await row.getByRole("button", { name: /Pokaż więcej zasobów|Show more resources/ }).click();
        const nextCount = Math.min(visibleCount + 8, resources.length);
        for (const resource of resources.slice(visibleCount, nextCount)) {
          const id = `resource:${encodeURIComponent(rider.id)}:${encodeURIComponent(resource.id)}`;
          await expect(page.getByTestId(`rf__node-${id}`)).toBeAttached();
        }
        visibleCount = nextCount;
      }
      await row.getByRole("button", { name: resources[0].label }).first().click();
      await expect(page.locator("aside").last()).toContainText(resources[0].label);
      await page.reload();
      await expect(page.locator("aside").last()).toContainText(resources[0].label);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    expect(evidence.errors).toEqual([]);
    expect(evidence.writes).toEqual([]);
  });
}

/** Create a cached resource fixture with literal regex punctuation in its label. */
const resource = (id: string) => ({ id, label: `Robot [${id}] (demo)`, kind: "robot", state: "stale", configuration: "configured", selected: id === "0", source: "device_cache", reason_code: "not_observed" });
/** Create a complete large inventory fixture for resource paging and stale-data regression. */
const entry = (id: string, location = "local") => ({ id, label: "Same API", scope: "external", location, kind: "module", state: "unverified", configuration: "configured", activation: "enabled", connectivity: "unknown", source: "configuration", reason_code: "not_probed", resource_support: "supported", can_probe: false, resources_complete: true, resource_count: 64, observed_at: "2026-10-17T10:00:00Z", resources: Array.from({ length: 64 }, (_, index) => resource(String(index))) });

test("real canvas retains viewport, focus and selection on polling and failed refresh", async ({ page }) => {
  const evidence = await readOnly(page);
  let requests = 0;
  let fail = false;
  await page.route("**/api/v1/system/api-map", async (route) => {
    requests += 1;
    await route.fulfill({ status: fail ? 503 : 200, json: fail ? {} : { schema_version: 2, integrations: [entry("rider"), entry("cloud", "cloud")], internal_connections: [], external_connections: [] } });
  });
  await page.goto("/config?tab=topology&integration=rider&resource=0");
  await expect(page.locator(".react-flow__node")).toHaveCount(11);
  const riderRow = page.getByTestId("topology-entry-rider");
  for (const id of ["0", "1", "10", "11"]) {
    await riderRow.getByRole("button", { name: `Robot [${id}] (demo)` }).click();
    await expect(page.getByTestId(`rf__node-resource:rider:${id}`)).toHaveClass(/selected/);
  }
  await riderRow.getByRole("button", { name: "Robot [0] (demo)" }).click();
  await expect(page.locator("aside").last()).toContainText(/zasoby: 64|resources: 64/i);
  await page.getByRole("button", { name: /Pokaż więcej zasobów|Show more resources/ }).first().click();
  await expect(page.locator(".react-flow__node")).toHaveCount(19);
  const zoom = page.locator(".react-flow__controls-zoomin");
  await zoom.click();
  const viewport = page.locator(".react-flow__viewport");
  const transform = await viewport.getAttribute("style");
  const node = page.locator('.react-flow__node[data-id="resource:rider:0"]');
  await node.focus();
  await node.press("Enter");
  await expect(page).toHaveURL(/resource=0/);
  await expect.poll(() => requests, { timeout: 15000 }).toBeGreaterThanOrEqual(2);
  await expect(node).toBeFocused();
  expect(await viewport.getAttribute("style")).toBe(transform);
  await expect(node).toHaveClass(/selected/);
  fail = true;
  await expect(page.getByRole("alert").filter({ hasText: /Odświeżenie|refresh/i })).toBeVisible({ timeout: 15000 });
  await expect(page.locator(".react-flow__node")).toHaveCount(19);
  expect(await viewport.getAttribute("style")).toBe(transform);
  expect(requests).toBe(3);
  await expect(page.locator("aside").last()).toContainText(/zasoby: 64|resources: 64/i);
  await page.getByRole("tab", { name: /Uprawnienia|Permissions/ }).click();
  await expect(page.getByTestId("integration-topology-canvas")).toHaveCount(0);
  await page.clock.install();
  await page.clock.fastForward(30000);
  expect(requests).toBe(3);
  expect(evidence.writes).toEqual([]);
  expect(evidence.errors).toEqual([]);
});

test("orphan resource selection and empty inventory remain local states", async ({ page }) => {
  await readOnly(page);
  await page.route("**/api/v1/system/api-map", (route) => route.fulfill({ json: { schema_version: 2, integrations: [], internal_connections: [], external_connections: [] } }));
  await page.goto("/config?tab=topology&integration=removed&resource=gone");
  await expect(page.getByRole("status").filter({ hasText: /nie są już dostępne|no longer available/ })).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
  await page.getByRole("tab", { name: /Integracje i węzły|Integrations/ }).click();
  await expect(page.getByText(/Wybrana integracja nie jest już dostępna|selected integration is no longer available/)).toBeVisible();
});

test("URL reload keeps a later resource and a namespaced worker visible in both views", async ({ page }) => {
  await readOnly(page);
  const fixture = entry("rider");
  fixture.resources[62] = resource("nexus:worker/1");
  await page.route("**/api/v1/system/api-map", (route) => route.fulfill({ json: { schema_version: 2, integrations: [fixture], internal_connections: [], external_connections: [] } }));
  for (const id of ["63", "nexus:worker/1"]) {
    await page.goto(`/config?tab=topology&integration=rider&resource=${encodeURIComponent(id)}`);
    const node = page.getByTestId(`rf__node-resource:rider:${encodeURIComponent(id)}`);
    const row = page.getByTestId("topology-entry-rider");
    await expect(node).toHaveClass(/selected/);
    await expect(row.getByRole("button", { name: `Robot [${id}] (demo)` })).toBeVisible();
    await page.reload();
    await expect(node).toHaveClass(/selected/);
    await expect(row.getByRole("button", { name: `Robot [${id}] (demo)` })).toBeVisible();
    if (id === "63") {
      const count = await page.locator(".react-flow__node").count();
      await row.getByRole("button", { name: /Pokaż więcej zasobów|Show more resources/ }).click();
      await expect.poll(() => page.locator(".react-flow__node").count()).toBeGreaterThan(count);
    }
  }
});
