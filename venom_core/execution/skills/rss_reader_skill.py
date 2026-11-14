"""Configured, read-only public news feed skill."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from venom_core.execution.agent_contracts import tool_function as kernel_function
from venom_core.services.chat_public_sources import FeedSource, load_public_sources
from venom_core.services.verified_web import NewsHeadline, fetch_rss_headlines


class RSSReaderSkill:
    """Read bounded headlines from operator-approved regional feeds."""

    async def read_feed(self, feed: FeedSource) -> list[NewsHeadline]:
        return await fetch_rss_headlines(
            feed.url,
            article_hosts=feed.article_hosts,
            article_path_prefix=feed.article_path_prefix,
            today=datetime.now(timezone.utc).date(),
        )

    @kernel_function(
        name="get_headlines",
        description="Czyta aktualne nagłówki z kanałów RSS skonfigurowanych dla regionu.",
    )
    async def get_headlines(
        self, region: Annotated[str, "Klucz skonfigurowanego regionu wiadomości"]
    ) -> str:
        try:
            sources = load_public_sources()
        except (OSError, ValueError, KeyError, TypeError):
            return "Źródła wiadomości są niedostępne."
        selected = sources.regions.get(region)
        if selected is None:
            return "Region wiadomości nie jest skonfigurowany."
        for feed in selected.feeds:
            headlines = await self.read_feed(feed)
            if headlines:
                lines = [
                    f"{item.title} | {item.published_at} | {item.url}"
                    for item in headlines
                ]
                return f"Źródło: {feed.name} ({feed.url})\n" + "\n".join(lines)
        return "Brak aktualnych nagłówków w skonfigurowanych kanałach."
