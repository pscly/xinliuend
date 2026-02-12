from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException

from flow_backend.config import settings
from flow_backend.db import reset_engine_cache, session_scope
from flow_backend.models import User
from flow_backend.services import collections_service
from flow_backend.v2.schemas.collections import (
    CollectionItemCreateRequest,
    CollectionItemMoveItem,
    CollectionItemPatchRequest,
)


def _alembic_upgrade_head() -> None:
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")


async def _create_user(*, username: str) -> int:
    async with session_scope() as session:
        user = User(
            username=username,
            password_hash="x",
            memos_id=None,
            memos_token=f"tok-{username}",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.id is not None
        return int(user.id)


@pytest.mark.anyio
async def test_collections_service_create_conflict_and_patch_validation_and_conflict(
    tmp_path: Path,
) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-collections-service-patch.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        user_id = await _create_user(username="u_col_svc_1")
        folder_id = "00000000-0000-0000-0000-000000000101"

        async with session_scope() as session:
            item = await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=folder_id,
                    item_type="folder",
                    parent_id=None,
                    name="F1",
                    sort_order=1,
                    client_updated_at_ms=1000,
                ),
            )
            assert item.id == folder_id

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc:
                await collections_service.create_collection_item(
                    session,
                    user_id=user_id,
                    payload=CollectionItemCreateRequest(
                        id=folder_id,
                        item_type="folder",
                        parent_id=None,
                        name="F1",
                        sort_order=1,
                        client_updated_at_ms=1100,
                    ),
                )
            assert exc.value.status_code == 409

        async with session_scope() as session:
            out = await collections_service.patch_collection_item(
                session,
                user_id=user_id,
                item_id=folder_id,
                payload=CollectionItemPatchRequest(
                    name="F1-renamed",
                    client_updated_at_ms=2000,
                ),
            )
            assert out.name == "F1-renamed"

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc2:
                await collections_service.patch_collection_item(
                    session,
                    user_id=user_id,
                    item_id=folder_id,
                    payload=CollectionItemPatchRequest(
                        name=None,
                        client_updated_at_ms=2100,
                    ),
                )
            assert exc2.value.status_code == 400
            assert exc2.value.detail == "name cannot be null"

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc3:
                await collections_service.patch_collection_item(
                    session,
                    user_id=user_id,
                    item_id=folder_id,
                    payload=CollectionItemPatchRequest(
                        ref_type="flow_note",
                        ref_id="note-1",
                        client_updated_at_ms=2200,
                    ),
                )
            assert exc3.value.status_code == 400
            assert exc3.value.detail == "ref_type/ref_id can only be patched for note_ref"

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc4:
                await collections_service.patch_collection_item(
                    session,
                    user_id=user_id,
                    item_id=folder_id,
                    payload=CollectionItemPatchRequest(
                        name="stale",
                        client_updated_at_ms=1999,
                    ),
                )
            assert exc4.value.status_code == 409
            detail = cast(dict[str, object], exc4.value.detail)
            assert cast(str, detail.get("message")) == "conflict"
            details = cast(dict[str, object], detail.get("details"))
            assert "server_snapshot" in details
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_collections_service_delete_note_ref_and_folder_recursive(tmp_path: Path) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-collections-service-delete.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        user_id = await _create_user(username="u_col_svc_2")

        root_id = "00000000-0000-0000-0000-000000000201"
        child_folder_id = "00000000-0000-0000-0000-000000000202"
        child_ref_id = "00000000-0000-0000-0000-000000000203"

        async with session_scope() as session:
            await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=root_id,
                    item_type="folder",
                    parent_id=None,
                    name="root",
                    sort_order=1,
                    client_updated_at_ms=1000,
                ),
            )
            await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=child_folder_id,
                    item_type="folder",
                    parent_id=root_id,
                    name="child",
                    sort_order=1,
                    client_updated_at_ms=1100,
                ),
            )
            await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=child_ref_id,
                    item_type="note_ref",
                    parent_id=child_folder_id,
                    ref_type="flow_note",
                    ref_id="note-1",
                    sort_order=1,
                    client_updated_at_ms=1200,
                ),
            )

        async with session_scope() as session:
            await collections_service.delete_collection_item(
                session,
                user_id=user_id,
                item_id=child_ref_id,
                client_updated_at_ms=1300,
            )

        async with session_scope() as session:
            await collections_service.delete_collection_item(
                session,
                user_id=user_id,
                item_id=root_id,
                client_updated_at_ms=2000,
            )
    finally:
        settings.database_url = old_db


@pytest.mark.anyio
async def test_collections_service_move_duplicate_ids_and_cycle_and_parent_validation(
    tmp_path: Path,
) -> None:
    old_db = settings.database_url
    try:
        settings.database_url = f"sqlite:///{tmp_path / 'test-collections-service-move.db'}"
        reset_engine_cache()
        _alembic_upgrade_head()

        user_id = await _create_user(username="u_col_svc_3")

        a_id = "00000000-0000-0000-0000-000000000301"
        b_id = "00000000-0000-0000-0000-000000000302"
        ref_parent_id = "00000000-0000-0000-0000-000000000303"

        async with session_scope() as session:
            await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=a_id,
                    item_type="folder",
                    parent_id=None,
                    name="A",
                    sort_order=1,
                    client_updated_at_ms=1000,
                ),
            )
            await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=b_id,
                    item_type="folder",
                    parent_id=a_id,
                    name="B",
                    sort_order=1,
                    client_updated_at_ms=1100,
                ),
            )
            await collections_service.create_collection_item(
                session,
                user_id=user_id,
                payload=CollectionItemCreateRequest(
                    id=ref_parent_id,
                    item_type="note_ref",
                    parent_id=None,
                    ref_type="flow_note",
                    ref_id="note-x",
                    sort_order=1,
                    client_updated_at_ms=1200,
                ),
            )

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc:
                await collections_service.move_collection_items(
                    session,
                    user_id=user_id,
                    items=[
                        CollectionItemMoveItem(
                            id=a_id,
                            parent_id=None,
                            sort_order=1,
                            client_updated_at_ms=2000,
                        ),
                        CollectionItemMoveItem(
                            id=a_id,
                            parent_id=None,
                            sort_order=2,
                            client_updated_at_ms=2001,
                        ),
                    ],
                )
            assert exc.value.status_code == 400
            assert exc.value.detail == "duplicate item ids in request"

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc2:
                await collections_service.move_collection_items(
                    session,
                    user_id=user_id,
                    items=[
                        CollectionItemMoveItem(
                            id=a_id,
                            parent_id=b_id,
                            sort_order=1,
                            client_updated_at_ms=3000,
                        )
                    ],
                )
            assert exc2.value.status_code == 400

        async with session_scope() as session:
            with pytest.raises(HTTPException) as exc3:
                await collections_service.move_collection_items(
                    session,
                    user_id=user_id,
                    items=[
                        CollectionItemMoveItem(
                            id=b_id,
                            parent_id=ref_parent_id,
                            sort_order=1,
                            client_updated_at_ms=3100,
                        )
                    ],
                )
            assert exc3.value.status_code == 400
            assert exc3.value.detail == "parent must be an active folder"
    finally:
        settings.database_url = old_db
