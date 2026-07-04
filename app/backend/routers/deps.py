"""JWT auth dependency — used by all protected routes."""
import os
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-prod")
ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> tuple[str, str]:
    """Returns (user_id, workspace_id) or raises 401."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        workspace_id: str | None = payload.get("wid")
        if not user_id or not workspace_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id, workspace_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_workspace(
    workspace_id: str,
    current_user: tuple[str, str] = Depends(get_current_user),
) -> str:
    """Verify the path workspace_id matches the token. Returns workspace_id."""
    _, token_workspace_id = current_user
    if workspace_id != token_workspace_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return workspace_id
