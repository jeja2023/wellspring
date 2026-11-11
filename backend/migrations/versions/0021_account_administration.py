"""Role authorization, organization hierarchy and versioned account management."""
import json
from alembic import op
import sqlalchemy as sa
revision="0021"
down_revision="0020"
branch_labels=None
depends_on=None
startup_safe=True


def upgrade():
    op.create_table("roles",sa.Column("id",sa.String(36),primary_key=True),sa.Column("code",sa.String(80),nullable=False,unique=True),
        sa.Column("name",sa.String(120),nullable=False),sa.Column("kind",sa.String(20),nullable=False),sa.Column("description",sa.Text(),nullable=False),
        sa.Column("permissions_json",sa.Text(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False),sa.Column("version",sa.Integer(),nullable=False))
    permissions=[f"{resource}.{action}" for resource in ("intake","cases","evidence","intelligence","persons","wastewater") for action in ("read","write")]
    permissions += ["intake.import","intake.export","intake.hide","cases.import","audit.read"]
    table=sa.table("roles",sa.column("id",sa.String),sa.column("code",sa.String),sa.column("name",sa.String),sa.column("kind",sa.String),sa.column("description",sa.Text),sa.column("permissions_json",sa.Text),sa.column("active",sa.Boolean),sa.column("version",sa.Integer))
    op.bulk_insert(table,[dict(id="wellspring-business-user",code="business_user",name="业务用户",kind="USER",description="保留既有开发业务范围；正式岗位需另配",permissions_json=json.dumps(permissions),active=True,version=1)])
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("parent_id",sa.String(36),nullable=True))
        batch.add_column(sa.Column("active",sa.Boolean(),server_default=sa.true(),nullable=False))
        batch.add_column(sa.Column("version",sa.Integer(),server_default="1",nullable=False))
        batch.create_foreign_key("fk_organization_parent","organizations",["parent_id"],["id"])
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role_id",sa.String(36),nullable=True))
        batch.add_column(sa.Column("version",sa.Integer(),server_default="1",nullable=False))
        batch.create_foreign_key("fk_user_role","roles",["role_id"],["id"])
    op.execute(sa.text("UPDATE users SET role_id='wellspring-business-user' WHERE is_admin=false"))
    op.create_table("administration_lock",sa.Column("id",sa.String(36),primary_key=True),sa.Column("version",sa.Integer(),nullable=False))
    op.bulk_insert(sa.table("administration_lock",sa.column("id",sa.String),sa.column("version",sa.Integer)),[{"id":"accounts","version":1}])


def downgrade():
    op.drop_table("administration_lock")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_user_role",type_="foreignkey");batch.drop_column("role_id");batch.drop_column("version")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_constraint("fk_organization_parent",type_="foreignkey");batch.drop_column("parent_id");batch.drop_column("active");batch.drop_column("version")
    op.drop_table("roles")
