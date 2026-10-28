import { expect, test } from "@playwright/test";

// Every browser API request is intercepted, including unknown routes.
// This scenario never provisions a host, opens SSH, or runs a real model.
test.describe("Vast Ollama selector with isolated API fixtures", () => {
  for (const available of [false, true]) {
    test(available ? "selects the remote catalog without local models" : "cannot select a host that is unavailable", async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem("venom-language", "en");
      });
      const model = (name: string, runtime: string) => ({
        id: runtime + ":" + name, name, provider: "ollama", runtime_id: runtime,
        source_type: runtime === "vast_ollama" ? "remote" : "local-runtime",
        active: false, chat_compatible: true,
      });
      const localModel = model("local-only:latest", "ollama");
      const remoteModel = model("remote-only:latest", "vast_ollama");
      const runtimes = [
        {runtime_id: "ollama", source_type: "local-runtime", configured: true, available: true, status: "running", active: true, models: [localModel]},
        {runtime_id: "vast_ollama", label: "Ollama · Vast", source_type: "remote", configured: true, available, status: available ? "running" : "offline", active: false, adapter_deploy_supported: false, models: available ? [remoteModel] : []},
      ];
      let mutationCount = 0;
      await page.route("**/api/**", async (route) => {
        const req = route.request();
        const path = new URL(req.url()).pathname;
        if (req.method() !== "GET") {
          mutationCount += 1;
          await route.fulfill({status: 409, json: {detail: "Unexpected mutation in selector fixture"}});
          return;
        }
        if (path.endsWith("/system/llm-runtime/options")) {
          await route.fulfill({json: {
            status: "success", active: {runtime_id: "ollama", active_server: "ollama", active_model: "local-only:latest"},
            runtimes, model_catalog: {all_models: [localModel, ...(available ? [remoteModel] : [])], chat_models: [localModel, ...(available ? [remoteModel] : [])]},
          }});
        } else if (path.endsWith("/system/llm-servers/active")) {
          await route.fulfill({json: {active_server: "ollama", active_model: "local-only:latest", runtime_id: "ollama@http://localhost:11434/v1"}});
        } else if (path.endsWith("/system/status")) {
          await route.fulfill({json: {boot_id: "vast-fixture"}});
        } else {
          await route.fulfill({json: path.includes("/history") || path.endsWith("/tasks") ? [] : {}});
        }
      });
      await page.route("**/v1/daemon/**", (route) => route.fulfill({status: 503, json: {detail: "fixture daemon unavailable"}}));
      await page.routeWebSocket("**/ws/**", (socket) => socket.close());
      await page.goto("/");
      const select = page.getByTestId("llm-server-select");
      await expect(select).toBeVisible();
      await select.click();
      const option = page.getByTestId("llm-server-option-vast_ollama");
      await expect(option).toHaveText("Ollama · Vast");
      if (!available) {
        await expect(option).toBeDisabled();
      } else {
        await expect(option).toBeEnabled();
        await option.click();
        await page.getByTestId("llm-model-select").click();
        await expect(page.getByTestId("llm-model-option-remote-only:latest")).toBeVisible();
        await expect(page.getByTestId("llm-model-option-local-only:latest")).toHaveCount(0);
      }
      expect(mutationCount).toBe(0);
    });
  }
});
