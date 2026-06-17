from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import timedelta, datetime, timezone
from typing import List
from ...config import settings
from ...database import get_db
from ...models.user import User, Team, UserTeam
from ...utils.auth import (
    verify_password, hash_password, create_access_token,
    create_refresh_token, get_current_user, require_role
)
from ...services.audit_service import audit_service
from ...schemas.auth import (
    UserLogin, UserCreate, UserUpdate, Token,
    UserResponse, TeamResponse, TeamCreate,
    LoginResponse, UserListResponse, TeamListResponse
)
from ...utils.logger import logger

router = APIRouter(prefix="/auth", tags=["认证授权"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash if user else ""):
        await audit_service.log_action(
            user_id=None,
            username=request.username,
            module="auth",
            action_type="login",
            action_desc=f"用户登录失败: 用户名或密码错误",
            status="failed",
            severity_level="warning",
            user_ip="unknown",
            error_message="用户名或密码错误",
            db=db,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用，请联系管理员",
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    await audit_service.log_action(
        user_id=str(user.id),
        username=user.username,
        module="auth",
        action_type="login",
        action_desc=f"用户登录成功",
        status="success",
        severity_level="info",
        db=db,
    )

    token = Token(access_token=access_token, refresh_token=refresh_token)
    return LoginResponse(data=token)


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="auth",
        action_type="logout",
        action_desc=f"用户登出",
        status="success",
        db=db,
    )
    return {"code": 200, "message": "登出成功"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserTeam).where(UserTeam.user_id == current_user.id)
    )
    user_teams = result.scalars().all()
    teams_data = []
    for ut in user_teams:
        team_result = await db.execute(select(Team).where(Team.id == ut.team_id))
        team = team_result.scalar_one_or_none()
        if team:
            teams_data.append({
                "id": str(team.id),
                "name": team.name,
                "is_team_leader": ut.is_team_leader,
            })

    user_dict = {
        "id": current_user.id,
        "username": current_user.username,
        "real_name": current_user.real_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "last_login_at": current_user.last_login_at,
        "created_at": current_user.created_at,
        "teams": teams_data,
    }
    return UserResponse(**user_dict)


@router.get("/users", response_model=UserListResponse, dependencies=[Depends(require_role("supervisor"))])
async def list_users(
    page: int = 1,
    page_size: int = 50,
    role: str = None,
    is_active: bool = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)

    from sqlalchemy import func
    count_result = await db.execute(
        select(func.count(User.id)).where(and_(*conditions)) if conditions else select(func.count(User.id))
    )
    total = int(count_result.scalar() or 0)

    query = (
        select(User)
        .where(and_(*conditions) if conditions else True)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    users = list(result.scalars().all())

    return UserListResponse(
        data=[UserResponse.model_validate(u, from_attributes=True) for u in users],
        total=total,
    )


@router.post("/users", response_model=UserResponse, dependencies=[Depends(require_role("supervisor"))])
async def create_user(
    request: UserCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where((User.username == request.username) | (User.email == request.email))
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名或邮箱已存在",
        )

    user = User(
        username=request.username,
        password_hash=hash_password(request.password),
        real_name=request.real_name,
        email=request.email,
        phone=request.phone,
        role=request.role,
    )
    db.add(user)
    await db.flush()

    if request.team_ids:
        for team_id_str in request.team_ids:
            try:
                from uuid import UUID as uuid_type
                team_id = uuid_type(team_id_str)
                db.add(UserTeam(user_id=user.id, team_id=team_id))
            except ValueError:
                pass

    await db.commit()
    await db.refresh(user)

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="auth",
        action_type="create",
        action_desc=f"创建用户: {user.username}",
        target_type="user",
        target_id=str(user.id),
        target_name=user.real_name,
        db=db,
    )

    return user


@router.put("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_role("supervisor"))])
async def update_user(
    user_id: str,
    request: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID as uuid_type
    result = await db.execute(select(User).where(User.id == uuid_type(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_data = request.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if hasattr(user, key):
            setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="auth",
        action_type="update",
        action_desc=f"更新用户信息: {user.username}",
        target_type="user",
        target_id=str(user.id),
        target_name=user.real_name,
        db=db,
    )

    return user


@router.get("/teams", response_model=TeamListResponse)
async def list_teams(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    count_result = await db.execute(select(func.count(Team.id)))
    total = int(count_result.scalar() or 0)

    query = (
        select(Team)
        .order_by(Team.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    teams = list(result.scalars().all())

    return TeamListResponse(
        data=[TeamResponse.model_validate(t, from_attributes=True) for t in teams],
        total=total,
    )


@router.post("/teams", response_model=TeamResponse, dependencies=[Depends(require_role("supervisor"))])
async def create_team(
    request: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from uuid import UUID as uuid_type
    team = Team(
        name=request.name,
        description=request.description,
        parent_team_id=uuid_type(request.parent_team_id) if request.parent_team_id else None,
        leader_id=uuid_type(request.leader_id) if request.leader_id else None,
        notification_emails=request.notification_emails,
    )
    db.add(team)
    await db.commit()
    await db.refresh(team)

    await audit_service.log_action(
        user_id=str(current_user.id),
        username=current_user.username,
        module="auth",
        action_type="create",
        action_desc=f"创建团队: {team.name}",
        target_type="team",
        target_id=str(team.id),
        target_name=team.name,
        db=db,
    )

    return team
