"""Bounded retrieval of published articles for current-news chat answers."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

MAX_ARTICLE_BYTES = 256_000
MAX_ARTICLE_CHARS = 2200
MAX_FEED_BYTES = 64_000


@dataclass(frozen=True)
class VerifiedArticle:
    url: str
    title: str
    published_at: str
    text: str


@dataclass(frozen=True)
class NewsHeadline:
    url: str
    title: str
    published_at: str


def trusted_news_url(url: str, allowed_hosts: Collection[str]) -> bool:
    """Permit only public HTTPS URLs under operator-approved source hosts."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        valid_structure = (
            parsed.scheme == "https"
            and not parsed.username
            and not parsed.password
            and parsed.port in {None, 443}
            and len(url) <= 1500
        )
    except ValueError:
        return False
    if not valid_structure:
        return False
    return any(
        host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts
    )


def _host_has_only_public_addresses(host: str) -> bool:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(
            ipaddress.ip_address(item[4][0]).is_global for item in addresses
        )
    except (OSError, ValueError):
        return False


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.dates: list[str] = []
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.article_parts: list[str] = []
        self.main_parts: list[str] = []
        self.body_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and (
            values.get("property") == "article:published_time"
            or values.get("name") in {"datePublished", "pubdate"}
            or values.get("itemprop") == "datePublished"
        ):
            if values.get("content"):
                self.dates.append(values["content"])
        if tag == "time" and values.get("datetime"):
            self.dates.append(values["datetime"])
        if tag not in {"meta", "link", "br", "img", "input", "hr"}:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value or set(self.stack) & {
            "script",
            "style",
            "nav",
            "header",
            "footer",
            "aside",
        }:
            return
        if "title" in self.stack:
            self.title_parts.append(value)
        if "h1" in self.stack:
            self.h1_parts.append(value)
        if "article" in self.stack:
            self.article_parts.append(value)
        if "main" in self.stack:
            self.main_parts.append(value)
        if "body" in self.stack:
            self.body_parts.append(value)


def _published_date(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if not isinstance(candidate, str) or len(candidate) > 40:
            continue
        try:
            parsed = datetime.fromisoformat(candidate.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        if 1990 <= parsed.year <= datetime.now().year + 1:
            return parsed.date().isoformat()
    return None


def _parse_article(url: str, data: bytes) -> VerifiedArticle | None:
    parser = _ArticleParser()
    parser.feed(data.decode("utf-8", errors="replace"))
    published = _published_date(parser.dates)
    if not published:
        return None
    title = " ".join(parser.h1_parts or parser.title_parts)[:180]
    text = " ".join(parser.article_parts or parser.main_parts or parser.body_parts)[
        :MAX_ARTICLE_CHARS
    ]
    if len(text) < 80 or not title:
        return None
    return VerifiedArticle(url=url, title=title, published_at=published, text=text)


async def fetch_verified_article(
    url: str,
    *,
    allowed_hosts: Collection[str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> VerifiedArticle | None:
    """Read one small HTML response; redirects, private DNS and undated pages fail closed."""
    if not trusted_news_url(url, allowed_hosts):
        return None
    host = urlparse(url).hostname or ""
    if not await asyncio.to_thread(_host_has_only_public_addresses, host):
        return None
    try:
        timeout = httpx.Timeout(8.0, connect=3.0)
        async with httpx.AsyncClient(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                "GET", url, headers={"User-Agent": "Venom/0.1 (public news lookup)"}
            ) as response:
                if response.status_code != 200:
                    return None
                if "text/html" not in response.headers.get("content-type", "").lower():
                    return None
                if int(response.headers.get("content-length", "0")) > MAX_ARTICLE_BYTES:
                    return None
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_ARTICLE_BYTES:
                        return None
                    chunks.append(chunk)
        return _parse_article(url, b"".join(chunks))
    except (httpx.HTTPError, ValueError, OSError):
        return None


async def fetch_rss_headlines(
    feed_url: str,
    *,
    article_hosts: Collection[str],
    article_path_prefix: str,
    today: date,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[NewsHeadline]:
    """Read at most two recent headlines from a configured public RSS feed."""
    parsed_feed = urlparse(feed_url)
    if not parsed_feed.hostname or not trusted_news_url(
        feed_url, (parsed_feed.hostname,)
    ):
        return []
    if transport is None and not await asyncio.to_thread(
        _host_has_only_public_addresses, parsed_feed.hostname
    ):
        return []
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(8.0, connect=3.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                "GET", feed_url, headers={"User-Agent": "Venom/0.1"}
            ) as response:
                if (
                    response.status_code != 200
                    or "xml" not in response.headers.get("content-type", "").lower()
                ):
                    return []
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_FEED_BYTES:
                        return []
        payload = data.decode("utf-8")
        if "<!DOCTYPE" in payload.upper() or "<!ENTITY" in payload.upper():
            return []
        root = ElementTree.fromstring(payload)
    except (httpx.HTTPError, OSError, UnicodeError, ValueError, ElementTree.ParseError):
        return []
    headlines: list[NewsHeadline] = []
    for item in root.findall("./channel/item")[:25]:
        title = " ".join((item.findtext("title") or "").split())[:180]
        url = (item.findtext("link") or "").strip()
        published_text = item.findtext("pubDate") or ""
        try:
            published = parsedate_to_datetime(published_text)
            parsed = urlparse(url)
            port = parsed.port
        except (TypeError, ValueError, IndexError):
            continue
        if (
            published.tzinfo is None
            or not title
            or not (
                trusted_news_url(url, article_hosts)
                and parsed.path.startswith(article_path_prefix)
                and port in {None, 443}
            )
        ):
            continue
        age = (today - published.astimezone(timezone.utc).date()).days
        if not 0 <= age <= 2:
            continue
        headlines.append(
            NewsHeadline(
                url=url,
                title=title,
                published_at=published.astimezone(timezone.utc).date().isoformat(),
            )
        )
        if len(headlines) == 2:
            break
    return headlines
