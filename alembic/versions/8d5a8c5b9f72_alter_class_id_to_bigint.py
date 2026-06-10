"""alter class id to bigint

Revision ID: 8d5a8c5b9f72
Revises: 14881c45e193
Create Date: 2026-06-09 11:29:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "8d5a8c5b9f72"
down_revision = "14881c45e193"
branch_labels = None
depends_on = None


def _class_fk_names(inspector: object) -> list[str]:
    fk_names: list[str] = []
    for fk in inspector.get_foreign_keys("selected_classes"):
        constrained_columns = fk.get("constrained_columns") or []
        if constrained_columns == ["classid"] and fk.get("referred_table") == "classes":
            name = fk.get("name")
            if name:
                fk_names.append(name)
    return fk_names


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    class_id_type = next(
        (column["type"] for column in inspector.get_columns("classes") if column["name"] == "id"),
        None,
    )
    selected_class_id_type = next(
        (
            column["type"]
            for column in inspector.get_columns("selected_classes")
            if column["name"] == "classid"
        ),
        None,
    )
    if isinstance(class_id_type, sa.BigInteger) and isinstance(selected_class_id_type, sa.BigInteger):
        return

    fk_names = _class_fk_names(inspector)
    for fk_name in fk_names:
        op.drop_constraint(fk_name, "selected_classes", type_="foreignkey")

    op.alter_column(
        "classes",
        "id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "selected_classes",
        "classid",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        nullable=False,
    )

    if fk_names:
        for fk_name in fk_names:
            op.create_foreign_key(
                fk_name,
                "selected_classes",
                "classes",
                ["classid"],
                ["id"],
            )
    else:
        refreshed_inspector = inspect(bind)
        has_fk = any(
            (fk.get("constrained_columns") or []) == ["classid"]
            and fk.get("referred_table") == "classes"
            for fk in refreshed_inspector.get_foreign_keys("selected_classes")
        )
        if not has_fk:
            op.create_foreign_key(
                "fk_selected_classes_classid_classes",
                "selected_classes",
                "classes",
                ["classid"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    fk_names = _class_fk_names(inspector)
    for fk_name in fk_names:
        op.drop_constraint(fk_name, "selected_classes", type_="foreignkey")

    op.alter_column(
        "selected_classes",
        "classid",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "classes",
        "id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        nullable=False,
    )

    if fk_names:
        for fk_name in fk_names:
            op.create_foreign_key(
                fk_name,
                "selected_classes",
                "classes",
                ["classid"],
                ["id"],
            )
    else:
        op.create_foreign_key(
            "fk_selected_classes_classid_classes",
            "selected_classes",
            "classes",
            ["classid"],
            ["id"],
        )
