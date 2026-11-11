from alembic import context
from sqlalchemy import engine_from_config, pool
from wellspring.db import Base, DATABASE_URL
from wellspring import models
config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
target_metadata = Base.metadata
if context.is_offline_mode():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction(): context.run_migrations()
else:
    def run(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction(): context.run_migrations()
    supplied = config.attributes.get('connection')
    if supplied is not None:
        run(supplied)
    else:
        engine = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
        with engine.connect() as connection:
            run(connection)
