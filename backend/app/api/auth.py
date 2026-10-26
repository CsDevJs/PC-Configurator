from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_schemas import Credentials, TokenRead, UserRead
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.security import create_access_token, hash_password, read_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["Accounts"])
DbSession = Annotated[Session, Depends(get_db)]
_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    db: DbSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> User:
    """Resolve the bearer token to a user; any problem is the same generic 401."""
    if credentials is None:
        raise _UNAUTHORIZED
    user_id = read_access_token(credentials.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise _UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED,
             responses={409: {"description": "Email already registered"}})
def register(payload: Credentials, db: DbSession) -> User:
    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from None
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenRead, responses={401: {"description": "Wrong email or password"}})
def login(payload: Credentials, db: DbSession) -> TokenRead:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    # Same message for unknown email and wrong password, so accounts can't be probed.
    if not verify_password(user.password_hash if user else None, payload.password):
        raise HTTPException(status_code=401, detail="Wrong email or password")
    return TokenRead(access_token=create_access_token(user.id), expires_in=settings.access_token_minutes * 60)


@router.get("/me", response_model=UserRead, responses={401: {"description": "Not authenticated"}})
def me(user: CurrentUser) -> User:
    return user
