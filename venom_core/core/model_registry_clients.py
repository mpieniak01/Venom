"""Klienci I/O dla ModelRegistry (HTTP i subprocess)."""

import asyncio
import html
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class OllamaClient:
    """Klient do integracji z Ollama (HTTP + CLI)."""

    def __init__(self, endpoint: str = "http://localhost:11434"):
        self.endpoint = endpoint.rstrip("/")

    async def list_tags(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                response = await client.get(f"{self.endpoint}/api/tags")
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"Ollama list_tags failed: {e}")
                return {"models": []}

    async def search_models(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Przeszukuje modele na ollama.com (scraping)."""
        url = "https://ollama.com/search"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, params={"q": query})
                response.raise_for_status()
                return _parse_ollama_search_html(response.text, limit)
            except Exception as e:
                logger.warning(f"Ollama search failed: {e}")
                return []

    async def pull_model(
        self, model_name: str, progress_callback: Optional[Callable] = None
    ) -> bool:
        try:
            process = await asyncio.create_subprocess_exec(
                "ollama",
                "pull",
                model_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                if process.stdout is None or process.stderr is None:
                    logger.error("Nie udało się zainicjalizować strumieni Ollama")
                    return False
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode().strip()
                    logger.info(f"Ollama: {line_str}")
                    if progress_callback:
                        await progress_callback(line_str)

                await process.wait()
                if process.returncode == 0:
                    return True
                stderr = await process.stderr.read()
                logger.error(f"❌ Błąd podczas pobierania modelu: {stderr.decode()}")
                return False
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

        except FileNotFoundError:
            logger.error("Ollama nie jest zainstalowane lub niedostępne w PATH")
            return False
        except Exception as exc:
            logger.error(f"Błąd podczas pobierania modelu: {exc}")
            return False

    async def remove_model(self, model_name: str) -> bool:
        try:
            result = subprocess.run(
                ["ollama", "rm", model_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True
            logger.error(f"❌ Błąd podczas usuwania modelu: {result.stderr}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Timeout podczas usuwania modelu z Ollama")
            return False
        except FileNotFoundError:
            logger.error("Ollama nie jest zainstalowane")
            return False
        except Exception as exc:
            logger.error(f"Błąd podczas usuwania modelu: {exc}")
            return False


class HuggingFaceClient:
    """Klient do integracji z HuggingFace (HTTP + snapshot download)."""

    def __init__(self, token: Optional[str] = None):
        self.token = token

    async def list_models(self, sort: str, limit: int) -> List[Dict[str, Any]]:
        url = "https://huggingface.co/api/models"
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    url,
                    params={"limit": limit, "sort": sort},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError:
                if sort != "trendingScore":
                    raise
                response = await client.get(
                    url,
                    params={"limit": limit, "sort": "downloads"},
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()

        return payload if isinstance(payload, list) else []

    async def search_models(self, query: str, limit: int) -> List[Dict[str, Any]]:
        url = "https://huggingface.co/api/models"
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    url,
                    params={
                        "search": query,
                        "limit": limit,
                        "sort": "downloads",
                        "filter": "text-generation",  # Filter for text gen models
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, list) else []
            except Exception as e:
                logger.warning(f"HF search failed: {e}")
                return []

    async def fetch_blog_feed(self, limit: int) -> List[Dict[str, Any]]:
        url = "https://huggingface.co/blog/feed.xml"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.text

        return _parse_hf_blog_feed(payload, limit)

    async def fetch_papers_month(
        self, limit: int, month: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if month:
            target_month = month
        else:
            target_month = datetime.now().strftime("%Y-%m")
        url = f"https://huggingface.co/papers/month/{target_month}"
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            if response.is_redirect and response.headers.get("location"):
                redirect_url = response.headers["location"]
                if redirect_url.startswith("/"):
                    redirect_url = f"https://huggingface.co{redirect_url}"
                response = await client.get(redirect_url)
            response.raise_for_status()
            payload = response.text

        return _parse_hf_papers_html(payload, url, limit)

    async def download_snapshot(
        self,
        model_name: str,
        cache_dir: str,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[str]:
        try:
            from huggingface_hub import snapshot_download as hf_snapshot_download
        except ImportError:
            logger.error(
                "Biblioteka huggingface_hub nie jest zainstalowana. "
                "Zainstaluj: pip install huggingface_hub"
            )
            return None

        if progress_callback:
            await progress_callback(f"Pobieranie {model_name} z HuggingFace...")

        local_path = await asyncio.to_thread(
            hf_snapshot_download,
            repo_id=model_name,
            cache_dir=cache_dir,
            token=self.token,
            resume_download=True,
        )
        return local_path

    def remove_cached_model(self, cache_dir: Path, model_name: str) -> bool:
        model_cache_dir = (cache_dir / model_name.replace("/", "--")).resolve()
        cache_root = cache_dir.resolve()

        if not model_cache_dir.is_relative_to(cache_root):
            logger.error(f"Nieprawidłowa ścieżka modelu: {model_name}")
            return False

        if model_cache_dir.exists():
            try:
                shutil.rmtree(model_cache_dir)
                return True
            except Exception as exc:
                logger.error(f"Błąd podczas usuwania modelu: {exc}")
                return False
        logger.warning(f"Model {model_name} nie znaleziony w cache")
        return False


def _parse_hf_blog_feed(payload: str, limit: int) -> List[Dict[str, Any]]:
    try:
        import xml.etree.ElementTree as ET
    except Exception:
        return []

    root = ET.fromstring(payload)
    channel = root.find("channel")
    if channel is None:
        return []

    items: List[Dict[str, Any]] = []
    for entry in channel.findall("item")[:limit]:
        title = entry.findtext("title")
        url_value = entry.findtext("link")
        summary = entry.findtext("description")
        published_at = entry.findtext("pubDate")
        if summary:
            summary = re.sub(r"<[^>]+>", "", summary).strip()
        items.append(
            {
                "title": title,
                "url": url_value,
                "summary": summary,
                "published_at": published_at,
                "authors": None,
                "source": "huggingface",
            }
        )
    return items


def _parse_hf_papers_html(payload: str, url: str, limit: int) -> List[Dict[str, Any]]:
    marker = 'data-target="DailyPapers" data-props="'
    start_index = payload.find(marker)
    if start_index == -1:
        logger.warning(
            "Nie znaleziono sekcji DailyPapers na stronie HuggingFace: %s", url
        )
        return []
    start_index += len(marker)
    end_index = payload.find('"', start_index)
    if end_index == -1:
        logger.warning(
            "Nieprawidłowy format atrybutu data-props w sekcji DailyPapers na stronie HuggingFace: %s",
            url,
        )
        return []

    raw_props = html.unescape(payload[start_index:end_index])
    try:
        data = json.loads(raw_props)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Nie udało się sparsować JSON z atrybutu data-props w sekcji DailyPapers na stronie HuggingFace (%s): %s",
            url,
            exc,
        )
        return []
    if not isinstance(data, dict):
        logger.warning(
            "Nieoczekiwany format danych DailyPapers z HuggingFace (oczekiwano dict) dla URL: %s",
            url,
        )
        return []
    daily_papers = data.get("dailyPapers")
    if not isinstance(daily_papers, list):
        logger.warning(
            "Brak lub nieprawidłowy klucz 'dailyPapers' w danych z HuggingFace dla URL: %s",
            url,
        )
        return []

    items: List[Dict[str, Any]] = []
    for entry in daily_papers[:limit]:
        paper = entry.get("paper", {})
        paper_id = paper.get("id")
        title = entry.get("title") or paper.get("title")
        summary = entry.get("summary") or paper.get("summary")
        published_at = entry.get("publishedAt") or paper.get("publishedAt")
        authors = [
            author.get("name")
            for author in (paper.get("authors") or [])
            if isinstance(author, dict) and author.get("name")
        ]
        url_value = f"https://huggingface.co/papers/{paper_id}" if paper_id else None
        items.append(
            {
                "title": title,
                "url": url_value,
                "summary": summary,
                "published_at": published_at,
                "authors": authors,
                "source": "huggingface",
            }
        )
    return items


def _parse_ollama_search_html(payload: str, limit: int) -> List[Dict[str, Any]]:
    """Parsuje wyniki wyszukiwania z ollama.com."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("Brak biblioteki bs4 (beautifulsoup4)")
        return []

    soup = BeautifulSoup(payload, "html.parser")
    # Zakładamy, że wyniki są w liście <ul> -> <li>
    # Struktura na dzień 2024:
    # <li class="...">
    #   <a href="/library/modelname">
    #     <span class="...">modelname</span>
    #     <span class="...">description</span>
    #   </a>

    # Przystosowanie do potencjalnych zmian struktury - szukamy linków do /library/
    results = []

    seen = set()

    # Znajdźmy kontener wyników (zazwyczaj główny content)
    # create a resilient finder
    anchors = soup.find_all("a", href=True)

    for a in anchors:
        href = str(a["href"])
        parts = href.split("/")
        # Check if we have enough parts and the last part is not empty
        if href.startswith("/library/") and len(parts) >= 3:
            model_name = parts[-1]
            if not model_name:
                continue

            if model_name in seen:
                continue

            # W aktualnym layout ollama.com, opis jest w <p> poniżej tytułu wewnątrz <a>
            description = ""
            desc_tag = a.find("p")
            if desc_tag:
                description = desc_tag.get_text(strip=True)
            else:
                # Fallback: tekst elementu minus nazwa
                full_text = a.get_text(" ", strip=True)
                if model_name in full_text:
                    description = full_text.replace(model_name, "", 1).strip()

            results.append(
                {
                    "name": model_name,
                    "description": description,
                    "provider": "ollama",
                    "source": "ollama",
                    "runtime": "ollama",
                }
            )
            seen.add(model_name)

            if len(results) >= limit:
                break

    return results
