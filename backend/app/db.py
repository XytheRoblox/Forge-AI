from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///./data.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def _add_missing_columns() -> None:
    """Add columns that exist on the models but not yet in the database.

    `create_all` only ever CREATEs — it silently leaves an existing table
    alone, so adding a field to a model breaks every query against an
    already-populated database with "no such column" and a 500. There's no
    migration tool here, and dropping the file would throw away people's
    agents, so bridge the gap directly.

    Deliberately narrow: it only ADDs columns, and never drops, renames, or
    retypes anything. Those need a real migration and a human decision."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all will handle it
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                type_sql = column.type.compile(dialect=engine.dialect)
                # SQLite requires a constant default when adding a column to a
                # table that already has rows. JSON columns get an empty
                # container rather than NULL so existing agents deserialize.
                default = "'{}'" if type_sql.upper() == "JSON" else "NULL"
                connection.execute(
                    text(
                        f'ALTER TABLE "{table.name}" '
                        f'ADD COLUMN "{column.name}" {type_sql} DEFAULT {default}'
                    )
                )
                print(f"[db] added {table.name}.{column.name}")


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def get_session():
    with Session(engine) as session:
        yield session
