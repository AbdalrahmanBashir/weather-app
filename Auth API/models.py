from sqlmodel import SQLModel, Field
from pydantic import EmailStr
import uuid
from uuid import UUID


class User(SQLModel, table=True):
    """User model for authentication

    """

    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid.uuid4,
                     primary_key=True, nullable=False)
    email: EmailStr = Field(unique=True, max_length=255,
                            index=True, nullable=False)
    first_name: str
    last_name: str
    hashed_password: str
