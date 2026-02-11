from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from flow_backend.v2.schemas.collections import (
    CollectionItem,
    CollectionItemCreateRequest,
    CollectionItemPatchRequest,
)


def test_create_folder_requires_name_non_empty():
    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="folder", name=None)

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="folder", name="")

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="folder", name="   ")

    m = CollectionItemCreateRequest(item_type="folder", name="inbox")
    assert m.name == "inbox"


def test_create_folder_forbids_ref_fields():
    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="folder", name="x", ref_type="flow_note", ref_id="n1")

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="folder", name="x", ref_type=None, ref_id="n1")

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="folder", name="x", ref_type="flow_note", ref_id=None)


def test_create_note_ref_requires_ref_fields_name_optional():
    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="note_ref", ref_type=None, ref_id=None)

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="note_ref", ref_type="flow_note", ref_id=None)

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="note_ref", ref_type=None, ref_id="n1")

    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="note_ref", ref_type="flow_note", ref_id="")

    m1 = CollectionItemCreateRequest(
        item_type="note_ref", ref_type="flow_note", ref_id="n1", name=None
    )
    assert m1.name is None

    m2 = CollectionItemCreateRequest(
        item_type="note_ref", ref_type="memos_memo", ref_id="m1", name=""
    )
    assert m2.name == ""


def test_create_note_ref_ref_type_is_literal():
    with pytest.raises(ValidationError):
        CollectionItemCreateRequest(item_type="note_ref", ref_type=cast(Any, "unknown"), ref_id="x")


def test_item_semantics_match_create_rules():
    now = datetime.now()

    with pytest.raises(ValidationError):
        CollectionItem(
            id="c1",
            item_type="folder",
            parent_id=None,
            name="",
            color=None,
            ref_type=None,
            ref_id=None,
            sort_order=0,
            client_updated_at_ms=0,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    with pytest.raises(ValidationError):
        CollectionItem(
            id="c2",
            item_type="folder",
            parent_id=None,
            name="inbox",
            color=None,
            ref_type="flow_note",
            ref_id="n1",
            sort_order=0,
            client_updated_at_ms=0,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    with pytest.raises(ValidationError):
        CollectionItem(
            id="c3",
            item_type="note_ref",
            parent_id=None,
            name="",
            color=None,
            ref_type=None,
            ref_id=None,
            sort_order=0,
            client_updated_at_ms=0,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )

    ok = CollectionItem(
        id="c4",
        item_type="note_ref",
        parent_id=None,
        name="",
        color=None,
        ref_type="flow_note",
        ref_id="n1",
        sort_order=0,
        client_updated_at_ms=0,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    assert ok.ref_type == "flow_note"


def test_patch_requires_non_negative_timestamp():
    with pytest.raises(ValidationError):
        CollectionItemPatchRequest(client_updated_at_ms=-1, name="x")


def test_patch_requires_any_field_change_besides_timestamp():
    with pytest.raises(ValidationError):
        CollectionItemPatchRequest(client_updated_at_ms=0)


def test_patch_treats_explicit_null_as_a_change():
    m = CollectionItemPatchRequest(client_updated_at_ms=0, parent_id=None)
    assert m.parent_id is None


def test_patch_ref_fields_must_be_paired_when_present():
    with pytest.raises(ValidationError):
        CollectionItemPatchRequest(client_updated_at_ms=0, ref_type="flow_note")

    with pytest.raises(ValidationError):
        CollectionItemPatchRequest(client_updated_at_ms=0, ref_id="n1")

    ok_clear = CollectionItemPatchRequest(client_updated_at_ms=0, ref_type=None, ref_id=None)
    assert ok_clear.ref_type is None and ok_clear.ref_id is None

    with pytest.raises(ValidationError):
        CollectionItemPatchRequest(client_updated_at_ms=0, ref_type=None, ref_id="n1")

    with pytest.raises(ValidationError):
        CollectionItemPatchRequest(client_updated_at_ms=0, ref_type="flow_note", ref_id="")

    ok_set = CollectionItemPatchRequest(client_updated_at_ms=0, ref_type="memos_memo", ref_id="m1")
    assert ok_set.ref_type == "memos_memo" and ok_set.ref_id == "m1"
