import sqlalchemy as sa

from flow_backend.models import RateLimitCounter, UserSetting
from flow_backend.models_collections import CollectionItem
from flow_backend.models_notes import Note


def test_ms_columns_are_bigint() -> None:
    # 回归测试：epoch 毫秒（例如 1772712821891）会溢出 32 位 INTEGER，必须使用 BIGINT。
    assert isinstance(RateLimitCounter.__table__.c.window_start_ms.type, sa.BigInteger)
    assert isinstance(UserSetting.__table__.c.client_updated_at_ms.type, sa.BigInteger)
    assert isinstance(CollectionItem.__table__.c.client_updated_at_ms.type, sa.BigInteger)
    assert isinstance(Note.__table__.c.client_updated_at_ms.type, sa.BigInteger)

    # 不允许 NULL：否则会导致 LWW 逻辑与查询索引出现不一致。
    assert RateLimitCounter.__table__.c.window_start_ms.nullable is False
    assert UserSetting.__table__.c.client_updated_at_ms.nullable is False
    assert CollectionItem.__table__.c.client_updated_at_ms.nullable is False
    assert Note.__table__.c.client_updated_at_ms.nullable is False
