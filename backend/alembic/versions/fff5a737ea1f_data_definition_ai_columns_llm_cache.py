"""03_데이터정의 compliance: extractions.prompt_version/raw_llm_output, llm_cache, pages.image_path, risk_rules engine/params/default_severity

Revision ID: fff5a737ea1f
Revises: b898f28a4405
Create Date: 2026-10-12 12:00:00.000000

The 7 rules of 03_데이터정의 §6.1 (ai/risk/rules.yaml) are seeded at app start by app/core/seed.py, like the existing
risk_rules defaults.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fff5a737ea1f'
down_revision: Union[str, Sequence[str], None] = 'b898f28a4405'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default backfills existing rows (all produced by the offline rule-based extractor or model@version names)
    op.add_column('extractions', sa.Column('prompt_version', sa.String(length=20), server_default='rule-based-v1', nullable=False))
    op.add_column('extractions', sa.Column('raw_llm_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('pages', sa.Column('image_path', sa.String(length=500), nullable=True))
    op.add_column('risk_rules', sa.Column('engine', sa.String(length=5), nullable=True))
    op.add_column('risk_rules', sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('risk_rules', sa.Column('default_severity', sa.String(length=10), nullable=True))
    op.create_table(
        'llm_cache',
        sa.Column('prompt_hash', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=True),
        sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('prompt_hash'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('llm_cache')
    op.execute("DELETE FROM risk_rules WHERE rule_type = 'doc'")
    op.drop_column('risk_rules', 'default_severity')
    op.drop_column('risk_rules', 'params')
    op.drop_column('risk_rules', 'engine')
    op.drop_column('pages', 'image_path')
    op.drop_column('extractions', 'raw_llm_output')
    op.drop_column('extractions', 'prompt_version')
