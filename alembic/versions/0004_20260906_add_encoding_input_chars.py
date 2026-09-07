"""record successful encoder input lengths on corpus rows

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 使用当前 metadata，空库可能已有新列；旧行的未知长度始终保留 NULL。
    connection = op.get_bind()
    existing = {
        column["name"]: column
        for column in sa.inspect(connection).get_columns("eval_corpus_chunk")
    }
    expected = [
        sa.Column("dense_input_chars", sa.Integer(), nullable=True),
        sa.Column("sparse_input_chars", sa.Integer(), nullable=True),
    ]
    for column in expected:
        present = existing.get(column.name)
        if present is not None and (
            present["type"].compile(dialect=connection.dialect)
            != column.type.compile(dialect=connection.dialect)
            or present["nullable"] != column.nullable
            or present.get("default") is not None
        ):
            raise ValueError(f"eval_corpus_chunk.{column.name} 与迁移要求的类型、可空性或默认值不一致")
    for column in expected:
        if column.name not in existing:
            op.add_column("eval_corpus_chunk", column)


def downgrade() -> None:
    op.drop_column("eval_corpus_chunk", "sparse_input_chars")
    op.drop_column("eval_corpus_chunk", "dense_input_chars")
