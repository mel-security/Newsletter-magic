"""Initial schema.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # raw_items
    op.create_table(
        "raw_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw", JSONB(), nullable=True),
        sa.Column("status", sa.String(32), server_default="new"),
    )
    op.create_index("ix_raw_items_url", "raw_items", ["url"])

    # stories
    op.create_table(
        "stories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
    )

    # articles
    op.create_table(
        "articles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(10), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("score", sa.Float(), server_default="0"),
        sa.Column("story_id", UUID(as_uuid=True), sa.ForeignKey("stories.id"), nullable=True),
    )
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])

    # iocs
    op.create_table(
        "iocs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confidence", sa.String(16), server_default="medium"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("story_id", UUID(as_uuid=True), sa.ForeignKey("stories.id"), nullable=True),
        sa.Column("sources", ARRAY(sa.String()), nullable=True),
    )
    op.create_index("ix_iocs_value", "iocs", ["value"])

    # vulns
    op.create_table(
        "vulns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cve", sa.String(32), nullable=False),
        sa.Column("vendor", sa.String(255), nullable=True),
        sa.Column("product", sa.String(255), nullable=True),
        sa.Column("severity", sa.String(32), nullable=True),
        sa.Column("exploited_bool", sa.Boolean(), server_default="false"),
        sa.Column("references", ARRAY(sa.String()), nullable=True),
        sa.Column("story_id", UUID(as_uuid=True), sa.ForeignKey("stories.id"), nullable=True),
    )
    op.create_index("ix_vulns_cve", "vulns", ["cve"])

    # runs
    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), server_default="running"),
        sa.Column("stats_json", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("runs")
    op.drop_table("vulns")
    op.drop_table("iocs")
    op.drop_table("articles")
    op.drop_table("stories")
    op.drop_table("raw_items")
