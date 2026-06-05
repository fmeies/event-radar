from typing import Optional

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .auth import decode_access_token
from .database import get_db
from .models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    user_id = decode_access_token(token)
    if not user_id:
        return None
    return db.get(User, user_id)
