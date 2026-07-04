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
    op.add_column("eval_run", sa.Column("run_quality", sa.String(length=16), nullable=True))
    op.add_column("eval_run", sa.Column("failed_samples", sa.Integer(), nullable=True))
    op.add_column("eval_run", sa.Column("failed_sources_json", sa.Text(), nullable=True))
    op.add_column("eval_run", sa.Column("zero_ranked", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("eval_run", "zero_ranked")
    op.drop_column("eval_run", "failed_sources_json")
    op.drop_column("eval_run", "failed_samples")
    op.drop_column("eval_run", "run_quality")
