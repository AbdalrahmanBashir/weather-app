from sqlmodel import Session, create_engine, SQLModel
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith(
    "sqlite") else {}
engine = create_engine(DATABASE_URL, echo=True, connect_args=connect_args)


def init_db():
    SQLModel.metadata.create_all(engine)


def get_db_session():
    with Session(engine) as session:
        yield session
