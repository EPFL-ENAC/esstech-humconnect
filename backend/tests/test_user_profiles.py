import asyncio
import os
from uuid import uuid4

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from enacit4r_auth.services.auth import User

from api.models.user_profile import UserProfile
from api.services.user_profiles import get_or_create_user_profile_from_token


class FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class FakeProfileSession:
    def __init__(self, profile=None):
        self.profile = profile
        self.added = []
        self.commit_count = 0
        self.refresh_count = 0

    async def exec(self, query):
        return FakeResult(self.profile)

    def add(self, profile):
        self.added.append(profile)
        self.profile = profile

    async def commit(self):
        self.commit_count += 1

    async def refresh(self, profile):
        self.refresh_count += 1


def make_user(**overrides):
    values = {
        "id": "keycloak-sub-1",
        "username": "jane",
        "email": "jane@example.test",
        "first_name": "Jane",
        "last_name": "Example",
        "realm_roles": ["default-roles-epfl"], # ["humconnect-user"]
        "client_roles": [],
    }
    values.update(overrides)
    return User(**values)


def test_get_or_create_user_profile_creates_missing_profile():
    session = FakeProfileSession()

    profile = asyncio.run(get_or_create_user_profile_from_token(make_user(), session))

    assert profile.keycloak_sub == "keycloak-sub-1"
    assert profile.email == "jane@example.test"
    assert session.added == [profile]
    assert session.commit_count == 1
    assert session.refresh_count == 1


def test_get_or_create_user_profile_skips_commit_when_identity_unchanged():
    profile = UserProfile(
        id=uuid4(),
        keycloak_sub="keycloak-sub-1",
        email="jane@example.test",
        username="jane",
        first_name="Jane",
        last_name="Example",
    )
    original_updated_at = profile.updated_at
    session = FakeProfileSession(profile)

    result = asyncio.run(get_or_create_user_profile_from_token(make_user(), session))

    assert result is profile
    assert profile.updated_at == original_updated_at
    assert session.added == []
    assert session.commit_count == 0
    assert session.refresh_count == 0


def test_get_or_create_user_profile_updates_changed_identity():
    profile = UserProfile(
        id=uuid4(),
        keycloak_sub="keycloak-sub-1",
        email="old@example.test",
        username="jane",
        first_name="Jane",
        last_name="Example",
    )
    original_updated_at = profile.updated_at
    session = FakeProfileSession(profile)

    result = asyncio.run(
        get_or_create_user_profile_from_token(
            make_user(email="new@example.test"),
            session,
        )
    )

    assert result is profile
    assert profile.email == "new@example.test"
    assert profile.updated_at > original_updated_at
    assert session.added == [profile]
    assert session.commit_count == 1
    assert session.refresh_count == 1
