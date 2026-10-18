import { expect, test, type Page } from "@playwright/test";
import baseline from "./fixtures/theme-cascade-baseline.json";

const properties = [
  "background-color", "background-image", "border-top-color", "border-top-width",
  "border-right-color", "border-right-width", "border-left-style", "border-radius",
  "backdrop-filter", "padding-top", "padding-right", "font-family", "color",
  "outline-style", "outline-width", "box-shadow",
];
const legacyOverrides = baseline.declarations
  .map(({ selector, property, value }) => `${selector} { ${property}: ${value} !important; }`)
  .join("\n");
const fixtureHtml = `
  <main class="cascade-grid">
    <section id="panel" data-cascade-fixture class="glass-panel cascade-utility">Panel</section>
    <section id="kpi" data-cascade-fixture class="glass-panel kpi-panel cascade-utility">KPI</section>
    <section id="queue" data-cascade-fixture class="glass-panel queue-panel cascade-utility">Queue</section>
    <section id="console" data-cascade-fixture class="glass-panel command-console-panel cascade-utility">Console</section>
    <aside id="sidebar" data-cascade-fixture class="sidebar glass-panel cascade-utility">Sidebar</aside>
    <aside id="aside-panel" data-cascade-fixture class="glass-panel cascade-utility">Aside panel</aside>
    <nav id="nav-panel" data-cascade-fixture class="glass-panel cascade-utility">Navigation</nav>
    <div class="cascade-fields">
      <input id="text-input" data-cascade-fixture class="cascade-utility" aria-label="Text fixture" value="Text" />
      <input id="disabled-input" data-cascade-fixture class="cascade-utility" aria-label="Disabled fixture" value="Disabled" disabled />
      <input id="readonly-input" data-cascade-fixture class="cascade-utility" aria-label="Read only fixture" value="Read only" readonly />
      <textarea id="textarea" data-cascade-fixture class="cascade-utility" aria-label="Textarea fixture">Text area</textarea>
    </div>
    <button id="reset-focus">Reset fixture focus</button>
  </main>`;
const fixtureCss = `
  .cascade-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; padding:16px; }
  .cascade-grid > section, .cascade-grid > aside, .cascade-grid > nav { min-height:80px; }
  .cascade-fields { display:grid; gap:12px; grid-column:1 / -1; }
  @layer utilities {
    .cascade-utility { background:rgb(255,0,0); border:0; border-radius:99px; padding:3px;
      backdrop-filter:none; color:rgb(0,255,0); font-family:serif; outline:5px solid red; box-shadow:none; }
    .cascade-utility:focus { border-color:blue; outline:5px solid blue; box-shadow:none; }
  }
  @media (max-width:500px) { .cascade-grid { grid-template-columns:1fr; } }
`;

async function captureStyles(page: Page) {
  await page.locator("#reset-focus").focus();
  const normal = await page.locator("[data-cascade-fixture]").evaluateAll((elements, names) =>
    Object.fromEntries(elements.map((element) => {
      const style = getComputedStyle(element);
      const after = getComputedStyle(element, "::after");
      return [element.id, { ...Object.fromEntries(names.map((name) => [name, style.getPropertyValue(name)])), afterDisplay: after.display }];
    })), properties);
  const focused: Record<string, Record<string, string>> = {};
  for (const id of ["text-input", "textarea"]) {
    await page.locator(`#${id}`).focus();
    focused[id] = await page.locator(`#${id}`).evaluate((element, names) => {
      const style = getComputedStyle(element);
      return Object.fromEntries(names.map((name) => [name, style.getPropertyValue(name)]));
    }, properties);
  }
  return { normal, focused };
}

for (const theme of ["venom-dark", "venom-light"]) {
  for (const viewport of [{ width: 1280, height: 960 }, { width: 390, height: 844 }]) {
    test(`preserves the cascade and appearance for ${theme} at ${viewport.width}px`, async ({ page }, testInfo) => {
      await page.setViewportSize(viewport);
      await page.goto("/");
      const fontClasses = await page.locator("html").getAttribute("class");
      const links = await page.locator('link[rel="stylesheet"]').evaluateAll((elements) =>
        elements.map((element) => (element as HTMLLinkElement).href));
      expect(links.length).toBeGreaterThan(0);
      const sheets = await Promise.all(links.map(async (url) => {
        const response = await page.request.get(url);
        expect(response.ok()).toBe(true);
        return response.text();
      }));
      await page.setContent(`<!doctype html><html class="${fontClasses ?? ""}" data-theme="${theme}"><head></head><body>${fixtureHtml}</body></html>`);
      await page.addStyleTag({ content: sheets.join("\n") });
      await page.addStyleTag({ content: fixtureCss });
      await page.evaluate(() => document.fonts.ready);
      const current = await captureStyles(page);
      const currentImage = await page.screenshot({ fullPage: true, animations: "disabled", caret: "hide" });
      await page.addStyleTag({ content: legacyOverrides });
      const legacy = await captureStyles(page);
      const legacyImage = await page.screenshot({ fullPage: true, animations: "disabled", caret: "hide" });
      await testInfo.attach("current.png", { body: currentImage, contentType: "image/png" });
      await testInfo.attach("legacy-baseline.png", { body: legacyImage, contentType: "image/png" });
      await testInfo.attach("computed-styles.json", { body: Buffer.from(JSON.stringify({ current, legacy }, null, 2)), contentType: "application/json" });
      expect(current).toEqual(legacy);
      expect(currentImage.equals(legacyImage), "removing important must preserve fixture pixels").toBe(true);
    });
  }
}
