import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..exceptions import InvalidUploadError, UnsupportedMediaTypeError

_MAX_FILENAME_CHARS = 255
_TEXT_EXTENSIONS = {".txt": "text/plain", ".md": "text/markdown"}
_DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}
_ALLOWED_EXTENSIONS = {**_DOCUMENT_TYPES, **_TEXT_EXTENSIONS}
_GENERIC_DECLARED_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
_DECLARED_ALIASES = {
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/m4a": "audio/mp4",
    "video/x-m4v": "video/mp4",
}


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str
    extension: str
    media_type: str


def validate_upload(
    *,
    filename: str,
    declared_media_type: str | None,
    data: bytes,
) -> ValidatedUpload:
    """Valida extensão, MIME declarado e assinatura real do arquivo.

    >>> validate_upload(
    ...     filename="nota.txt",
    ...     declared_media_type="text/plain",
    ...     data=b"oi",
    ... ).media_type
    'text/plain'
    """
    safe_filename = sanitize_filename(filename)
    extension = PurePosixPath(safe_filename).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise UnsupportedMediaTypeError(
            f"extensão {extension or '(vazia)'} não permitida; "
            f"esperado uma de {sorted(_ALLOWED_EXTENSIONS)}"
        )
    if not data:
        raise InvalidUploadError(f"arquivo vazio: {safe_filename!r}")
    detected = _detect_media_type(extension, data)
    _ensure_declared_type_matches(declared_media_type, detected)
    return ValidatedUpload(
        filename=safe_filename,
        extension=extension,
        media_type=detected,
    )


def sanitize_filename(filename: str) -> str:
    """Remove caminhos e caracteres de controle do nome enviado pelo cliente."""
    basename = PurePosixPath(filename.replace("\\", "/")).name
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", basename).strip()
    if not cleaned:
        raise InvalidUploadError("filename vazio; esperado nome de arquivo")
    if len(cleaned) > _MAX_FILENAME_CHARS:
        raise InvalidUploadError(
            f"filename com {len(cleaned)} caracteres excede "
            f"{_MAX_FILENAME_CHARS} caracteres"
        )
    return cleaned


def _detect_media_type(extension: str, data: bytes) -> str:
    if extension in _TEXT_EXTENSIONS:
        _ensure_utf8_text(data, extension)
        return _TEXT_EXTENSIONS[extension]
    if extension == ".pdf":
        _ensure_prefix(data, b"%PDF-", "PDF")
    elif extension in {".docx", ".pptx"}:
        _ensure_office_zip(data, extension)
    elif extension == ".png":
        _ensure_prefix(data, b"\x89PNG\r\n\x1a\n", "PNG")
    elif extension in {".jpg", ".jpeg"}:
        _ensure_prefix(data, b"\xff\xd8\xff", "JPEG")
    elif extension == ".webp":
        _ensure_prefix(data, b"RIFF", "WEBP")
        if data[8:12] != b"WEBP":
            raise InvalidUploadError("assinatura WEBP inválida: esperado 'WEBP'")
    elif extension == ".mp3":
        _ensure_mp3(data)
    elif extension == ".wav":
        _ensure_riff(data, b"WAVE", "WAV")
    elif extension in {".m4a", ".mp4", ".mov"}:
        _ensure_ftyp(data, extension)
    elif extension == ".ogg":
        _ensure_prefix(data, b"OggS", "OGG")
    elif extension == ".flac":
        _ensure_prefix(data, b"fLaC", "FLAC")
    elif extension == ".webm":
        _ensure_prefix(data, b"\x1aE\xdf\xa3", "WEBM")
    return _DOCUMENT_TYPES[extension]


def _ensure_prefix(data: bytes, prefix: bytes, label: str) -> None:
    if not data.startswith(prefix):
        raise InvalidUploadError(
            f"assinatura {label} inválida: esperado prefixo {prefix!r}"
        )


def _ensure_mp3(data: bytes) -> None:
    if not (data.startswith(b"ID3") or data[:2] in {b"\xff\xfb", b"\xff\xf3"}):
        raise InvalidUploadError("assinatura MP3 inválida: esperado ID3 ou frame MPEG")


def _ensure_riff(data: bytes, marker: bytes, label: str) -> None:
    if not data.startswith(b"RIFF") or data[8:12] != marker:
        raise InvalidUploadError(
            f"assinatura {label} inválida: esperado 'RIFF' e {marker!r}"
        )


def _ensure_ftyp(data: bytes, extension: str) -> None:
    if data[4:8] != b"ftyp":
        raise InvalidUploadError(
            f"assinatura {extension.upper()} inválida: esperado box 'ftyp'"
        )


def _ensure_office_zip(data: bytes, extension: str) -> None:
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise InvalidUploadError(
            f"arquivo {extension} não é um ZIP/OOXML válido"
        ) from exc
    required = "word/document.xml" if extension == ".docx" else "ppt/presentation.xml"
    if required not in names:
        raise InvalidUploadError(
            f"arquivo {extension} não contém {required!r}; "
            "assinatura não corresponde ao formato declarado"
        )


def _ensure_utf8_text(data: bytes, extension: str) -> None:
    if b"\x00" in data:
        raise InvalidUploadError(f"arquivo {extension} contém bytes NUL")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidUploadError(
            f"arquivo {extension} não é UTF-8 válido (byte {exc.start})"
        ) from exc


def _ensure_declared_type_matches(
    declared_media_type: str | None,
    detected: str,
) -> None:
    declared = (declared_media_type or "").split(";")[0].strip().lower()
    if declared in _GENERIC_DECLARED_TYPES:
        return
    canonical = _DECLARED_ALIASES.get(declared, declared)
    if canonical != detected:
        raise UnsupportedMediaTypeError(
            f"Content-Type declarado {declared!r} diverge do detectado "
            f"{detected!r}; esperado {detected!r}"
        )
