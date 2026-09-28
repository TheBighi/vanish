from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import create_access_token, hash_password, verify_password
from ..database import get_db
from ..models import User
from ..schemas import TokenOut, UserCreate, UserLogin


router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    username = payload.username.strip()
    existing = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="Username is already taken")
    user = User(username=username, password_hash=hash_password(payload.password), public_key=payload.public_key)
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id), user=user)


@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.username) == payload.username.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return TokenOut(access_token=create_access_token(user.id), user=user)
