"""baseline: eval 自持库 6 表(EvalBase 全量)

Revision ID: 0001
Revises:
Create Date: 2026-06-28

0001 baseline 直接由 ``EvalBase.metadata`` 建全表(ORM 是 schema 权威源,baseline 与 ORM
恒一致,消除手工转写漂移)。表:eval_dataset / eval_corpus_chunk / eval_query / eval_qrel /
eval_run / eval_metric_result。**只建 eval 库的表,绝不碰生产 tolink_rag_db。**

后续字段变更不再走 create_all,而是 autogenerate 出显式 op.alter/add——本 baseline 是冻结起点。
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from linkrag_eval.store.models import EvalBase

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    EvalBase.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    EvalBase.metadata.drop_all(bind=op.get_bind())
