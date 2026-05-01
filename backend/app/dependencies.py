import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import async_sessionmaker
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.session_factory() as session:
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
):
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
        uid = uuid.UUID(user_id)
    except (JWTError, ValueError):
        raise credentials_exc

    from app.models.db import User  # local import breaks circular dependency

    user = await session.get(User, uid)
    if user is None or not user.is_active:
        raise credentials_exc
    return user


def get_llm(request: Request):
    return request.app.state.llm_cheap


def get_agent(request: Request):
    from app.services.agent import TravelAgent
    return TravelAgent(
        llm_cheap=request.app.state.llm_cheap,
        llm_strong=request.app.state.llm_strong,
        embedder=request.app.state.embedder,
        ml_model=request.app.state.ml_model,
         ml_meta=request.app.state.ml_meta,
    )
