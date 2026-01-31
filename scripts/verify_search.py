import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from venom_core.core.model_registry import ModelProvider, ModelRegistry
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def main():
    print("Initializing ModelRegistry...")
    registry = ModelRegistry(models_dir="./data/models_test")

    print("\n--- Testing HuggingFace Search ---")
    query_hf = "gemma"
    print(f"Searching for '{query_hf}'...")
    hf_results = await registry.search_external_models(
        ModelProvider.HUGGINGFACE, query_hf, limit=3
    )

    if hf_results.get("models"):
        print(f"✅ Found {len(hf_results['models'])} models.")
        for m in hf_results["models"]:
            print(f" - {m['model_name']} (Downloads: {m.get('downloads')})")
    else:
        print(f"❌ No models found or error: {hf_results.get('error')}")

    print("\n--- Testing Ollama Search (Scraping) ---")
    query_ollama = "llama3"
    print(f"Searching for '{query_ollama}'...")
    ollama_results = await registry.search_external_models(
        ModelProvider.OLLAMA, query_ollama, limit=3
    )

    if ollama_results.get("models"):
        print(f"✅ Found {len(ollama_results['models'])} models.")
        for m in ollama_results["models"]:
            print(
                f" - {m['model_name']}: {m['tags'][0] if m.get('tags') else 'No desc'}"
            )
    else:
        print(f"❌ No models found or error: {ollama_results.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
