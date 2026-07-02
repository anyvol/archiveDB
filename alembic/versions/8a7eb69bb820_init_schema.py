"""init schema with document status workflow

Revision ID: 8a7eb69bb820
Revises:
Create Date: 2025-11-11 23:56:30.002432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM


revision: str = "8a7eb69bb820"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOCUMENT_STATUS_VALUES = ("pending_review", "verified", "requires_correction")
USER_ROLE_VALUES = ("admin", "user", "reviewer")

document_status = ENUM(*DOCUMENT_STATUS_VALUES, name="documentstatus")
document_status_no_create = ENUM(*DOCUMENT_STATUS_VALUES, name="documentstatus", create_type=False)
user_role = ENUM(*USER_ROLE_VALUES, name="userrole")
user_role_no_create = ENUM(*USER_ROLE_VALUES, name="userrole", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    user_role.create(bind, checkfirst=True)
    document_status.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("position", sa.String(), nullable=True),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("role", user_role_no_create, nullable=False, server_default="user"),
        sa.Column("email", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_login", "users", ["login"], unique=True)

    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=8), nullable=True),
        sa.Column("name", sa.String(length=255)),
        sa.Column("code_okpo", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("num_code", sa.Integer(), nullable=True),
        sa.Column("num_code_okpo", sa.Integer(), nullable=True),
    )

    op.create_table(
        "class_codes_kd",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
    )
    op.create_index("ix_class_codes_kd_code", "class_codes_kd", ["code"], unique=True)

    op.create_table(
        "class_codes_td",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=7), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
    )
    op.create_index("ix_class_codes_td_code", "class_codes_td", ["code"], unique=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("file_path", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_update", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("developed_by", sa.String(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("position", sa.String(), nullable=True),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("doc_name", sa.String(), nullable=True),
        sa.Column(
            "status",
            document_status_no_create,
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.create_index("ix_documents_id", "documents", ["id"])
    op.create_index("ix_documents_file_name", "documents", ["file_name"], unique=True)

    op.create_table(
        "design_documents",
        sa.Column("id", sa.Integer(), sa.ForeignKey("documents.id"), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("kd_class_code_id", sa.Integer(), sa.ForeignKey("class_codes_kd.id"), nullable=False),
        sa.Column("prni", sa.Integer(), nullable=False),
        sa.Column("designation", sa.String(), nullable=False),
        sa.Column("org_code_str", sa.String(length=8)),
        sa.Column("class_code_str", sa.String(length=6)),
        sa.Column("doc_kind_code", sa.String(length=3), nullable=True),
    )
    op.create_index("ix_design_documents_designation", "design_documents", ["designation"], unique=True)

    op.create_table(
        "tech_documents",
        sa.Column("id", sa.Integer(), sa.ForeignKey("documents.id"), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("td_class_code_id", sa.Integer(), sa.ForeignKey("class_codes_td.id"), nullable=False),
        sa.Column("prn", sa.Integer(), nullable=False),
        sa.Column("designation", sa.String(), nullable=False),
        sa.Column("org_code_str", sa.String(length=8)),
        sa.Column("class_code_str", sa.String(length=7)),
    )
    op.create_index("ix_tech_documents_designation", "tech_documents", ["designation"], unique=True)


def downgrade() -> None:
    op.drop_table("tech_documents")
    op.drop_table("design_documents")
    op.drop_table("documents")
    op.drop_table("class_codes_td")
    op.drop_table("class_codes_kd")
    op.drop_table("organizations")
    op.drop_table("users")
    bind = op.get_bind()
    document_status.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
