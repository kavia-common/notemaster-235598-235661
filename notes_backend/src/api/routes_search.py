from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db import get_db_session
from src.api.repository import search_notes
from src.api.schemas import PageMeta, SearchRequest, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "",
    response_model=SearchResponse,
    summary="Search notes",
    description="Search notes by text query across title/content. Optionally filter by tag ids and/or tag names.",
    operation_id="search_notes",
)
async def search_notes_endpoint(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> SearchResponse:
    total, items = await search_notes(
        session,
        q=payload.q,
        limit=payload.limit,
        offset=payload.offset,
        sort=payload.sort,
        tag_ids=payload.tag_ids,
        tag_names=payload.tag_names,
    )
    return SearchResponse(meta=PageMeta(limit=payload.limit, offset=payload.offset, total=total), items=items)
