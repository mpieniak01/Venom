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

fish-speech-start:
	@echo "🚀 Uruchamiam Fish Speech..."
	@bash scripts/llm/fish_speech_service.sh start

fish-speech-stop:
	@echo "⏹️  Zatrzymuję Fish Speech..."
	@bash scripts/llm/fish_speech_service.sh stop

fish-speech-restart:
	@echo "🔄 Restartuję Fish Speech..."
	@bash scripts/llm/fish_speech_service.sh restart
