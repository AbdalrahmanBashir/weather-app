from pwdlib import PasswordHash
import jwt
from datetime import datetime, timedelta, timezone

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"

# Initialize the hasher first
hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    # Use the instance 'hasher', not the class 'PasswordHash'
    return hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    # Use the instance 'hasher'
    return hasher.verify(password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + \
        (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    # Note: ExpiredSignatureError and InvalidTokenError are subclasses of PyJWTError
    # Usually, you catch PyJWTError last.
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")
    except jwt.PyJWTError:
        return None
