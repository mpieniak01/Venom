# HTTP Scheme Inventory Report (Task 116)

Generated from scoped scan (`venom_core`, `tests`, `examples`, `web-next`, `scripts`, `compose`).

Summary:
- Total occurrences: `125`
- Category A: `89`
- Category B: `12`
- Category C: `17`
- Category D: `4`
- Category E: `3`
- Notes: category `D` currently contains only compose healthcheck probes on `localhost` (explicit technical exceptions).

| File | Line | Category | Decision | Occurrence |
|---|---:|:---:|---|---|
| `compose/compose.minimal.yml` | 50 | D | Runtime/prod path; migrate to central URL policy helper (required). | `      test: ["CMD", "curl", "-fsS", "http://localhost:8000/healthz"]` |
| `compose/compose.minimal.yml` | 74 | D | Runtime/prod path; migrate to central URL policy helper (required). | `      test: ["CMD", "node", "-e", "fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]` |
| `compose/compose.release.yml` | 45 | D | Runtime/prod path; migrate to central URL policy helper (required). | `      test: ["CMD", "curl", "-fsS", "http://localhost:8000/healthz"]` |
| `compose/compose.release.yml` | 67 | D | Runtime/prod path; migrate to central URL policy helper (required). | `      test: ["CMD", "node", "-e", "fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]` |
| `scripts/run-locust.sh` | 19 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `echo "🚀 Panel Locusta: http://${HOST}:${PORT}"` |
| `scripts/docker/install.sh` | 208 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `if ! wait_http "http://127.0.0.1:11434/api/tags" 180; then` |
| `scripts/docker/install.sh` | 213 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `wait_http "http://127.0.0.1:8000/healthz" 240` |
| `scripts/docker/install.sh` | 214 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `wait_http "http://127.0.0.1:3000" 240` |
| `scripts/docker/install.sh` | 223 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `echo "[INFO] UI:      http://127.0.0.1:3000"` |
| `scripts/docker/install.sh` | 224 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `echo "[INFO] Backend: http://127.0.0.1:8000"` |
| `web-next/playwright.perf.config.ts` | 3 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `const nextBase = process.env.PERF_NEXT_BASE_URL ?? "http://localhost:3000";` |
| `web-next/playwright.perf.config.ts` | 4 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `const legacyBase = process.env.PERF_LEGACY_BASE_URL ?? "http://localhost:8000";` |
| `scripts/llm/ollama_service.sh` | 66 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `  if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then` |
| `scripts/llm/ollama_service.sh` | 74 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `      loaded_models=$(curl -s http://localhost:11434/api/ps \| grep -oP '"name":"\K[^"]+' \|\| true)` |
| `scripts/llm/ollama_service.sh` | 77 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `          curl -s -X POST http://localhost:11434/api/generate -d "{\"model\":\"$m\",\"keep_alive\":0}" >/dev/null 2>&1 \|\| true` |
| `web-next/playwright.config.ts` | 7 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `const baseURL = process.env.BASE_URL \|\| `http://${devHost}:${devPort}`;` |
| `web-next/README.md` | 7 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `- Działający backend FastAPI Venoma (domyślnie `http://localhost:8000`)` |
| `web-next/README.md` | 19 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `NEXT_PUBLIC_API_BASE=http://localhost:8000` |
| `web-next/README.md` | 27 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `npm run dev    # http://localhost:3000` |
| `web-next/README.md` | 93 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `   (opcjonalnie `BASE_URL=http://127.0.0.1:3001` gdy chcesz wymusić inny adres).` |
| `web-next/tests/smoke.spec.ts` | 292 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `          { name: "vllm", status: "online", base_url: "http://localhost:8000" }` |
| `web-next/tests/perf/chat-latency.spec.ts` | 19 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `  return `http://${host}:${port}`;` |
| `web-next/tests/perf/chat-latency.spec.ts` | 37 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `  "http://127.0.0.1:8000";` |
| `venom_core/main.py` | 786 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `        "http://localhost:3000",` |
| `venom_core/main.py` | 787 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `        "http://127.0.0.1:3000",` |
| `venom_core/main.py` | 788 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `        "http://localhost:3100",` |
| `venom_core/main.py` | 789 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `        "http://127.0.0.1:3100",` |
| `venom_core/agents/tester.py` | 52 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `1. visit_page("http://localhost:3000/login")` |
| `venom_core/core/intent_manager.py` | 187 | E | External/probe/configurable host; avoid hardcoded scheme in business logic. | `        if "http://" in phrase or "https://" in phrase or "www." in phrase:` |
| `web-next/app/inspector/page.tsx` | 63 | E | External/probe/configurable host; avoid hardcoded scheme in business logic. | `      "http://www.w3.org/2000/svg",` |
| `web-next/dev-3000.log` | 11 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `   - Local:        http://localhost:3000` |
| `web-next/dev-3000.log` | 12 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `   - Network:      http://0.0.0.0:3000` |
| `web-next/scripts/check-e2e-env.mjs` | 10 | C | Dev localhost runtime; keep via policy-controlled local HTTP allowance. | `const defaultNextUrl = process.env.PERF_NEXT_BASE_URL ?? `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;` |
| `venom_core/simulation/README.md` | 101 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `    target_url="http://localhost:3000",` |
| `venom_core/simulation/README.md` | 270 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `    target_url="http://localhost:8080",` |
| `venom_core/simulation/README.md` | 285 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `    target_url="http://localhost:8080",` |
| `venom_core/simulation/README.md` | 310 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `    target_url="http://localhost:3000",` |
| `venom_core/simulation/README.md` | 360 | B | Demo/example only; keep non-prod or migrate gradually to helper usage. | `    target_url="http://localhost:3000",` |
| `tests/test_cloud_provisioner.py` | 266 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert url == "http://venom.local:8000"` |
| `tests/test_cloud_provisioner.py` | 270 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert url == "http://test-agent.local:8000"` |
| `tests/test_cloud_provisioner.py` | 274 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert url == "http://agent.local:8000"` |
| `tests/test_cloud_provisioner.py` | 281 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert url == "http://custom.local:9000"` |
| `tests/test_llm_simple_stream.py` | 19 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        self.endpoint = "http://localhost:11434/v1"` |
| `tests/test_llm_simple_stream.py` | 72 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        lambda runtime: "http://localhost:11434/v1/chat/completions",` |
| `venom_core/execution/skills/browser_skill.py` | 216 | E | External/probe/configurable host; avoid hardcoded scheme in business logic. | `        url: Annotated[str, "URL strony do odwiedzenia (np. 'http://localhost:3000')"],` |
| `tests/test_config_sync.py` | 24 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            "LLM_LOCAL_ENDPOINT": "http://localhost:8001/v1",` |
| `tests/test_config_sync.py` | 25 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            "VLLM_ENDPOINT": "http://localhost:8001/v1",` |
| `tests/test_config_sync.py` | 44 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert env_values["LLM_LOCAL_ENDPOINT"] == "http://localhost:11434/v1"` |
| `tests/test_config_sync.py` | 57 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert env_values["LLM_LOCAL_ENDPOINT"] == "http://localhost:8001/v1"` |
| `tests/test_config_sync.py` | 67 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            "LLM_LOCAL_ENDPOINT": "http://custom-server:1234/v1",` |
| `tests/test_config_sync.py` | 75 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert env_values["LLM_LOCAL_ENDPOINT"] == "http://custom-server:1234/v1"` |
| `tests/test_llm_server_controller.py` | 12 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        "LLM_LOCAL_ENDPOINT": "http://localhost:8001/v1",` |
| `tests/test_llm_server_controller.py` | 14 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        "VLLM_ENDPOINT": "http://localhost:8001/v1",` |
| `tests/test_motor_cortex_integration.py` | 24 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_motor_cortex_integration.py` | 28 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/test_translation_service.py` | 31 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        "http://localhost:8000/v1",` |
| `tests/test_service_monitor_streaming.py` | 22 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://fake.api/health",` |
| `tests/test_llm_server_selection.py` | 82 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    SETTINGS.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_llm_server_selection.py` | 121 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    SETTINGS.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_llm_server_selection.py` | 159 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    SETTINGS.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_state_and_orchestrator.py` | 30 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_state_and_orchestrator.py` | 34 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/test_file_operations_integration.py` | 22 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_file_operations_integration.py` | 26 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/test_file_operations_integration.py` | 104 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_url_policy.py` | 22 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        "http://api.example.com/v1/models", env="production", policy="force_https"` |
| `tests/test_ingestion_engine_roi.py` | 37 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        await engine.ingest_url("http://localhost:8000/health")` |
| `tests/test_llm_runtime_activation_api.py` | 37 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_orchestrator_decision_gates.py` | 19 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_orchestrator_decision_gates.py` | 23 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/test_council.py` | 53 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        base_url="http://localhost:11434/v1",` |
| `tests/test_history_api.py` | 25 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        llm_endpoint="http://localhost:11434",` |
| `tests/test_history_api.py` | 124 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        llm_endpoint="http://localhost:11434",` |
| `tests/test_orchestrator_intent.py` | 23 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_orchestrator_intent.py` | 27 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/test_ota_manager.py` | 200 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            package_url="http://example.com/package.zip",` |
| `tests/test_benchmark_service.py` | 187 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            endpoint="http://localhost:8000", timeout=5` |
| `tests/test_benchmark_service.py` | 204 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `                endpoint="http://localhost:8000", timeout=1` |
| `tests/test_benchmark_service.py` | 241 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `                question, model_name="model1", endpoint="http://localhost:8000"` |
| `tests/test_eyes.py` | 40 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_eyes.py` | 57 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_eyes.py` | 73 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_eyes.py` | 91 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_eyes.py` | 113 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_eyes.py` | 137 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_eyes.py` | 153 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        mock_settings.LLM_LOCAL_ENDPOINT = "http://localhost:11434/v1"` |
| `tests/test_kernel_builder.py` | 13 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"` |
| `tests/test_kernel_builder.py` | 36 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        LLM_LOCAL_ENDPOINT="http://localhost:11434/v1",` |
| `tests/test_kernel_builder.py` | 122 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        LLM_LOCAL_ENDPOINT="http://localhost:11434/v1",` |
| `tests/test_service_monitor.py` | 40 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://test.example.com",` |
| `tests/test_service_monitor.py` | 56 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://test.example.com",` |
| `tests/test_service_monitor.py` | 107 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://test.example.com",` |
| `tests/test_service_monitor.py` | 137 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://test.example.com",` |
| `tests/test_service_monitor.py` | 185 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://test.example.com",` |
| `tests/test_council_basic.py` | 22 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        base_url="http://localhost:8080/v1",` |
| `tests/test_council_basic.py` | 28 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert config["config_list"][0]["base_url"] == "http://localhost:8080/v1"` |
| `tests/test_benchmark_service_runtime_selection.py` | 25 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    monkeypatch.setattr(SETTINGS, "VLLM_ENDPOINT", "http://vllm.local/v1")` |
| `tests/test_benchmark_service_runtime_selection.py` | 26 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    monkeypatch.setattr(SETTINGS, "LLM_LOCAL_ENDPOINT", "http://ollama.local/v1")` |
| `tests/test_benchmark_service_runtime_selection.py` | 61 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert called["health"] == "http://vllm.local/v1"` |
| `tests/test_benchmark_service_runtime_selection.py` | 62 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert called["query"] == ("gemma-3-4b-it", "http://vllm.local/v1")` |
| `tests/test_benchmark_service_runtime_selection.py` | 68 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    monkeypatch.setattr(SETTINGS, "VLLM_ENDPOINT", "http://vllm.local/v1")` |
| `tests/test_benchmark_service_runtime_selection.py` | 69 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    monkeypatch.setattr(SETTINGS, "LLM_LOCAL_ENDPOINT", "http://ollama.local/v1")` |
| `tests/test_benchmark_service_runtime_selection.py` | 105 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert called["health"] == "http://ollama.local/v1"` |
| `tests/test_benchmark_service_runtime_selection.py` | 106 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert called["query"] == ("gemma3:4b", "http://ollama.local/v1")` |
| `tests/perf/test_llm_runtime_direct.py` | 16 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `OLLAMA_ENDPOINT = os.getenv("VENOM_OLLAMA_ENDPOINT", "http://localhost:11434")` |
| `tests/perf/chat_pipeline.py` | 24 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    return f"http://localhost:{api_port}"` |
| `tests/test_mcp_manager.py` | 36 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        repo_url="http://git.fake/repo",` |
| `tests/test_orchestrator_core_scenarios.py` | 21 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_orchestrator_core_scenarios.py` | 25 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/perf/locustfile.py` | 22 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    host = os.getenv("LOCUST_TARGET", "http://localhost:8000")` |
| `tests/test_core_nervous_system.py` | 21 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_core_nervous_system.py` | 25 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
| `tests/test_llm_runtime_utils.py` | 12 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://localhost:8000",` |
| `tests/test_llm_runtime_utils.py` | 24 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert llm_runtime.infer_local_provider("http://localhost:11434") == "ollama"` |
| `tests/test_llm_runtime_utils.py` | 25 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert llm_runtime.infer_local_provider("http://vllm.local") == "vllm"` |
| `tests/test_llm_runtime_utils.py` | 26 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert llm_runtime.infer_local_provider("http://lmstudio.local") == "lmstudio"` |
| `tests/test_llm_runtime_utils.py` | 27 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    assert llm_runtime.infer_local_provider("http://localhost:8001") == "vllm"` |
| `tests/test_llm_runtime_utils.py` | 51 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        DummySettings(service_type="local", endpoint="http://localhost:11434")` |
| `tests/test_llm_runtime_utils.py` | 60 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://localhost:8001/v1",` |
| `tests/test_llm_runtime_utils.py` | 73 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `            endpoint="http://localhost:11434",` |
| `tests/test_llm_runtime_utils.py` | 101 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://localhost:8001",` |
| `tests/test_llm_runtime_utils.py` | 130 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://localhost:8001",` |
| `tests/test_professor.py` | 14 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `    LLM_LOCAL_ENDPOINT: str = "http://localhost:11434/v1"` |
| `tests/test_coder_critic_loop.py` | 20 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        endpoint="http://mock",` |
| `tests/test_coder_critic_loop.py` | 24 | A | Test-only; keep as accepted exception (Sonar Safe/Accepted). | `        runtime_id="local@http://mock",` |
