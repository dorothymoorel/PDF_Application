from alembic import context
from transloka_core.database import create_sqlite_engine, create_sqlite_url
from transloka_core.storage import resolve_local_data_directories

target_metadata = None


def run_migrations_offline() -> None:
    directories = resolve_local_data_directories()
    context.configure(
        url=create_sqlite_url(directories),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    directories = resolve_local_data_directories()
    engine = create_sqlite_engine(directories)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
