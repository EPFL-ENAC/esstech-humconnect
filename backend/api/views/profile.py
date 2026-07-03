from enacit4r_auth.services.auth import User
from fastapi import APIRouter, Depends, Query
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.auth import require_user
from api.db import get_session
from api.models.user_profile import (
    ListAddressSuggestionsResponse,
    UserProfileEditableFields,
    UserProfileResponse,
)
from api.services.nominatim import search_address_suggestions
from api.services.user_profiles import (
    get_or_create_user_profile_from_token,
    update_profile_center_coordinates,
)

router = APIRouter(prefix="/profile", tags=["Profile"])


@router.get("", response_model=UserProfileResponse)
async def get_profile(
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> UserProfileResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    return UserProfileResponse.from_db_model(profile)


@router.get(
    "/center-address/search",
    response_model=ListAddressSuggestionsResponse,
)
async def search_profile_center_address(
    q: str = Query(min_length=3),
    user: User = Depends(require_user()),
) -> ListAddressSuggestionsResponse:
    suggestions = await search_address_suggestions(q)
    return ListAddressSuggestionsResponse(suggestions=suggestions)


@router.put("", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileEditableFields,
    user: User = Depends(require_user()),
    session: AsyncSQLModelSession = Depends(get_session),
) -> UserProfileResponse:
    profile = await get_or_create_user_profile_from_token(user, session)
    await update_profile_center_coordinates(
        profile,
        payload.center_address,
        payload.center_coordinates,
    )
    profile.update_from_editable_fields(payload)

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return UserProfileResponse.from_db_model(profile)
