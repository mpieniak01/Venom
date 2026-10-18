"""Moduł: huggingface_skill - Skill do wyszukiwania modeli i datasets na Hugging Face."""

from pathlib import Path
from typing import Annotated, Optional

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import RepositoryNotFoundError

from venom_core.execution.agent_contracts import tool_function as kernel_function
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

# Limity dla bezpieczeństwa i wydajności
MAX_MODELS_RESULTS = 5
MAX_DATASETS_RESULTS = 5
MAX_MODEL_CARD_LENGTH = 8000
# Mnożnik dla filtrowania modeli ONNX/GGUF
# Pobieramy więcej wyników niż potrzeba, aby móc wyfiltrować i preferować ONNX/GGUF
FILTER_MULTIPLIER = 3


class HuggingFaceSkill:
    """
    Skill do wyszukiwania modeli AI i zbiorów danych na Hugging Face.
    Pozwala agentom znajdować odpowiednie modele, sprawdzać ich parametry i wymagania.
    """

    def __init__(self, hf_token: Optional[str] = None):
        """
        Inicjalizacja HuggingFaceSkill.

        Args:
            hf_token: Token Hugging Face API (opcjonalny, dla prywatnych modeli).
        """
        self.api = HfApi(token=hf_token)
        logger.info("HuggingFaceSkill zainicjalizowany")

    @kernel_function(
        name="search_models",
        description="Wyszukuje modele AI na Hugging Face według zadania i zapytania. Preferuje modele ONNX i GGUF (kompatybilne lokalnie). Użyj gdy użytkownik szuka modelu do konkretnego zadania NLP/Vision.",
    )
    def search_models(
        self,
        task: Annotated[
            str,
            "Typ zadania (np. 'text-classification', 'question-answering', 'image-classification', 'text-generation')",
        ] = "",
        query: Annotated[str, "Zapytanie tekstowe (np. 'sentiment', 'polish')"] = "",
        sort: Annotated[
            str, "Sortowanie: 'downloads', 'likes', 'trending'"
        ] = "downloads",
    ) -> str:
        """
        Wyszukuje modele na Hugging Face.

        Args:
            task: Typ zadania ML
            query: Zapytanie tekstowe
            sort: Kryterium sortowania

        Returns:
            Sformatowana lista TOP 5 modeli
        """
        logger.info(
            f"HuggingFaceSkill: search_models (task={task}, query={query}, sort={sort})"
        )

        try:
            search_params = self._build_model_search_params(
                task=task, query=query, sort=sort
            )
            models = list(self.api.list_models(**search_params))

            if not models:
                return f"Nie znaleziono modeli dla: task={task}, query={query}"

            prioritized_models = self._prioritize_models(models)
            results = self._to_model_results(prioritized_models)

            if not results:
                return f"Nie znaleziono modeli dla: task={task}, query={query}"

            output = self._format_model_search_output(results, task=task, query=query)

            logger.info(f"HuggingFaceSkill: znaleziono {len(results)} modeli")
            return output.strip()

        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania modeli: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    @staticmethod
    def _build_model_search_params(
        task: str, query: str, sort: str
    ) -> dict[str, object]:
        params: dict[str, object] = {
            "limit": MAX_MODELS_RESULTS * FILTER_MULTIPLIER,
            "sort": sort,
        }
        if task:
            params["filter"] = task
        if query:
            params["search"] = query
        return params

    @staticmethod
    def _classify_model_compatibility(model) -> str:
        tags_lower = [tag.lower() for tag in (model.tags or [])]
        model_id_lower = model.id.lower()
        if "onnx" in tags_lower or "onnx" in model_id_lower:
            return "onnx"
        if "gguf" in tags_lower or "gguf" in model_id_lower:
            return "gguf"
        return "other"

    def _prioritize_models(self, models: list) -> list:
        onnx_models = []
        gguf_models = []
        other_models = []
        for model in models:
            bucket = self._classify_model_compatibility(model)
            if bucket == "onnx":
                model._venom_compat = "✅ ONNX (lokalne uruchamianie)"
                onnx_models.append(model)
            elif bucket == "gguf":
                model._venom_compat = "✅ GGUF (lokalne uruchamianie)"
                gguf_models.append(model)
            else:
                model._venom_compat = "⚠️ Standard (wymaga GPU/transformers)"
                other_models.append(model)

        prioritized = (
            onnx_models[:MAX_MODELS_RESULTS]
            + gguf_models[: MAX_MODELS_RESULTS - len(onnx_models)]
            + other_models[: MAX_MODELS_RESULTS - len(onnx_models) - len(gguf_models)]
        )
        return prioritized[:MAX_MODELS_RESULTS]

    @staticmethod
    def _to_model_results(prioritized_models: list) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for rank, model in enumerate(prioritized_models, 1):
            results.append(
                {
                    "rank": rank,
                    "id": model.id,
                    "task": getattr(model, "pipeline_tag", "Nieznane"),
                    "downloads": getattr(model, "downloads", 0),
                    "likes": getattr(model, "likes", 0),
                    "url": f"https://huggingface.co/{model.id}",
                    "tags": ", ".join(model.tags[:5]) if model.tags else "Brak tagów",
                    "compatibility": model._venom_compat,
                }
            )
        return results

    @staticmethod
    def _format_model_search_output(
        results: list[dict[str, object]], *, task: str, query: str
    ) -> str:
        output = f"🤗 TOP {len(results)} modeli Hugging Face\n"
        if task:
            output += f"📋 Zadanie: {task}\n"
        if query:
            output += f"🔍 Zapytanie: {query}\n"
        output += "\n"

        for row in results:
            output += f"[{row['rank']}] {row['id']}\n"
            output += (
                f"📊 Pobrania: {row['downloads']:,} | ❤️ Polubienia: {row['likes']}\n"
            )
            output += f"🎯 Zadanie: {row['task']}\n"
            output += f"{row['compatibility']}\n"
            output += f"🏷️ Tagi: {row['tags']}\n"
            output += f"🔗 URL: {row['url']}\n\n"
        return output

    @kernel_function(
        name="get_model_card",
        description="Pobiera szczegółowy opis modelu (Model Card) z Hugging Face, zawierający informacje o architekturze, wymaganiach sprzętowych, licencji i przykładach użycia.",
    )
    def get_model_card(
        self,
        model_id: Annotated[str, "ID modelu (np. 'distilbert-base-uncased')"],
    ) -> str:
        """
        Pobiera Model Card (opis modelu).

        Args:
            model_id: ID modelu na Hugging Face

        Returns:
            Opis modelu lub komunikat o błędzie
        """
        logger.info(f"HuggingFaceSkill: get_model_card dla {model_id}")

        try:
            # Pobierz informacje o modelu
            model_info = self.api.model_info(model_id)

            # Pobierz README (Model Card)
            try:
                # Używamy card_data do pobrania treści
                card_content: str = (
                    str(model_info.card_data) if model_info.card_data else ""
                )

                # Jeśli card_data jest puste, spróbuj pobrać bezpośrednio
                if not card_content:
                    # Pobierz plik README.md
                    try:
                        readme_path = hf_hub_download(
                            repo_id=model_id,
                            filename="README.md",
                            repo_type="model",
                        )
                        # Użyj pathlib do bezpiecznego czytania pliku
                        card_content = Path(readme_path).read_text(encoding="utf-8")
                    except OSError as e:
                        logger.debug(f"Nie można pobrać README dla {model_id}: {e}")
                        card_content = "Brak dostępnego Model Card"
                else:
                    # card_content już jest stringiem
                    card_content = str(card_content)

            except Exception as e:
                logger.warning(f"Nie udało się pobrać Model Card: {e}")
                card_content = "Brak dostępnego Model Card"

            # Ogranicz długość
            if (
                isinstance(card_content, str)
                and len(card_content) > MAX_MODEL_CARD_LENGTH
            ):
                card_content = (
                    card_content[:MAX_MODEL_CARD_LENGTH]
                    + "\n\n[...Model Card obcięty...]"
                )

            # Formatuj wynik
            output = f"🤗 Model Card: {model_id}\n"
            output += f"🔗 URL: https://huggingface.co/{model_id}\n"
            output += f"📊 Pobrania: {getattr(model_info, 'downloads', 0):,}\n"
            output += f"❤️ Polubienia: {getattr(model_info, 'likes', 0)}\n"
            output += f"🎯 Zadanie: {getattr(model_info, 'pipeline_tag', 'Nieznane')}\n"

            # Licencja
            license_info = getattr(model_info, "card_data", {})
            if license_info and hasattr(license_info, "get"):
                license_name = license_info.get("license", "Nieznana")
            else:
                license_name = "Nieznana"
            output += f"📜 Licencja: {license_name}\n"

            # Tagi
            if model_info.tags:
                output += f"🏷️ Tagi: {', '.join(model_info.tags[:10])}\n"

            output += f"\n{'=' * 80}\n\n"
            output += str(card_content)

            logger.info(f"HuggingFaceSkill: pobrano Model Card dla {model_id}")
            return output

        except RepositoryNotFoundError:
            logger.warning(f"Model nie znaleziony: {model_id}")
            return f"❌ Model nie znaleziony: {model_id}"
        except Exception as e:
            logger.error(f"Błąd podczas pobierania Model Card: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"

    @kernel_function(
        name="search_datasets",
        description="Wyszukuje zbiory danych (datasets) na Hugging Face według zapytania. Użyj gdy użytkownik szuka danych do treningu lub testowania modeli.",
    )
    def search_datasets(
        self,
        query: Annotated[str, "Zapytanie tekstowe (np. 'sentiment', 'polish', 'qa')"],
    ) -> str:
        """
        Wyszukuje zbiory danych na Hugging Face.

        Args:
            query: Zapytanie tekstowe

        Returns:
            Sformatowana lista zbiorów danych
        """
        logger.info(f"HuggingFaceSkill: search_datasets dla '{query}'")

        try:
            # Wyszukaj datasets
            datasets = list(
                self.api.list_datasets(
                    search=query,
                    limit=MAX_DATASETS_RESULTS,
                    sort="downloads",
                )
            )

            if not datasets:
                return f"Nie znaleziono zbiorów danych dla zapytania: {query}"

            # Formatuj wyniki
            results = []
            for i, dataset in enumerate(datasets, 1):
                dataset_info = {
                    "rank": i,
                    "id": dataset.id,
                    "downloads": getattr(dataset, "downloads", 0),
                    "likes": getattr(dataset, "likes", 0),
                    "url": f"https://huggingface.co/datasets/{dataset.id}",
                    "tags": (
                        ", ".join(dataset.tags[:5]) if dataset.tags else "Brak tagów"
                    ),
                }
                results.append(dataset_info)

            output = f"🗂️ TOP {len(results)} zbiorów danych dla: '{query}'\n\n"
            for r in results:
                output += f"[{r['rank']}] {r['id']}\n"
                output += (
                    f"📊 Pobrania: {r['downloads']:,} | ❤️ Polubienia: {r['likes']}\n"
                )
                output += f"🏷️ Tagi: {r['tags']}\n"
                output += f"🔗 URL: {r['url']}\n\n"

            logger.info(f"HuggingFaceSkill: znaleziono {len(results)} zbiorów danych")
            return output.strip()

        except Exception as e:
            logger.error(f"Błąd podczas wyszukiwania zbiorów danych: {e}")
            return f"❌ Wystąpił błąd: {str(e)}"
