from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingLimits:
    max_extracted_chars: int
    prompt_max_chars: int
