from typing import Protocol

from ..entities.provider_contracts import (
    ClassificationProviderResult,
    ClassificationRequest,
)


class RelevanceProvider(Protocol):
    async def classify(
        self, request: ClassificationRequest
    ) -> ClassificationProviderResult: ...
