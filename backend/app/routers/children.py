import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.auth import get_current_parent
from app.models.parent import Parent
from app.models.child import Child
from app.schemas.children import ChildCreate, ChildUpdate, ChildResponse

router = APIRouter(prefix="/children", tags=["children"])


@router.get("", response_model=list[ChildResponse])
async def list_children(
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Child)
        .where(Child.parent_id == current_parent.id)
        .options(selectinload(Child.gmail_connections))
        .order_by(Child.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=ChildResponse, status_code=status.HTTP_201_CREATED)
async def create_child(
    body: ChildCreate,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child = Child(parent_id=current_parent.id, display_name=body.display_name, birth_year=body.birth_year)
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return child


@router.patch("/{child_id}", response_model=ChildResponse)
async def update_child(
    child_id: str,
    body: ChildUpdate,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child = await _get_owned_child(db, child_id, current_parent.id)
    if body.display_name is not None:
        child.display_name = body.display_name
    if body.birth_year is not None:
        child.birth_year = body.birth_year
    await db.commit()
    await db.refresh(child)
    return child


@router.delete("/{child_id}", status_code=204)
async def delete_child(
    child_id: str,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    child = await _get_owned_child(db, child_id, current_parent.id)
    await db.delete(child)
    await db.commit()


async def _get_owned_child(db: AsyncSession, child_id: str, parent_id: uuid.UUID) -> Child:
    result = await db.execute(
        select(Child).where(Child.id == uuid.UUID(child_id), Child.parent_id == parent_id)
    )
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=404, detail="Child not found")
    return child
