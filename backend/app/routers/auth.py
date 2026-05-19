from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..schemas.user import (
    PasswordChange,
    RefreshTokenRequest,
    Token,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from ..services.auth_service import (
    authenticate_user,
    change_user_password,
    create_auth_tokens,
    refresh_auth_tokens,
    register_user,
    revoke_user_tokens,
    update_user_profile,
)
from ..middleware.auth import get_current_user
from ..middleware.rate_limit import limiter, login_email_or_remote_address
from ..models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
async def register(request: Request, user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    return await register_user(db, user_data)


@router.post("/login", response_model=Token)
@limiter.limit("20/hour", key_func=login_email_or_remote_address)
@limiter.limit("5/minute", key_func=login_email_or_remote_address)
async def login(request: Request, user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, user_data.email, user_data.password)
    return create_auth_tokens(user)


@router.post("/refresh", response_model=Token)
async def refresh_token(token_data: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    return await refresh_auth_tokens(db, token_data.refresh_token)


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await revoke_user_tokens(db, current_user)
    return {"message": "Successfully logged out."}


@router.post("/password", response_model=UserResponse)
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await change_user_password(
        db,
        current_user,
        password_data.current_password,
        password_data.new_password,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    return await update_user_profile(db, current_user, user_data)
