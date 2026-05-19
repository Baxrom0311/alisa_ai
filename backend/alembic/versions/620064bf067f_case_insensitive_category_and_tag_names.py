"""case insensitive category and tag names

Revision ID: 620064bf067f
Revises: d18c861a1c3f
Create Date: 2026-05-15 18:52:53.345798

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '620064bf067f'
down_revision = 'd18c861a1c3f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        naming_convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
        with op.batch_alter_table("categories", naming_convention=naming_convention) as batch_op:
            batch_op.drop_constraint("uq_categories_name", type_="unique")
        with op.batch_alter_table("tags", naming_convention=naming_convention) as batch_op:
            batch_op.drop_constraint("uq_tags_name", type_="unique")
    else:
        op.drop_constraint("categories_name_key", "categories", type_="unique")
        op.drop_constraint("tags_name_key", "tags", type_="unique")

    op.create_index(
        "uq_categories_name_lower",
        "categories",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_tags_name_lower",
        "tags",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_tags_name_lower", table_name="tags")
    op.drop_index("uq_categories_name_lower", table_name="categories")

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("categories") as batch_op:
            batch_op.create_unique_constraint("uq_categories_name", ["name"])
        with op.batch_alter_table("tags") as batch_op:
            batch_op.create_unique_constraint("uq_tags_name", ["name"])
    else:
        op.create_unique_constraint("categories_name_key", "categories", ["name"])
        op.create_unique_constraint("tags_name_key", "tags", ["name"])
