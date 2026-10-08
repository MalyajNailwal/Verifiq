"""initial schema: cases, documents, extracted fields, flags, reports, review tasks, llm call logs

Revision ID: 0001
Revises:
Create Date: 2026-10-08
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("jurisdiction", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("doc_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True, index=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("ocr_status", sa.String(length=16), nullable=False),
        sa.Column("ocr_error", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("needs_vision", sa.Boolean(), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=True),
        sa.Column("extraction_method", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_doc_page"),
    )

    op.create_table(
        "extracted_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("field_name", sa.String(length=64), nullable=False, index=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("normalized_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_snippet", sa.Text(), nullable=True),
        sa.Column("extraction_reason", sa.String(length=64), nullable=True),
        sa.Column("edited_by_reviewer", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("severity", sa.String(length=16), nullable=False, index=True),
        sa.Column("flag_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("related_fields", sa.JSON(), nullable=True),
        sa.Column("rule_id", sa.String(length=64), nullable=True),
        sa.Column("rule_confidence", sa.Float(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False, index=True, unique=True),
        sa.Column("risk_rating", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("score_details", sa.JSON(), nullable=True),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("triggers", sa.JSON(), nullable=True),
        sa.Column("assigned_to", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, index=True),
        sa.Column("reviewer_notes", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "llm_call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_name", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("call_type", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_usd", sa.Float(), nullable=True),
        sa.Column("case_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("document_id", sa.String(length=64), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("llm_call_logs")
    op.drop_table("review_tasks")
    op.drop_table("reports")
    op.drop_table("flags")
    op.drop_table("extracted_fields")
    op.drop_table("document_pages")
    op.drop_table("documents")
    op.drop_table("cases")
