from typing import Protocol


class UrlValidator(Protocol):
    async def validate(self, url: str) -> str: ...
