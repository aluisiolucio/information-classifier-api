import asyncio


class InMemoryObjectStorage:
    """Storage em memória para testes e execução local sem MinIO.

    Não é compartilhado entre processos; em produção use S3/MinIO.
    """

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._lock = asyncio.Lock()

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        async with self._lock:
            self._objects[key] = (data, content_type)

    async def get_object(self, key: str) -> bytes:
        async with self._lock:
            item = self._objects.get(key)
        if item is None:
            raise FileNotFoundError(f"objeto não encontrado: {key}")
        return item[0]

    async def delete_object(self, key: str) -> None:
        async with self._lock:
            self._objects.pop(key, None)

    async def ensure_bucket(self) -> None:
        return None
