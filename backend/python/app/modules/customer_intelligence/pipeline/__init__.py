"""Composable post-extraction pipeline for Customer Feature Intelligence."""
from __future__ import annotations

from app.modules.customer_intelligence.pipeline.context import ExtractionContext
from app.modules.customer_intelligence.pipeline.stages import (
    CanonicalizeToTopic,
    DedupeWithinEvent,
    ResolveCustomer,
    Stage,
    VerifyExcerpts,
)

DEFAULT_STAGES: list[Stage] = [
    VerifyExcerpts(),
    DedupeWithinEvent(),
    CanonicalizeToTopic(),
    ResolveCustomer(),
]


async def run_pipeline(
    ctx: ExtractionContext, stages: list[Stage] | None = None
) -> ExtractionContext:
    """Run stages in order. Append a new Stage to extend the harness."""
    for stage in stages or DEFAULT_STAGES:
        ctx = await stage.run(ctx)
    return ctx
