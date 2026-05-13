# =============================================================================
# Kontrola LLM Runtime (vLLM, Ollama, Gemma4 Audio)
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

gemma4-audio-start:
	@echo "🚀 Uruchamiam Gemma4 Audio..."
	@bash scripts/llm/gemma4_audio_service.sh start

gemma4-audio-stop:
	@echo "⏹️  Zatrzymuję Gemma4 Audio..."
	@bash scripts/llm/gemma4_audio_service.sh stop

gemma4-audio-restart:
	@echo "🔄 Restartuję Gemma4 Audio..."
	@bash scripts/llm/gemma4_audio_service.sh restart

gemma4-audio-hygiene:
	@echo "🧹 Higiena Gemma4 Audio (stop + cleanup daemon state)..."
	@bash scripts/llm/gemma4_audio_service.sh stop
