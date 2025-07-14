import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# 1. Load from `.env` if present
from dotenv import load_dotenv
env_file = os.getenv("ENV_FILE", ".env")
load_dotenv(dotenv_path=env_file, override=True)

# 2. Alembic config
config = context.config

# 3. Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. Import models for autogenerate
from nuance.database.schema import Base
target_metadata = Base.metadata

# 5. Override sqlalchemy.url using env var (if present)
from sqlalchemy.engine.url import make_url
db_url = os.getenv("DATABASE_URL")
if db_url:
    url_obj = make_url(db_url)
    if url_obj.drivername == "sqlite+aiosqlite":
        url_obj = url_obj.set(drivername="sqlite")
    db_url = str(url_obj)
    config.set_main_option("sqlalchemy.url", db_url)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
