from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db import get_db_session
from src.api.repository import (
    create_note,
    ensure_tags_by_names,
    get_note,
    list_notes,
    replace_note_tags,
    update_note,
    delete_note,
)
from src.api.schemas import ErrorResponse, NoteCreate, NoteOut, NoteUpdate, NotesListResponse, PageMeta

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get(
    "",
    response_model=NotesListResponse,
    responses={400: {"model": ErrorResponse}},
    summary="List notes",
    description="List notes with pagination and sorting. Optionally filter by a single tag (by id or name).",
    operation_id="list_notes",
)
async def list_notes_endpoint(
    limit: int = Query(20, ge=1, le=100, description="Page size."),
    offset: int = Query(0, ge=0, description="Offset into the result set."),
    sort: str = Query(
        "updated_at_desc",
        description="Sort mode: updated_at_desc|updated_at_asc|created_at_desc|created_at_asc|title_asc|title_desc",
    ),
    tag_id: Optional[UUID] = Query(None, description="Optional filter: only notes having this tag UUID."),
    tag_name: Optional[str] = Query(None, description="Optional filter: only notes having this tag name."),
    session: AsyncSession = Depends(get_db_session),
) -> NotesListResponse:
    if tag_id and tag_name:
        raise HTTPException(status_code=400, detail="Provide either tag_id or tag_name, not both.")

    total, items = await list_notes(session, limit=limit, offset=offset, sort=sort, tag_id=tag_id, tag_name=tag_name)
    return NotesListResponse(meta=PageMeta(limit=limit, offset=offset, total=total), items=items)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=NoteOut,
    responses={400: {"model": ErrorResponse}},
    summary="Create a note",
    description="Create a note and optionally assign tags by UUIDs and/or tag names (missing tags will be created).",
    operation_id="create_note",
)
async def create_note_endpoint(
    payload: NoteCreate,
    session: AsyncSession = Depends(get_db_session),
) -> NoteOut:
    tag_ids = list(payload.tag_ids)
    if payload.tag_names:
        ensured = await ensure_tags_by_names(session, payload.tag_names)
        tag_ids.extend(ensured)

    note_id = await create_note(session, title=payload.title, content=payload.content, tag_ids=tag_ids)
    await session.commit()

    note = await get_note(session, note_id)
    assert note is not None
    return note


@router.get(
    "/{note_id}",
    response_model=NoteOut,
    responses={404: {"model": ErrorResponse}},
    summary="Get a note",
    description="Fetch a single note by id including its tags.",
    operation_id="get_note",
)
async def get_note_endpoint(
    note_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> NoteOut:
    note = await get_note(session, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found.")
    return note


@router.put(
    "/{note_id}",
    response_model=NoteOut,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    summary="Update a note",
    description="Update note fields and optionally replace tag assignments (by UUIDs or names).",
    operation_id="update_note",
)
async def update_note_endpoint(
    note_id: UUID,
    payload: NoteUpdate,
    session: AsyncSession = Depends(get_db_session),
) -> NoteOut:
    existed = await update_note(session, note_id=note_id, title=payload.title, content=payload.content)
    if not existed:
        raise HTTPException(status_code=404, detail="Note not found.")

    # Replace tags only if the client provided tag info
    if payload.tag_ids is not None or payload.tag_names is not None:
        new_tag_ids = list(payload.tag_ids or [])
        if payload.tag_names:
            ensured = await ensure_tags_by_names(session, payload.tag_names)
            new_tag_ids.extend(ensured)
        await replace_note_tags(session, note_id, new_tag_ids)

    await session.commit()

    note = await get_note(session, note_id)
    assert note is not None
    return note


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
    summary="Delete a note",
    description="Delete a note by id (also deletes note_tags rows via cascade).",
    operation_id="delete_note",
)
async def delete_note_endpoint(
    note_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await delete_note(session, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found.")
    await session.commit()
    return None
