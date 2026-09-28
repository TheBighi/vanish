from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..schemas import EncryptionKeyUpdate, UserOut


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me/encryption-key", response_model=UserOut)
def set_encryption_key(
    payload: EncryptionKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.public_key:
        raise HTTPException(status_code=409, detail="Encryption key is already registered")
    current_user.public_key = payload.public_key
    db.commit()
    db.refresh(current_user)
    return current_user
