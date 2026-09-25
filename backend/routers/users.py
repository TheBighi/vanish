from fastapi import APIRouter, Depends

from ..auth import get_current_user
from ..models import User
from ..schemas import UserOut


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
