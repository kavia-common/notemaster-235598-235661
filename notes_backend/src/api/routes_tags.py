from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db import get_db_session
from src.api.repository import create_tag, delete_tag, list_tags, update_tag
from src.api.schemas import ErrorResponse, PageMeta, TagCreate, TagOut, TagsListResponse, TagUpdate

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get(
    "",
    response_model=TagsListResponse,
    summary="List tags",
    description="List tags with pagination and sorting.",
    operation_id="list_tags",
)
async def list_tags_endpoint(
    limit: int = Query(50, ge=1, le=100, description="Page size."),
    offset: int = Query(0, ge=0, description="Offset into the result set."),
    sort: str = Query("updated_at_desc", description="Sort mode: updated_at_desc|name_asc|name_desc"),
    session: AsyncSession = Depends(get_db_session),
) -> TagsListResponse:
    total, items = await list_tags(session, limit=limit, offset=offset, sort=sort)
    return TagsListResponse(meta=PageMeta(limit=limit, offset=offset, total=total), items=items)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TagOut,
    responses={400: {"model": ErrorResponse}},
    summary="Create a tag",
    description="Create a new tag. If the tag name already exists, returns the existing tag (idempotent).",
    operation_id="create_tag",
)
async def create_tag_endpoint(
    payload: TagCreate,
    session: AsyncSession = Depends(get_db_session),
) -> TagOut:
    tag_id = await create_tag(session, payload.name)
    await session.commit()

    # Re-select for full payload
    row = (
        await session.execute(
            # select in a simple way without duplicating repo helper
            # (note: this is safe and keeps router self-contained)
            __import__("sqlalchemy").text("SELECT id, name, created_at, updated_at FROM tags WHERE id = :id"),
            {"id": tag_id},
        )
    ).mappings().one()

    return TagOut(**dict(row))


@router.put(
    "/{tag_id}",
    response_model=TagOut,
    responses={404: {"model": ErrorResponse}},
    summary="Update a tag",
    description="Rename a tag (name must remain unique).",
    operation_id="update_tag",
)
async def update_tag_endpoint(
    tag_id: UUID,
    payload: TagUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> TagOut:
    existed = await update_tag(session, tag_id, payload.name)
    if not existed:
        raise HTTPException(status_code=404, detail="Tag not found.")
    await session.commit()

    row = (
        await session.execute(
            __import__("sqlalchemy").text("SELECT id, name, created_at, updated_at FROM tags WHERE id = :id"),
            {"id": tag_id},
        )
    ).mappings().one()
    return TagOut(**dict(row))


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
    summary="Delete a tag",
    description="Delete a tag by id (also deletes note_tags rows via cascade).",
    operation_id="delete_tag",
)
async def delete_tag_endpoint(
    tag_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await delete_tag(session, tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tag not found.")
    await session.commit()
    return None
