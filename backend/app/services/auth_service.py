from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from ..config import settings
from ..models.user import User
from ..schemas.user import UserCreate, UserUpdate
from ..utils.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def create_auth_tokens(user: User) -> dict:
    claims = {"sub": str(user.id), "tv": user.token_version}
    return {
        "access_token": create_access_token(data=claims),
        "refresh_token": create_refresh_token(data=claims),
        "token_type": "bearer",
    }


async def register_user(db: AsyncSession, user_data: UserCreate) -> User:
    normalized_email = user_data.email.lower()

    # Check if user already exists
    result = await db.execute(select(User).where(func.lower(User.email) == normalized_email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    
    # Keep the developer convenience fallback out of production.
    count_result = await db.execute(select(func.count(User.id)))
    user_count = count_result.scalar()
    is_admin = user_count == 0 and settings.ENVIRONMENT.lower() == "development"
    
    # Create new user
    hashed_password = hash_password(user_data.password)
    db_user = User(
        email=normalized_email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        is_admin=is_admin
    )
    db.add(db_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    await db.refresh(db_user)
    return db_user


async def ensure_initial_admin(db: AsyncSession) -> User | None:
    email = settings.INITIAL_ADMIN_EMAIL.strip().lower()
    password = settings.INITIAL_ADMIN_PASSWORD
    if not email or not password:
        return None

    admin_result = await db.execute(select(User.id).where(User.is_admin.is_(True)).limit(1))
    if admin_result.scalar_one_or_none() is not None:
        return None

    user_result = await db.execute(select(User).where(func.lower(User.email) == email))
    user = user_result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name="Initial Admin",
            hashed_password=hash_password(password),
            is_admin=True,
        )
        db.add(user)
    else:
        user.is_admin = True
        user.hashed_password = hash_password(password)
        user.token_version += 1

    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


async def update_user_profile(db: AsyncSession, user: User, user_data: UserUpdate) -> User:
    if user_data.email is not None:
        normalized_email = str(user_data.email).lower()
        if normalized_email != user.email.lower():
            result = await db.execute(
                select(User).where(
                    func.lower(User.email) == normalized_email,
                    User.id != user.id
                )
            )
            if result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered"
                )
            user.email = normalized_email

    if user_data.full_name is not None:
        user.full_name = user_data.full_name
    
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )
    await db.refresh(user)
    return user


async def change_user_password(
    db: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> User:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect current password"
        )

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    await db.commit()
    await db.refresh(user)
    return user


async def revoke_user_tokens(db: AsyncSession, user: User) -> User:
    user.token_version += 1
    await db.commit()
    await db.refresh(user)
    return user


async def refresh_auth_tokens(db: AsyncSession, refresh_token: str) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token"
    )

    payload = decode_access_token(refresh_token)
    if payload is None or payload.get("typ") != "refresh":
        raise credentials_exception

    try:
        user_id = int(payload.get("sub"))
        token_version = int(payload.get("tv"))
    except (TypeError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or user.token_version != token_version:
        raise credentials_exception

    return create_auth_tokens(user)
