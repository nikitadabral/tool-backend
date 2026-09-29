import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.enums import Role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services import auth as auth_service

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_EXC
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise _CREDENTIALS_EXC

    user = auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    return user


def require_role(*roles: Role):
    """Build a dependency that allows only the given roles."""
    allowed = {role.value for role in roles}

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return checker


require_user = require_role(Role.USER)
require_reviewer = require_role(Role.REVIEWER)
