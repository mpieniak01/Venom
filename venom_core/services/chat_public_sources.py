"""Operator-configured, bounded public sources for ordinary chat."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from venom_core.config import SETTINGS


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    article_hosts: tuple[str, ...]
    article_path_prefix: str


@dataclass(frozen=True)
class NewsRegion:
    match_terms: tuple[str, ...]
    search_domains: tuple[str, ...]
    article_hosts: tuple[str, ...]
    feeds: tuple[FeedSource, ...]


@dataclass(frozen=True)
class PublicSources:
    city_aliases: dict[str, str]
    default_region: str
    regions: dict[str, NewsRegion]

    def region_for(self, message: str) -> NewsRegion:
        lowered = message.casefold()
        for key, region in self.regions.items():
            if key != self.default_region and any(
                re.search(rf"(?<!\w){re.escape(term)}\w*", lowered)
                for term in region.match_terms
            ):
                return region
        return self.regions[self.default_region]


def _host(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Public source host must be text")
    host = value.lower().rstrip(".")
    if (
        len(host) > 253
        or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host)
        or any(part.startswith("-") or part.endswith("-") for part in host.split("."))
    ):
        raise ValueError(f"Invalid public source host: {value}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ValueError("IP literals are not allowed as public source hosts")


def _hosts(values: list[str]) -> tuple[str, ...]:
    if not isinstance(values, list) or len(values) > 10 or not values:
        raise ValueError("Source hosts must be a nonempty list of up to 10")
    return tuple(_host(item) for item in values)


def _feed(item: dict) -> FeedSource:
    url = item["url"]
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or len(url) > 1000
    ):
        raise ValueError("RSS feed requires a public HTTPS URL")
    _host(parsed.hostname)
    prefix = item.get("article_path_prefix", "/")
    if not isinstance(prefix, str) or not prefix.startswith("/") or len(prefix) > 100:
        raise ValueError("Invalid RSS article path prefix")
    name = item["name"]
    if not isinstance(name, str) or not 1 <= len(name) <= 80:
        raise ValueError("Invalid RSS source name")
    return FeedSource(name, url, _hosts(item["article_hosts"]), prefix)


def _city_aliases(aliases: dict) -> dict[str, str]:
    if not isinstance(aliases, dict) or len(aliases) > 300:
        raise ValueError("Invalid weather city aliases")
    clean_aliases = {}
    for form, city in aliases.items():
        if (
            not isinstance(form, str)
            or not isinstance(city, str)
            or not 1 <= len(city) <= 100
        ):
            raise ValueError("Invalid weather city alias")
        clean_aliases[form.casefold()] = city
    return clean_aliases


def _news_region(item: dict) -> NewsRegion:
    terms = item["match_terms"]
    if (
        not isinstance(terms, list)
        or len(terms) > 30
        or any(not isinstance(term, str) or not 1 <= len(term) <= 50 for term in terms)
    ):
        raise ValueError("Invalid news region match terms")
    domains = item["search_domains"]
    if not isinstance(domains, list) or len(domains) > 5:
        raise ValueError("Invalid news search domains")
    feeds = item["feeds"]
    if not isinstance(feeds, list) or len(feeds) > 3:
        raise ValueError("Invalid news feeds")
    return NewsRegion(
        tuple(term.casefold() for term in terms),
        tuple(_host(domain) for domain in domains),
        _hosts(item["article_hosts"]),
        tuple(_feed(feed) for feed in feeds),
    )


def load_public_sources(path: Path | None = None) -> PublicSources:
    """Read operator configuration; invalid sources fail closed in the caller."""
    if path is None:
        configured = Path(SETTINGS.CHAT_PUBLIC_SOURCES_CONFIG)
        path = Path(__file__).resolve().parents[2] / configured
    data = json.loads(path.read_text(encoding="utf-8"))
    aliases = _city_aliases(data["weather"]["city_aliases"])
    news = data["news"]
    region_configs = news["regions"]
    if not isinstance(region_configs, dict) or not 1 <= len(region_configs) <= 12:
        raise ValueError("Invalid news regions")
    regions = {key: _news_region(item) for key, item in region_configs.items()}
    default = news["default_region"]
    if default not in regions:
        raise ValueError("Default news region is missing")
    return PublicSources(aliases, default, regions)
