from fastapi import APIRouter, Depends, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    UserProfile,
)
from app.services import auth_service
from app.utils import error_response, success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    # 1a. Check if this is an admin employee-ID login (no external API)
    admin_profile = await auth_service.verify_admin_credentials(body.username, body.password)
    if admin_profile:
        user_doc = await auth_service.upsert_admin(db, admin_profile)
        user_id = str(user_doc["_id"])
        role = "admin"
    else:
        # 1b. Verify student credentials against PESUAuth
        try:
            profile = await auth_service.verify_pesu_credentials(body.username, body.password)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )

        if not profile:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # 2. Upsert user in MongoDB
        user_doc = await auth_service.upsert_user(db, profile)
        user_id = str(user_doc["_id"])
        role = user_doc.get("role", "student")

    # 3. Generate tokens
    access_token = auth_service.create_access_token(user_id, role)
    refresh_token = auth_service.create_refresh_token(user_id)

    # 4. Persist session (hashed refresh token)
    ip = request.client.host if request.client else None
    await auth_service.create_session(db, user_id, refresh_token, ip)

    user_out = UserProfile(
        id=user_id,
        srn=user_doc["srn"],
        email=user_doc.get("email", ""),
        name=user_doc.get("name", ""),
        program=user_doc.get("program"),
        branch=user_doc.get("branch"),
        campus=user_doc.get("campus"),
        role=role,
    )

    return success_response(
        data=LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_out,
        ).model_dump(),
        message="Login successful",
    )


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    session = await auth_service.validate_refresh_token(db, body.refresh_token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = str(session["user_id"])
    user_doc = await db["users"].find_one({"_id": session["user_id"]})
    if not user_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    new_access_token = auth_service.create_access_token(user_id, user_doc.get("role", "student"))

    return success_response(
        data=AccessTokenResponse(access_token=new_access_token).model_dump(),
        message="Token refreshed",
    )


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await auth_service.delete_session(db, body.refresh_token)
    return success_response(data=None, message="Logged out successfully")


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    user_out = UserProfile(
        id=str(current_user["_id"]),
        srn=current_user["srn"],
        email=current_user.get("email", ""),
        name=current_user.get("name", ""),
        program=current_user.get("program"),
        branch=current_user.get("branch"),
        campus=current_user.get("campus"),
        role=current_user.get("role", "student"),
    )
    return success_response(data=user_out.model_dump(), message="User profile fetched")
