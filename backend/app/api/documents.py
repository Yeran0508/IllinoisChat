import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
)
from pydantic import BaseModel

from app.dependencies import get_document_service, run_ingestion
from app.ingestion.service import DocumentIngestionService, DocumentNotFoundError

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentVersionResponse(BaseModel):
    id: uuid.UUID
    status: str
    media_type: str
    byte_size: int
    content_sha256: str
    embedding_model: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class DocumentResponse(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    source_name: str
    is_protected: bool
    versions: list[DocumentVersionResponse]


class DocumentRegistrationResponse(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    status: str
    reused: bool


class IngestionAcceptedResponse(BaseModel):
    document_id: uuid.UUID
    version_id: uuid.UUID
    status: str


@router.post("", response_model=DocumentRegistrationResponse)
async def register_document(
    response: Response,
    course_code: Annotated[str, Form()],
    course_name: Annotated[str, Form()],
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    service: Annotated[DocumentIngestionService, Depends(get_document_service)],
    is_protected: Annotated[bool, Form()] = False,
) -> DocumentRegistrationResponse:
    content = await file.read(service.max_upload_bytes + 1)
    media_type = (file.content_type or "").split(";", maxsplit=1)[0].strip().lower()
    try:
        result = service.register(
            course_code=course_code,
            course_name=course_name,
            title=title,
            source_name=file.filename or "",
            media_type=media_type,
            content=content,
            is_protected=is_protected,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    response.status_code = 200 if result.reused else 201
    return DocumentRegistrationResponse(**asdict(result))


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    service: Annotated[DocumentIngestionService, Depends(get_document_service)],
) -> DocumentResponse:
    try:
        document = service.get_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    versions = sorted(document.versions, key=lambda value: value.created_at, reverse=True)
    return DocumentResponse(
        id=document.id,
        course_id=document.course_id,
        title=document.title,
        source_name=document.source_name,
        is_protected=document.is_protected,
        versions=[
            DocumentVersionResponse.model_validate(value, from_attributes=True)
            for value in versions
        ],
    )


@router.post(
    "/{document_id}/ingest",
    response_model=IngestionAcceptedResponse,
    status_code=202,
)
def ingest_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    service: Annotated[DocumentIngestionService, Depends(get_document_service)],
    version_id: uuid.UUID | None = None,
) -> IngestionAcceptedResponse:
    try:
        document = service.get_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    versions = [
        value for value in document.versions if version_id is None or value.id == version_id
    ]
    if not versions:
        raise HTTPException(status_code=404, detail="Document version was not found")
    version = max(versions, key=lambda value: value.created_at)
    if version.status != "completed":
        background_tasks.add_task(run_ingestion, version.id)
    return IngestionAcceptedResponse(
        document_id=document.id,
        version_id=version.id,
        status=version.status,
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    service: Annotated[DocumentIngestionService, Depends(get_document_service)],
) -> None:
    try:
        service.delete_document(document_id)
    except DocumentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
