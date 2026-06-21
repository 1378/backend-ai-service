"""API route definitions for the backend AI service."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.models.contact import ContactRequest
from app.services.contact_service import (
    ContactService,
    ContactServiceResponse,
    RateLimitExceededError,
)
from app.services.metrics_service import MetricsService


def get_contact_service() -> ContactService:
    """Dependency provider — override at app startup with a real instance.

    In main.py:
        app.dependency_overrides[get_contact_service] = lambda: real_instance
    """
    raise RuntimeError("ContactService has not been configured")


ContactServiceDep = Annotated[ContactService, Depends(get_contact_service)]


def get_metrics_service() -> MetricsService:
    """Dependency provider — override at app startup with a real instance.

    In main.py:
        app.dependency_overrides[get_metrics_service] = lambda: real_instance
    """
    raise RuntimeError("MetricsService has not been configured")


MetricsServiceDep = Annotated[MetricsService, Depends(get_metrics_service)]

router = APIRouter()


@router.post(
    "/contact",
    response_model=ContactServiceResponse,
    status_code=status.HTTP_200_OK,
    tags=["contact"],
)
async def submit_contact(
    request: Request,
    body: ContactRequest,
    service: ContactServiceDep,
) -> ContactServiceResponse:
    """Process a contact form submission."""
    client_key = request.client.host if request.client else "unknown"
    try:
        return await service.process_contact(body, client_key)
    except RateLimitExceededError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


@router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return service liveness status."""
    return {"status": "ok"}


@router.get("/metrics", tags=["metrics"])
async def get_metrics(service: MetricsServiceDep) -> dict[str, Any]:
    """Return service metrics."""
    return await service.get_metrics()
