"""Extraction Service HTTP API routes.

Endpoints
---------
POST /api/v1/extract/classify
    Run LLM document classification on a BlocksContainer.
POST /api/v1/extract/feature-intelligence
    Run LLM pain-point / feature-gap extraction on a customer-signal text.

GET  /health
    Standard health probe (defined in extraction_main.py).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.models.blocks import BlocksContainer
from app.models.intelligence import FeatureIntelligenceExtractionResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/extract", tags=["extraction"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ClassifyRequest(BaseModel):
    block_container: BlocksContainer
    org_id: str
    departments: list[str] = []


class ClassifyResponse(BaseModel):
    success: bool
    classification: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# POST /api/v1/extract/classify
# ---------------------------------------------------------------------------


@router.post(
    "/classify",
    response_model=ClassifyResponse,
    summary="LLM document classification",
)
async def classify(request: Request, body: ClassifyRequest) -> JSONResponse:
    """Classify a document (departments, topics, summary, sentiment).

    ``departments`` should be pre-fetched by the caller (e.g. from the graph
    DB) to avoid introducing a graph connection dependency here.
    """
    document_extraction = request.app.state.document_extraction

    try:
        classification = await document_extraction.classify(
            blocks=body.block_container.blocks,
            org_id=body.org_id,
            departments=body.departments or None,
        )
        if classification is None:
            metadata = None
        else:
            from app.models.blocks import SemanticMetadata  # noqa: PLC0415
            metadata = SemanticMetadata(
                departments=classification.departments,
                languages=classification.languages,
                topics=classification.topics,
                summary=classification.summary,
                categories=[classification.category],
                sub_category_level_1=classification.subcategories.level1,
                sub_category_level_2=classification.subcategories.level2,
                sub_category_level_3=classification.subcategories.level3,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error during classification for org '%s'", body.org_id
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ClassifyResponse(success=False, error=str(exc)).model_dump(),
        )

    if metadata is None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=ClassifyResponse(success=True, classification=None).model_dump(),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ClassifyResponse(
            success=True, classification=metadata.model_dump()
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/extract/feature-intelligence
# ---------------------------------------------------------------------------


class FeatureIntelligenceRequest(BaseModel):
    text: str
    org_id: str
    infer_customer: bool = False


class FeatureIntelligenceResponse(BaseModel):
    success: bool
    result: dict | None = None
    error: str | None = None


@router.post(
    "/feature-intelligence",
    response_model=FeatureIntelligenceResponse,
    summary="LLM customer pain-point / feature-gap extraction",
)
async def extract_feature_intelligence(
    request: Request, body: FeatureIntelligenceRequest
) -> JSONResponse:
    """Extract evidence-backed pain points and feature gaps from customer-signal text.

    Used by the Customer Feature Intelligence pipeline (any connector's
    ticket/CRM-note/call-transcript/document text), independent of the
    document-classification path above.
    """
    extractor = request.app.state.feature_intelligence_extractor

    try:
        result: FeatureIntelligenceExtractionResult | None = await extractor.extract(
            text=body.text, org_id=body.org_id, infer_customer=body.infer_customer
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error during feature-intelligence extraction for org '%s'", body.org_id
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=FeatureIntelligenceResponse(success=False, error=str(exc)).model_dump(),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=FeatureIntelligenceResponse(
            success=True,
            result=result.model_dump() if result is not None else FeatureIntelligenceExtractionResult().model_dump(),
        ).model_dump(),
    )
