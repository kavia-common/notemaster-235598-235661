from __future__ import annotations

from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import NoteOut, TagOut


def _normalize_tag_name(name: str) -> str:
    return name.strip()


async def fetch_note_tags(session: AsyncSession, note_ids: Sequence[UUID]) -> dict[UUID, list[TagOut]]:
    if not note_ids:
        return {}

    rows = (
        await session.execute(
            text(
                """
                SELECT
                  nt.note_id,
                  t.id,
                  t.name,
                  t.created_at,
                  t.updated_at
                FROM note_tags nt
                JOIN tags t ON t.id = nt.tag_id
                WHERE nt.note_id = ANY(:note_ids)
                ORDER BY t.name ASC
                """
            ),
            {"note_ids": list(note_ids)},
        )
    ).mappings().all()

    out: dict[UUID, list[TagOut]] = {nid: [] for nid in note_ids}
    for r in rows:
        out[r["note_id"]].append(
            TagOut(
                id=r["id"],
                name=r["name"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
        )
    return out


async def fetch_tags_by_names(session: AsyncSession, names: Sequence[str]) -> list[TagOut]:
    if not names:
        return []
    rows = (
        await session.execute(
            text(
                """
                SELECT id, name, created_at, updated_at
                FROM tags
                WHERE lower(name) = ANY(:names)
                ORDER BY name ASC
                """
            ),
            {"names": [n.lower() for n in names]},
        )
    ).mappings().all()
    return [TagOut(**dict(r)) for r in rows]


async def ensure_tags_by_names(session: AsyncSession, names: Sequence[str]) -> list[UUID]:
    """
    Ensure tags exist for each name (idempotent). Returns UUIDs for the ensured tags.

    Uses INSERT ... ON CONFLICT DO NOTHING then selects ids.
    """
    clean = [_normalize_tag_name(n) for n in names if _normalize_tag_name(n)]
    if not clean:
        return []

    # Insert (ignore if exists)
    for name in clean:
        await session.execute(
            text(
                """
                INSERT INTO tags (name)
                VALUES (:name)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": name},
        )

    # Fetch ids
    rows = (
        await session.execute(
            text(
                """
                SELECT id
                FROM tags
                WHERE lower(name) = ANY(:names)
                """
            ),
            {"names": [n.lower() for n in clean]},
        )
    ).mappings().all()
    return [r["id"] for r in rows]


async def replace_note_tags(session: AsyncSession, note_id: UUID, tag_ids: Sequence[UUID]) -> None:
    """
    Replace a note's tag assignments with the provided set.
    """
    await session.execute(text("DELETE FROM note_tags WHERE note_id = :note_id"), {"note_id": note_id})
    for tid in tag_ids:
        await session.execute(
            text(
                """
                INSERT INTO note_tags (note_id, tag_id)
                VALUES (:note_id, :tag_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"note_id": note_id, "tag_id": tid},
        )


async def create_note(
    session: AsyncSession, *, title: str, content: str, tag_ids: Sequence[UUID]
) -> UUID:
    row = (
        await session.execute(
            text(
                """
                INSERT INTO notes (title, content)
                VALUES (:title, :content)
                RETURNING id
                """
            ),
            {"title": title, "content": content},
        )
    ).mappings().one()
    note_id: UUID = row["id"]

    await replace_note_tags(session, note_id, tag_ids)
    return note_id


async def update_note(
    session: AsyncSession, *, note_id: UUID, title: Optional[str], content: Optional[str]
) -> bool:
    """
    Update note fields; returns True if note existed.
    """
    row = (
        await session.execute(
            text(
                """
                UPDATE notes
                SET
                  title = COALESCE(:title, title),
                  content = COALESCE(:content, content)
                WHERE id = :id
                RETURNING id
                """
            ),
            {"id": note_id, "title": title, "content": content},
        )
    ).mappings().first()
    return row is not None


async def delete_note(session: AsyncSession, note_id: UUID) -> bool:
    row = (
        await session.execute(
            text("DELETE FROM notes WHERE id = :id RETURNING id"),
            {"id": note_id},
        )
    ).mappings().first()
    return row is not None


async def get_note(session: AsyncSession, note_id: UUID) -> Optional[NoteOut]:
    row = (
        await session.execute(
            text(
                """
                SELECT id, title, content, created_at, updated_at
                FROM notes
                WHERE id = :id
                """
            ),
            {"id": note_id},
        )
    ).mappings().first()
    if not row:
        return None

    tags_map = await fetch_note_tags(session, [row["id"]])
    return NoteOut(
        id=row["id"],
        title=row["title"],
        content=row["content"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        tags=tags_map.get(row["id"], []),
    )


def _notes_order_by(sort: str) -> str:
    mapping = {
        "updated_at_desc": "n.updated_at DESC",
        "updated_at_asc": "n.updated_at ASC",
        "created_at_desc": "n.created_at DESC",
        "created_at_asc": "n.created_at ASC",
        "title_asc": "n.title ASC",
        "title_desc": "n.title DESC",
    }
    return mapping.get(sort, "n.updated_at DESC")


async def list_notes(
    session: AsyncSession, *, limit: int, offset: int, sort: str, tag_id: Optional[UUID], tag_name: Optional[str]
) -> Tuple[int, List[NoteOut]]:
    """
    List notes with optional tag filter.
    """
    where = []
    params: dict = {"limit": limit, "offset": offset}
    join = ""

    if tag_id:
        join = "JOIN note_tags nt ON nt.note_id = n.id"
        where.append("nt.tag_id = :tag_id")
        params["tag_id"] = tag_id

    if tag_name:
        join = "JOIN note_tags nt ON nt.note_id = n.id JOIN tags t ON t.id = nt.tag_id"
        where.append("lower(t.name) = :tag_name")
        params["tag_name"] = tag_name.lower()

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    total_row = (
        await session.execute(
            text(f"SELECT COUNT(*) AS cnt FROM notes n {join} {where_sql}"),
            params,
        )
    ).mappings().one()
    total = int(total_row["cnt"])

    rows = (
        await session.execute(
            text(
                f"""
                SELECT n.id, n.title, n.content, n.created_at, n.updated_at
                FROM notes n
                {join}
                {where_sql}
                ORDER BY {_notes_order_by(sort)}
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    note_ids = [r["id"] for r in rows]
    tags_map = await fetch_note_tags(session, note_ids)

    items = [
        NoteOut(
            id=r["id"],
            title=r["title"],
            content=r["content"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            tags=tags_map.get(r["id"], []),
        )
        for r in rows
    ]
    return total, items


async def search_notes(
    session: AsyncSession,
    *,
    q: str,
    limit: int,
    offset: int,
    sort: str,
    tag_ids: Sequence[UUID],
    tag_names: Sequence[str],
) -> Tuple[int, List[NoteOut]]:
    """
    Simple search across title/content using ILIKE.
    Optional tag filters (by ids and/or names).
    """
    where = ["(n.title ILIKE :q OR n.content ILIKE :q)"]
    params: dict = {"q": f"%{q}%", "limit": limit, "offset": offset}

    join = ""
    if tag_ids or tag_names:
        join = "JOIN note_tags nt ON nt.note_id = n.id JOIN tags t ON t.id = nt.tag_id"

        if tag_ids:
            where.append("nt.tag_id = ANY(:tag_ids)")
            params["tag_ids"] = list(tag_ids)

        if tag_names:
            where.append("lower(t.name) = ANY(:tag_names)")
            params["tag_names"] = [n.lower() for n in tag_names]

    where_sql = f"WHERE {' AND '.join(where)}"

    # When joining tags, duplicates can appear; use DISTINCT on note id.
    total_row = (
        await session.execute(
            text(
                f"""
                SELECT COUNT(DISTINCT n.id) AS cnt
                FROM notes n
                {join}
                {where_sql}
                """
            ),
            params,
        )
    ).mappings().one()
    total = int(total_row["cnt"])

    rows = (
        await session.execute(
            text(
                f"""
                SELECT DISTINCT n.id, n.title, n.content, n.created_at, n.updated_at
                FROM notes n
                {join}
                {where_sql}
                ORDER BY {_notes_order_by(sort)}
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    note_ids = [r["id"] for r in rows]
    tags_map = await fetch_note_tags(session, note_ids)

    items = [
        NoteOut(
            id=r["id"],
            title=r["title"],
            content=r["content"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            tags=tags_map.get(r["id"], []),
        )
        for r in rows
    ]
    return total, items


async def list_tags(session: AsyncSession, *, limit: int, offset: int, sort: str) -> tuple[int, list[TagOut]]:
    sort_sql = "name ASC" if sort == "name_asc" else "name DESC" if sort == "name_desc" else "updated_at DESC"

    total_row = (await session.execute(text("SELECT COUNT(*) AS cnt FROM tags"))).mappings().one()
    total = int(total_row["cnt"])

    rows = (
        await session.execute(
            text(
                f"""
                SELECT id, name, created_at, updated_at
                FROM tags
                ORDER BY {sort_sql}
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        )
    ).mappings().all()

    return total, [TagOut(**dict(r)) for r in rows]


async def create_tag(session: AsyncSession, name: str) -> UUID:
    try:
        row = (
            await session.execute(
                text(
                    """
                    INSERT INTO tags (name)
                    VALUES (:name)
                    RETURNING id
                    """
                ),
                {"name": _normalize_tag_name(name)},
            )
        ).mappings().one()
        return row["id"]
    except IntegrityError:
        # Unique violation; fall back to selecting existing
        row = (
            await session.execute(
                text("SELECT id FROM tags WHERE lower(name) = :name"),
                {"name": name.strip().lower()},
            )
        ).mappings().one()
        return row["id"]


async def update_tag(session: AsyncSession, tag_id: UUID, name: str) -> bool:
    row = (
        await session.execute(
            text(
                """
                UPDATE tags
                SET name = :name
                WHERE id = :id
                RETURNING id
                """
            ),
            {"id": tag_id, "name": _normalize_tag_name(name)},
        )
    ).mappings().first()
    return row is not None


async def delete_tag(session: AsyncSession, tag_id: UUID) -> bool:
    row = (
        await session.execute(
            text("DELETE FROM tags WHERE id = :id RETURNING id"),
            {"id": tag_id},
        )
    ).mappings().first()
    return row is not None
