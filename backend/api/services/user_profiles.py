from enacit4r_auth.services.auth import User
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as AsyncSQLModelSession

from api.models.chat import utc_now
from api.models.user_profile import UserProfile, UserProfileCoordinates


async def get_or_create_user_profile_from_token(
    user: User,
    session: AsyncSQLModelSession,
) -> UserProfile:
    result = await session.exec(
        select(UserProfile).where(UserProfile.keycloak_sub == user.id)
    )
    profile = result.first()
    now = utc_now()

    if profile is None:
        profile = UserProfile(
            keycloak_sub=user.id,
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile

    identity_changed = (
        profile.email != user.email
        or profile.username != user.username
        or profile.first_name != user.first_name
        or profile.last_name != user.last_name
    )

    if not identity_changed:
        return profile

    profile.email = user.email
    profile.username = user.username
    profile.first_name = user.first_name
    profile.last_name = user.last_name
    profile.updated_at = now

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


async def update_profile_center_coordinates(
    profile: UserProfile,
    fields_center_address: str | None,
    fields_center_coordinates: UserProfileCoordinates | None,
) -> None:
    if not fields_center_address:
        profile.center_latitude = None
        profile.center_longitude = None
        return

    if fields_center_coordinates is None:
        profile.center_latitude = None
        profile.center_longitude = None
        return

    profile.center_latitude = fields_center_coordinates.latitude
    profile.center_longitude = fields_center_coordinates.longitude
