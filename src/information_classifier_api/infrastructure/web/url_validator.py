import asyncio
import socket
from urllib.parse import urlsplit

from ...domain.exceptions import UrlBlockedError
from ...domain.interfaces.url_validator import UrlValidator
from ...domain.services.url_policy import UrlPolicy, ensure_public_ip
from .dns import resolve_addresses

_RESOLVE_TIMEOUT_SECONDS = 5


class DnsUrlValidator(UrlValidator):
    """Valida sintaxe e todos os IPs resolvidos antes de enfileirar a URL."""

    def __init__(self, policy: UrlPolicy) -> None:
        self._policy = policy

    async def validate(self, url: str) -> str:
        canonical = self._policy.validate(url)
        await self._validate_dns(canonical)
        return canonical

    async def _validate_dns(self, canonical: str) -> None:
        parts = urlsplit(canonical)
        host = parts.hostname
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if host is None:
            raise UrlBlockedError(canonical, "host ausente após canonicalização")
        try:
            addresses = await asyncio.wait_for(
                asyncio.to_thread(resolve_addresses, host, port),
                timeout=_RESOLVE_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise UrlBlockedError(
                canonical, f"DNS de {host!r} excedeu {_RESOLVE_TIMEOUT_SECONDS}s"
            ) from exc
        except socket.gaierror as exc:
            raise UrlBlockedError(
                canonical, f"DNS de {host!r} não resolveu: {exc.strerror}"
            ) from exc
        if not addresses:
            raise UrlBlockedError(canonical, f"DNS de {host!r} retornou lista vazia")
        for address in addresses:
            ensure_public_ip(host, address, canonical)
