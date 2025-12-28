"""Add AI embedding columns to hub_vendor_items

Revision ID: 20251227_0001
Revises: 20251224_0001
Create Date: 2025-12-27
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = '20251227_0001'
down_revision = '20251224_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Add embedding column (1536 dimensions for text-embedding-3-small)
    op.add_column('hub_vendor_items', sa.Column('embedding', Vector(1536), nullable=True))

    # Add timestamp for when embedding was generated
    op.add_column('hub_vendor_items', sa.Column('embedding_generated_at', sa.DateTime(timezone=True), nullable=True))

    # Create index for similarity search (using ivfflat for faster approximate search)
    # Note: ivfflat index requires at least some data to build efficiently
    # We'll create a basic index first, can be recreated with ivfflat later when we have data
    op.execute('CREATE INDEX IF NOT EXISTS ix_hub_vendor_items_embedding ON hub_vendor_items USING hnsw (embedding vector_cosine_ops)')


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_hub_vendor_items_embedding')
    op.drop_column('hub_vendor_items', 'embedding_generated_at')
    op.drop_column('hub_vendor_items', 'embedding')
