"""add eval_run quality summary columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 0001 从当前 ORM 建表时这些字段已经存在；已有库仍须严格匹配当前定义。
    connection = op.get_bind()
    existing = {column["name"]: column for column in sa.inspect(connection).get_columns("eval_run")}
    expected = [
        sa.Column("run_quality", sa.String(length=16), nullable=True),
        sa.Column("failed_samples", sa.Integer(), nullable=True),
        sa.Column("failed_sources_json", sa.Text(), nullable=True),
        sa.Column("zero_ranked", sa.Integer(), nullable=True),
    ]
    for column in expected:
        present = existing.get(column.name)
        if present is not None and (
            present["type"].compile(dialect=connection.dialect)
            != column.type.compile(dialect=connection.dialect)
            or present["nullable"] != column.nullable
        ):
            raise ValueError(f"eval_run.{column.name} 与迁移要求的类型或可空性不一致")
    for column in expected:
        if column.name not in existing:
            op.add_column("eval_run", column)


def downgrade() -> None:
    op.drop_column("eval_run", "zero_ranked")
    op.drop_column("eval_run", "failed_sources_json")
    op.drop_column("eval_run", "failed_samples")
    op.drop_column("eval_run", "run_quality")
