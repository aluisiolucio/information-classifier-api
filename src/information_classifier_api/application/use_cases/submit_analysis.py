from datetime import UTC, datetime
from uuid import UUID, uuid4

from ...domain.entities.analysis import Analysis, AnalysisStatus, InputType
from ...domain.entities.classification_rule import DEFAULT_RULE_PROMPT
from ...domain.exceptions import (
    DomainValidationError,
    PayloadTooLargeError,
)
from ...domain.interfaces.analysis_repository import AnalysisRepository
from ...domain.interfaces.classification_rule_repository import (
    ClassificationRuleRepository,
)
from ...domain.interfaces.object_storage import ObjectStorage
from ...domain.interfaces.url_validator import UrlValidator
from ...domain.services.text_normalizer import (
    extract_title,
    normalize_text_to_markdown,
)
from ...domain.services.upload_validator import validate_upload
from ..dto import (
    AnalysisInput,
    SubmitFileAnalysis,
    SubmitTextAnalysis,
    SubmitUrlAnalysis,
)


class SubmitAnalysis:
    """Cria uma análise de uma única origem e persiste o snapshot da regra.

    >>> SubmitAnalysis(analyses, rules, storage, validator, 1024, 1000)
    """

    def __init__(
        self,
        analyses: AnalysisRepository,
        rules: ClassificationRuleRepository,
        storage: ObjectStorage,
        url_validator: UrlValidator,
        max_upload_bytes: int,
        max_text_chars: int,
    ) -> None:
        self._analyses = analyses
        self._rules = rules
        self._storage = storage
        self._url_validator = url_validator
        self._max_upload_bytes = max_upload_bytes
        self._max_text_chars = max_text_chars

    async def execute(self, input: AnalysisInput) -> Analysis:
        analysis_id = uuid4()
        rule = await self._rules.get()
        prompt = rule.prompt if rule is not None else DEFAULT_RULE_PROMPT
        analysis = await self._build(analysis_id, input, prompt)
        await self._analyses.add(analysis)
        return analysis

    async def _build(
        self, analysis_id: UUID, input: AnalysisInput, prompt: str
    ) -> Analysis:
        if isinstance(input, SubmitTextAnalysis):
            return self._text_analysis(analysis_id, input.text, prompt)
        if isinstance(input, SubmitUrlAnalysis):
            return await self._url_analysis(analysis_id, input.url, prompt)
        if isinstance(input, SubmitFileAnalysis):
            return await self._file_analysis(analysis_id, input, prompt)
        raise DomainValidationError(
            f"origem não suportada: {type(input).__name__}; "
            "esperado texto, URL ou arquivo"
        )

    def _text_analysis(self, analysis_id: UUID, text: str, prompt: str) -> Analysis:
        markdown = normalize_text_to_markdown(text)
        if len(markdown) > self._max_text_chars:
            raise DomainValidationError(
                f"texto com {len(markdown)} caracteres excede "
                f"MAX_TEXT_CHARS={self._max_text_chars}"
            )
        return self._new_analysis(
            analysis_id,
            prompt,
            input_type=InputType.TEXT,
            source_text=markdown,
            title=extract_title(markdown),
        )

    async def _url_analysis(self, analysis_id: UUID, url: str, prompt: str) -> Analysis:
        canonical = await self._url_validator.validate(url)
        return self._new_analysis(
            analysis_id,
            prompt,
            input_type=InputType.URL,
            source_url=canonical,
        )

    async def _file_analysis(
        self, analysis_id: UUID, input: SubmitFileAnalysis, prompt: str
    ) -> Analysis:
        if len(input.data) > self._max_upload_bytes:
            raise PayloadTooLargeError(len(input.data), self._max_upload_bytes)
        upload = validate_upload(
            filename=input.filename,
            declared_media_type=input.declared_media_type,
            data=input.data,
        )
        storage_key = f"uploads/{analysis_id}/{upload.filename}"
        await self._storage.put_object(storage_key, input.data, upload.media_type)
        return self._new_analysis(
            analysis_id,
            prompt,
            input_type=InputType.FILE,
            source_filename=upload.filename,
            source_media_type=upload.media_type,
            storage_key=storage_key,
            title=upload.filename,
        )

    def _new_analysis(
        self,
        analysis_id: UUID,
        prompt: str,
        *,
        input_type: str,
        source_text: str | None = None,
        source_url: str | None = None,
        source_filename: str | None = None,
        source_media_type: str | None = None,
        storage_key: str | None = None,
        title: str | None = None,
    ) -> Analysis:
        return Analysis(
            id=analysis_id,
            input_type=input_type,
            status=AnalysisStatus.QUEUED,
            rule_prompt=prompt,
            created_at=datetime.now(UTC),
            source_text=source_text,
            source_url=source_url,
            source_filename=source_filename,
            source_media_type=source_media_type,
            storage_key=storage_key,
            title=title,
        )
