from enacit4r_auth.services.auth import KeycloakService, User

from api.config import config

ADMIN_ROLE = "humconnect-admin"
# USER_ROLE = "humconnect-user"

kc_service = KeycloakService(
    config.KEYCLOAK_URL,
    config.KEYCLOAK_REALM,
    config.KEYCLOAK_API_ID,
    config.KEYCLOAK_API_SECRET,
    ADMIN_ROLE,
)


def is_admin(user: User) -> bool:
    return ADMIN_ROLE in user.realm_roles


def get_current_user():
    return kc_service.get_user_info()


def require_user():
    return kc_service.get_user_info()


def require_admin():
    return kc_service.require_admin()
