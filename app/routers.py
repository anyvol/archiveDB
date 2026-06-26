# app/routers.py

from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException, status, Query, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional

from app.database import get_session
from app.models import UserRole, User, DEPARTMENTS
from app.schemas import UserCreate, Token, UserAdminUpdate, UserProfileUpdate
from app.schemas import User as UserSchema
from app.auth import create_access_token, get_current_user, get_password_hash, authenticate_user
from app.column_preferences import DEFAULT_VISIBLE_COLUMNS
from app.dependencies import get_current_admin_user
from app.user_helpers import build_full_name

router = APIRouter()


@router.post("/register", response_model=Token)
async def register(
    login: str = Form(..., description="Логин пользователя"),
    password: str = Form(..., description="Пароль пользователя"),
    password_confirm: str = Form(..., description="Подтверждение пароля"),
    full_name: Optional[str] = Form(None, description="Полное имя"),
    last_name: Optional[str] = Form(None, description="Фамилия"),
    first_name: Optional[str] = Form(None, description="Имя"),
    patronymic: Optional[str] = Form(None, description="Отчество"),
    position: Optional[str] = Form(None, description="Должность"),
    department: Optional[str] = Form(None, description="Отдел"),
    session: AsyncSession = Depends(get_session),
):
    if password != password_confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Пароли не совпадают")

    if department not in DEPARTMENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый отдел")

    if last_name and first_name:
        resolved_name = build_full_name(last_name, first_name, patronymic or "")
    else:
        resolved_name = full_name

    result = await session.execute(select(User).where(User.login == login))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Login already registered")

    user = User(
        login=login,
        password_hash=get_password_hash(password),
        full_name=resolved_name,
        position=position,
        department=department,
        role=UserRole.user,
    )
    session.add(user)
    await session.commit()

    access_token = create_access_token({"sub": user.login})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
):
    return await authenticate_user(
        session=session,
        username=form_data.username,
        password=form_data.password,
    )


@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/me/profile", response_model=UserSchema)
async def update_my_profile(
    profile: UserProfileUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if profile.department is not None and profile.department not in DEPARTMENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимый отдел")

    if profile.full_name is not None:
        current_user.full_name = profile.full_name
    if profile.position is not None:
        current_user.position = profile.position
    if profile.department is not None:
        current_user.department = profile.department
    if profile.preferred_org_code is not None:
        current_user.preferred_org_code = profile.preferred_org_code or None
    current_user.preferred_org_okpo = profile.preferred_org_okpo
    if profile.visible_columns is not None:
        current_user.visible_columns = profile.visible_columns or list(DEFAULT_VISIBLE_COLUMNS)

    await session.commit()
    await session.refresh(current_user)
    return current_user


@router.get("/", response_model=List[UserSchema])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    result = await session.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()


@router.put("/{user_id}", response_model=UserSchema)
async def update_user(
    user_id: int,
    user_update: UserAdminUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.login = user_update.login
    user.full_name = user_update.full_name
    user.position = user_update.position
    user.department = user_update.department
    user.role = user_update.role

    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_admin_user),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await session.delete(user)
    await session.commit()
