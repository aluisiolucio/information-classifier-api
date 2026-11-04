import socket


def resolve_addresses(host: str, port: int) -> list[str]:
    """Resolve um host para IPs únicos, validáveis contra SSRF.

    >>> resolve_addresses("localhost", 80)  # doctest: +SKIP
    ['127.0.0.1']
    """
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))
