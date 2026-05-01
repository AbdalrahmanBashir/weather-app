from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from typing import Annotated

from database import init_db, get_db_session
from models import User
from schemas import UserCreate, UserLogin, TokenResponse, UserResponse, TokenData
from security import hash_password, verify_password, create_access_token

app = FastAPI()


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db: Annotated[Session, Depends(get_db_session)]):
    existing_user = db.exec(select(User).where(
        User.email == user.email)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    hashed_pw = hash_password(user.password)
    new_user = User(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        hashed_password=hashed_pw
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/login", response_model=TokenResponse)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[Session, Depends(get_db_session)]):
    user = db.exec(select(User).where(
        User.email == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/")
async def root():
    return {"message": "Hello, World!"}
