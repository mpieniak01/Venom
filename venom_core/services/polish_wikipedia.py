"""Bounded Polish Wikipedia lookup for grounding ordinary chat answers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

from venom_core.infrastructure.traffic_control import TrafficControlledHttpClient
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

WIKIPEDIA_API_URL = "https://pl.wikipedia.org/w/api.php"
WIKIPEDIA_USER_AGENT = (
    "Venom/0.1 (https://github.com/mpieniak01/Venom; Polish Wikipedia lookup)"
)
MAX_QUERY_CHARS = 256
MAX_EXTRACT_CHARS = 1200
MAX_RESULTS = 2


@dataclass(frozen=True)
class WikipediaSource:
    """Small source excerpt with attribution for the answering model and UI."""

    title: str
    url: str
    extract: str
    retrieved_at: str


def _clean_text(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


async def search_polish_wikipedia(
    query: str, *, limit: int = MAX_RESULTS
) -> list[WikipediaSource]:
    """Search article intros using one bounded MediaWiki Action API request.

    Network failures and missing articles return an empty list. Callers can then
    explicitly report that the source is unavailable instead of guessing.
    """
    cleaned_query = _clean_text(query, MAX_QUERY_CHARS)
    if not cleaned_query:
        return []
    result_limit = min(max(1, limit), MAX_RESULTS)
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": cleaned_query,
        "gsrnamespace": "0",
        "gsrlimit": str(result_limit),
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "exchars": str(MAX_EXTRACT_CHARS),
        "format": "json",
        "formatversion": "2",
    }
    try:
        async with TrafficControlledHttpClient(
            provider="wikipedia", timeout=8.0
        ) as client:
            response = await client.aget(
                WIKIPEDIA_API_URL,
                params=params,
                headers={"User-Agent": WIKIPEDIA_USER_AGENT},
                raise_for_status=False,
            )
        if response.status_code != 200:
            logger.warning("Wikipedia returned HTTP %s", response.status_code)
            return []
        payload = response.json()
    except Exception as exc:
        logger.warning("Polish Wikipedia lookup failed: %s", exc)
        return []

    return _extract_sources(payload, cleaned_query, result_limit)


def _extract_sources(
    payload: object, cleaned_query: str, result_limit: int
) -> list[WikipediaSource]:
    query_data = payload.get("query") if isinstance(payload, dict) else None
    pages = query_data.get("pages", []) if isinstance(query_data, dict) else []
    if not isinstance(pages, list):
        return []
    fetched_at = datetime.now(timezone.utc).isoformat()
    sources: list[WikipediaSource] = []
    # MediaWiki can rank a related team or place before an exact article title.
    ranked_pages = sorted(
        pages,
        key=lambda page: (
            not (
                isinstance(page, dict)
                and str(page.get("title", "")).casefold() == cleaned_query.casefold()
            ),
        ),
    )
    for page in ranked_pages[:result_limit]:
        if not isinstance(page, dict) or page.get("ns") != 0:
            continue
        title = page.get("title")
        extract = page.get("extract")
        if not isinstance(title, str) or not isinstance(extract, str):
            continue
        cleaned_title = _clean_text(title, 180)
        cleaned_extract = _clean_text(extract, MAX_EXTRACT_CHARS)
        if not cleaned_title or not cleaned_extract:
            continue
        article_path = quote(cleaned_title.replace(" ", "_"), safe="")
        sources.append(
            WikipediaSource(
                title=cleaned_title,
                url=f"https://pl.wikipedia.org/wiki/{article_path}",
                extract=cleaned_extract,
                retrieved_at=fetched_at,
            )
        )
    return sources
