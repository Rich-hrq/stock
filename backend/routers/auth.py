"""用户注册/登录 API 路由。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_token, get_current_user, hash_password, verify_password
from ..database import get_session
from ..models import User
from ..schemas import TokenResponse, UserCreate, UserLogin, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(req: UserCreate, session: AsyncSession = Depends(get_session)):
    """注册新用户，成功后返回 JWT Token。"""
    username = req.username.strip()
    if len(username) < 3 or len(username) > 20:
        raise HTTPException(status_code=400, detail="用户名长度需在 3-20 个字符之间")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于 6 位")

    # 查重
    existing = await session.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="用户名已存在")

    user = User(username=username, password_hash=hash_password(req.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return TokenResponse(access_token=create_token(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(req: UserLogin, session: AsyncSession = Depends(get_session)):
    """用户登录，验证凭据后返回 JWT Token。"""
    result = await session.execute(select(User).where(User.username == req.username.strip()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return TokenResponse(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
async def get_me(user: User = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return UserOut(id=user.id, username=user.username, created_at=user.created_at)
