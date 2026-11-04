from types import ModuleType, SimpleNamespace
from typing import cast

from information_classifier_api.infrastructure.normalization.docling import (
    converter,
)


class FakeWhisperOptions:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeAsrPipelineOptions:
    def __init__(self, asr_options: object) -> None:
        self.asr_options = asr_options


class FakeVideoPipelineOptions:
    def __init__(self, asr_options: object) -> None:
        self.asr_options = asr_options


class FakeFormatOption:
    def __init__(self, pipeline_options: object) -> None:
        self.pipeline_options = pipeline_options


class FakeDocumentConverter:
    def __init__(self, format_options: dict[object, object]) -> None:
        self.format_options = format_options


def _module(**attributes: object) -> ModuleType:
    return cast(ModuleType, SimpleNamespace(**attributes))


def test_whisper_options_pass_model_language_and_disable_verbose_logs() -> None:
    asr_specs = _module(InlineAsrNativeWhisperOptions=FakeWhisperOptions)
    options = converter._whisper_options(asr_specs, "small", "pt")
    assert options.kwargs == {
        "repo_id": "small",
        "language": "pt",
        "verbose": False,
    }


def test_build_converter_uses_asr_for_audio_and_video_options() -> None:
    sentinel = object()
    audio = object()
    video = object()
    converter_module = _module(
        InputFormat=SimpleNamespace(AUDIO=audio, VIDEO=video),
        AudioFormatOption=FakeFormatOption,
        VideoFormatOption=FakeFormatOption,
        DocumentConverter=FakeDocumentConverter,
    )
    pipeline_options = _module(
        AsrPipelineOptions=FakeAsrPipelineOptions,
        VideoPipelineOptions=FakeVideoPipelineOptions,
    )
    built = converter._build_converter(converter_module, pipeline_options, sentinel)
    audio_options = built.format_options[audio].pipeline_options
    video_options = built.format_options[video].pipeline_options
    assert isinstance(audio_options, FakeAsrPipelineOptions)
    assert isinstance(video_options, FakeVideoPipelineOptions)
    assert audio_options.asr_options is sentinel
    assert video_options.asr_options is sentinel


def test_dependency_hint_mentions_asr_extra_for_whisper_errors() -> None:
    hint = converter._dependency_hint(ImportError("whisper ausente"))
    assert "extra 'asr'" in hint
    assert converter._dependency_hint(ValueError("outro erro")) == ""
