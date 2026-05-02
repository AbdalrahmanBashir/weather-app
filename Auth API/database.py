from sqlmodel import Session, create_engine, SQLModel
import os
from sqlalchemy.engine import URL


SERVER = "A3BASHIR"
DATABASE = "Test10DB"

connection_url = URL.create(
    "mssql+pyodbc",
    host=SERVER,
    database=DATABASE,
    query={
        "driver": "ODBC Driver 17 for SQL Server",
        "trusted_connection": "yes",
        "TrustServerCertificate": "yes",
        "Encrypt": "no",
    },
)

DATABASE_URL = os.getenv("DATABASE_URL", str(connection_url))

engine = create_engine(DATABASE_URL, echo=True)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_db_session():
    with Session(engine) as session:
        yield session
