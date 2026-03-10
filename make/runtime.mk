# =============================================================================
# Kontrola LLM Runtime (vLLM, Ollama)
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
