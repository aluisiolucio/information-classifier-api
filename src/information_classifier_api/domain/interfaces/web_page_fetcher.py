from typing import Protocol

from ..entities.fetched_page import FetchedPage


class WebPageFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedPage: ...
