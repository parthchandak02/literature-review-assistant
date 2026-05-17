"""Execution profile tuning for runtime speed/quality tradeoffs."""

from __future__ import annotations

from src.models import ReviewConfig, SettingsConfig


def apply_execution_profile(review: ReviewConfig, settings: SettingsConfig) -> None:
    """Apply optional speed/quality presets by mutating existing settings fields."""
    profile = review.execution_profile
    if profile == "balanced":
        return
    if profile == "throughput":
        settings.screening.calibrate_threshold = False
        settings.screening.screening_concurrency = min(max(settings.screening.screening_concurrency, 8), 20)
        settings.screening.batch_screen_concurrency = min(max(settings.screening.batch_screen_concurrency, 4), 10)
        settings.extraction.extraction_concurrency = min(max(settings.extraction.extraction_concurrency, 6), 16)
        settings.rag.embed_concurrency = min(max(settings.rag.embed_concurrency, 6), 16)
        settings.rag.use_hyde = False
        settings.rag.candidate_k = max(8, min(settings.rag.candidate_k, 14))
        settings.rag.final_k = max(4, min(settings.rag.final_k, 6))
        settings.writing.writing_concurrency = min(max(settings.writing.writing_concurrency, 4), 10)
        return
    if profile == "max_quality":
        settings.screening.calibrate_threshold = True
        settings.screening.batch_screen_uncertain_band = max(settings.screening.batch_screen_uncertain_band, 0.05)
        settings.screening.batch_screen_validation_fraction = max(
            settings.screening.batch_screen_validation_fraction, 0.20
        )
        settings.screening.batch_screen_validation_max_sample = max(
            settings.screening.batch_screen_validation_max_sample, 100
        )
        settings.screening.max_llm_screen = None
        settings.screening.empty_abstract_rescue_sample_size = max(
            settings.screening.empty_abstract_rescue_sample_size, 12
        )
        settings.rag.use_hyde = True
        settings.rag.rerank = True
        settings.rag.candidate_k = min(max(settings.rag.candidate_k, 28), 100)
        settings.rag.final_k = min(max(settings.rag.final_k, 10), 50)
        settings.rag.min_chunks_per_section = max(settings.rag.min_chunks_per_section, 2)
        return
    raise ValueError(f"Unsupported execution_profile: {profile}")
