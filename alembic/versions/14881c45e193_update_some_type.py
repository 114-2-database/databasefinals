"""update some type

Revision ID: 14881c45e193
Revises: 149c6810ac16
Create Date: 2026-06-09 11:14:55.264711

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '14881c45e193'
down_revision = '149c6810ac16'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("departments")}

    if "humanities_min" not in column_names:
        op.add_column(
            "departments",
            sa.Column("humanities_min", sa.Integer(), nullable=True),
        )
        if "humanities" in column_names:
            op.execute("UPDATE departments SET humanities_min = humanities")
        op.execute("UPDATE departments SET humanities_min = 0 WHERE humanities_min IS NULL")
        op.alter_column(
            "departments",
            "humanities_min",
            existing_type=sa.Integer(),
            nullable=False,
        )

    if "humanities_max" not in column_names:
        op.add_column(
            "departments",
            sa.Column("humanities_max", sa.Integer(), nullable=True),
        )

    op.alter_column(
        "departments",
        "social_max",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "departments",
        "sciences_max",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "departments",
        "residential_max",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "departments",
        "chinese_max",
        existing_type=sa.INTEGER(),
        nullable=True,
    )

    if "humanities" in column_names:
        op.drop_column("departments", "humanities")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    column_names = {column["name"] for column in inspector.get_columns("departments")}

    if "humanities" not in column_names:
        op.add_column(
            "departments",
            sa.Column("humanities", sa.INTEGER(), autoincrement=False, nullable=True),
        )
        if "humanities_min" in column_names:
            op.execute("UPDATE departments SET humanities = humanities_min")
        op.execute("UPDATE departments SET humanities = 0 WHERE humanities IS NULL")
        op.alter_column(
            "departments",
            "humanities",
            existing_type=sa.INTEGER(),
            nullable=False,
        )

    op.alter_column(
        "departments",
        "chinese_max",
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    op.alter_column(
        "departments",
        "residential_max",
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    op.alter_column(
        "departments",
        "sciences_max",
        existing_type=sa.INTEGER(),
        nullable=False,
    )
    op.alter_column(
        "departments",
        "social_max",
        existing_type=sa.INTEGER(),
        nullable=False,
    )

    if "humanities_max" in column_names:
        op.drop_column("departments", "humanities_max")
    if "humanities_min" in column_names:
        op.drop_column("departments", "humanities_min")
