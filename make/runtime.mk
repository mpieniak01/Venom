# =============================================================================
# Kontrola LLM Runtime (vLLM, Ollama, Multi-Runtime)
# =============================================================================

vllm-start:
	@echo "🚀 Uruchamiam vLLM..."
	@bash scripts/llm/vllm_service.sh start

vllm-stop:
	@echo "⏹️  Zatrzymuję vLLM..."
	@bash scripts/llm/vllm_service.sh stop

vllm-restart:
	@echo "🔄 Restartuję vLLM..."
	@bash scripts/llm/vllm_service.sh restart

ollama-start:
	@echo "🚀 Uruchamiam Ollama..."
	@bash scripts/llm/ollama_service.sh start

ollama-stop:
	@echo "⏹️  Zatrzymuję Ollama..."
	@bash scripts/llm/ollama_service.sh stop

ollama-restart:
	@echo "🔄 Restartuję Ollama..."
	@bash scripts/llm/ollama_service.sh restart

multi-runtime-start:
	@echo "🚀 Uruchamiam Multi-Runtime..."
	@bash scripts/llm/multi_runtime_service.sh start

multi-runtime-stop:
	@echo "⏹️  Zatrzymuję Multi-Runtime..."
	@bash scripts/llm/multi_runtime_service.sh stop

multi-runtime-restart:
	@echo "🔄 Restartuję Multi-Runtime..."
	@bash scripts/llm/multi_runtime_service.sh restart

multi-runtime-hygiene:
	@echo "🧹 Higiena Multi-Runtime (stop + cleanup daemon state)..."
	@bash scripts/llm/multi_runtime_service.sh stop
