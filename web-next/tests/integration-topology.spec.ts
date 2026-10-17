import { test, expect, type Page } from "@playwright/test";

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
    const inventory = await (await response).json();
    await expect(page.getByTestId("integration-topology-canvas")).toBeVisible();
    await expect(page.locator('.react-flow__node[data-id="venom:root"]')).toBeVisible();
    const rider = inventory.integrations.find((entry: { kind: string; resources?: { kind: string }[] }) => entry.kind === "module" && entry.resources?.some((resource) => resource.kind === "robot"));
    if (rider) {
      for (const resource of rider.resources) {
        const id = `resource:${encodeURIComponent(rider.id)}:${encodeURIComponent(resource.id)}`;
        await expect(page.locator(`.react-flow__node[data-id="${id}"]`)).toBeAttached();
      }
      await page.locator("details").getByRole("button", { name: new RegExp(rider.resources[0].label) }).first().click();
      await expect(page.locator("aside").last()).toContainText(rider.resources[0].label);
      await page.reload();
      await expect(page.locator("aside").last()).toContainText(rider.resources[0].label);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    expect(evidence.errors).toEqual([]);
    expect(evidence.writes).toEqual([]);
  });
}

const resource = (id: string) => ({ id, label: "Same device", kind: "robot", state: "stale", configuration: "configured", selected: id === "0", source: "device_cache", reason_code: "not_observed" });
const entry = (id: string, location = "local") => ({ id, label: "Same API", scope: "external", location, kind: "module", state: "unverified", configuration: "configured", activation: "enabled", connectivity: "unknown", source: "configuration", reason_code: "not_probed", resource_support: "supported", can_probe: false, resources_complete: false, resources: Array.from({ length: 64 }, (_, index) => resource(String(index))) });

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
