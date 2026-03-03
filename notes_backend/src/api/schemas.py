from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Unique tag name (1..50 chars).")


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="New unique tag name (1..50 chars).")


class TagOut(TagBase):
    id: UUID = Field(..., description="Tag UUID.")
    created_at: datetime = Field(..., description="Tag creation time (UTC).")
    updated_at: datetime = Field(..., description="Tag last update time (UTC).")


class NoteBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Note title (<= 200 chars).")
    content: str = Field(..., description="Note body content (markdown/plain text).")


class NoteCreate(NoteBase):
    tag_ids: List[UUID] = Field(default_factory=list, description="Optional list of tag UUIDs to assign.")
    tag_names: List[str] = Field(
        default_factory=list,
        description="Optional list of tag names to create/ensure and assign (case-insensitive match).",
    )


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="Updated note title.")
    content: Optional[str] = Field(None, description="Updated note content.")
    tag_ids: Optional[List[UUID]] = Field(None, description="Replace tag assignments with these tag UUIDs.")
    tag_names: Optional[List[str]] = Field(
        None, description="Replace tag assignments with these tag names (will create missing tags)."
    )


class NoteOut(NoteBase):
    id: UUID = Field(..., description="Note UUID.")
    created_at: datetime = Field(..., description="Note creation time (UTC).")
    updated_at: datetime = Field(..., description="Note last update time (UTC).")
    tags: List[TagOut] = Field(default_factory=list, description="Tags assigned to this note.")


class PageMeta(BaseModel):
    limit: int = Field(..., ge=1, le=100, description="Page size.")
    offset: int = Field(..., ge=0, description="Offset into result set.")
    total: int = Field(..., ge=0, description="Total number of results matching the query.")


class NotesListResponse(BaseModel):
    meta: PageMeta
    items: List[NoteOut]


class TagsListResponse(BaseModel):
    meta: PageMeta
    items: List[TagOut]


class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, description="Search query text.")
    tag_ids: List[UUID] = Field(default_factory=list, description="Optional filter: only notes with these tag UUIDs.")
    tag_names: List[str] = Field(
        default_factory=list, description="Optional filter: only notes with these tag names (case-insensitive)."
    )
    limit: int = Field(20, ge=1, le=100, description="Max number of notes to return.")
    offset: int = Field(0, ge=0, description="Offset into matching notes.")
    sort: str = Field(
        "updated_at_desc",
        description="Sort mode: updated_at_desc|updated_at_asc|created_at_desc|created_at_asc|title_asc|title_desc",
    )


class SearchResponse(NotesListResponse):
    pass


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error message.")
