import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from ..exceptions import UrlBlockedError

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "metadata",
    "metadata.google.internal",
    "metadata.azure.internal",
    "instance-data",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")


@dataclass(frozen=True)
class UrlPolicy:
    """Política sintática de URLs. Resolução DNS é validada no adaptador."""

    allowed_ports: frozenset[int]
    allowed_schemes: frozenset[str] = frozenset({"http", "https"})

    @classmethod
    def from_ports(cls, ports: list[int]) -> "UrlPolicy":
        return cls(allowed_ports=frozenset(ports))

    def validate(self, url: str) -> str:
        """Valida esquema/host/porta e retorna a URL canônica."""
        parts = _split_url(url)
        host = self._validate_host(parts.hostname, url)
        port = _validate_port(parts, self.allowed_ports, url)
        _reject_credentials(parts.username, parts.password, url)
        self._validate_scheme(parts.scheme, url)
        return _canonical(parts, host, port)

    def _validate_scheme(self, scheme: str, url: str) -> None:
        if scheme.lower() not in self.allowed_schemes:
            raise UrlBlockedError(
                url,
                f"esquema {scheme!r} não permitido; esperado http ou https",
            )

    def _validate_host(self, hostname: str | None, url: str) -> str:
        if not hostname:
            raise UrlBlockedError(url, "host ausente; esperado hostname público")
        host = hostname.rstrip(".").lower()
        try:
            host.encode("idna")
        except UnicodeError as exc:
            raise UrlBlockedError(url, f"hostname inválido: {host!r}") from exc
        if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
            raise UrlBlockedError(url, f"hostname interno bloqueado: {host!r}")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return host
        ensure_public_ip(host, str(address), url)
        return host


def _split_url(url: str):
    if not isinstance(url, str) or not url.strip():
        raise UrlBlockedError(url, "URL vazia; esperado http(s)://host/path")
    if len(url) > 2048:
        raise UrlBlockedError(url, f"URL com {len(url)} caracteres excede 2048")
    try:
        return urlsplit(url.strip())
    except ValueError as exc:
        raise UrlBlockedError(url, f"URL malformada: {exc}") from exc


def _validate_port(parts, allowed_ports: frozenset[int], url: str) -> int:
    default_port = 443 if parts.scheme.lower() == "https" else 80
    try:
        port = parts.port or default_port
    except ValueError as exc:
        raise UrlBlockedError(url, f"porta inválida: {exc}") from exc
    if port not in allowed_ports:
        raise UrlBlockedError(
            url,
            f"porta {port} não permitida; esperado uma de {sorted(allowed_ports)}",
        )
    return port


def _reject_credentials(username: str | None, password: str | None, url: str) -> None:
    if username is not None or password is not None:
        raise UrlBlockedError(url, "credenciais embutidas não são permitidas")


def _canonical(parts, host: str, port: int) -> str:
    default_port = 443 if parts.scheme.lower() == "https" else 80
    netloc = host if port == default_port else f"{host}:{port}"
    return urlunsplit(
        (parts.scheme.lower(), netloc, parts.path or "/", parts.query, "")
    )


def ensure_public_ip(host: str, address: str, url: str | None = None) -> None:
    """Bloqueia IP privado, loopback, link-local, multicast e reservado."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise UrlBlockedError(url or host, f"IP inválido {address!r}") from exc
    if not parsed.is_global or parsed.is_multicast or parsed.is_reserved:
        raise UrlBlockedError(
            url or host,
            f"endereço não público {address!r}; esperado IP global",
        )
