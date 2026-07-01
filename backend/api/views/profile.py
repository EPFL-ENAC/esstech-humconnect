from enacit4r_auth.services.auth import User
from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.auth import require_user
from api.db import get_session
from api.models.user_profile import UserProfileEditableFields, UserProfileResponse
from api.services.user_profiles import get_or_create_user_profile_from_token

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_model=UserProfileResponse)
async def get_profile(
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> UserProfileResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    return UserProfileResponse.from_db_model(profile)


@router.put("", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileEditableFields,
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> UserProfileResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    profile.update_from_editable_fields(payload)

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return UserProfileResponse.from_db_model(profile)
