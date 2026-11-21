"""Bounded Polish Wikipedia lookup for grounding ordinary chat answers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

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
MAX_SECTION_HTML = 150_000


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


class _SectionText(HTMLParser):
    """Preserve paragraph boundaries and omit scripts and reference markers."""

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "sup"}:
            self.ignored.append(tag)
        elif tag in {"p", "li", "div", "br", "h2", "h3", "dt", "dd", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.ignored and self.ignored[-1] == tag:
            self.ignored.pop()

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


async def search_wikipedia_section(
    source: WikipediaSource, headings: Sequence[str]
) -> WikipediaSource | None:
    """Read one named section from the same Polish Wikipedia article."""

    headers = {"User-Agent": WIKIPEDIA_USER_AGENT}
    params = {
        "action": "parse",
        "page": source.title,
        "format": "json",
        "formatversion": "2",
    }
    wanted = {heading.casefold() for heading in headings}
    try:
        async with TrafficControlledHttpClient(
            provider="wikipedia", timeout=8.0
        ) as client:
            sections_response = await client.aget(
                WIKIPEDIA_API_URL,
                params={**params, "prop": "sections"},
                headers=headers,
                raise_for_status=False,
            )
            if sections_response.status_code != 200:
                return None
            sections = sections_response.json().get("parse", {}).get("sections", [])
            index = next(
                (
                    section["index"]
                    for section in sections
                    if isinstance(section, dict)
                    and str(section.get("line", "")).strip().casefold() in wanted
                    and re.fullmatch(r"[1-9]\d{0,2}", str(section.get("index", "")))
                ),
                None,
            )
            if index is None:
                return None
            section_response = await client.aget(
                WIKIPEDIA_API_URL,
                params={**params, "prop": "text", "section": index},
                headers=headers,
                raise_for_status=False,
            )
        if section_response.status_code != 200:
            return None
        parsed = section_response.json().get("parse", {})
        html = parsed.get("text")
        if (
            parsed.get("title") != source.title
            or not isinstance(html, str)
            or len(html) > MAX_SECTION_HTML
        ):
            return None
        parser = _SectionText()
        parser.feed(html)
        excerpt = "\n".join(
            filter(
                None,
                (" ".join(line.split()) for line in "".join(parser.parts).splitlines()),
            )
        )[:MAX_EXTRACT_CHARS]
        return (
            WikipediaSource(source.title, source.url, excerpt, source.retrieved_at)
            if excerpt
            else None
        )
    except (AttributeError, TypeError, ValueError, OSError, httpx.HTTPError) as exc:
        logger.warning("Polish Wikipedia section lookup failed: %s", exc)
        return None
