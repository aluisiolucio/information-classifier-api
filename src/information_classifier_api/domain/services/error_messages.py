def sanitize_error_message(message: str, max_chars: int = 500) -> str:
    """Remove quebras de linha e limita o tamanho de mensagens persistidas.

    >>> sanitize_error_message("falha\\n na rede")
    'falha na rede'
    """
    cleaned = " ".join(str(message).split())
    return cleaned[:max_chars]
