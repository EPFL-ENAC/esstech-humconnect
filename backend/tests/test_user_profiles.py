import asyncio
import os
from uuid import uuid4

import pytest
from pydantic import ValidationError

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("OPENAI_API_URL", "http://test.local")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("MEDITRON_MCP_API_KEY", "test")
os.environ.setdefault("KEYCLOAK_API_ID", "test")
os.environ.setdefault("KEYCLOAK_API_SECRET", "test")

from enacit4r_auth.services.auth import User

from api.models.user_profile import UserProfile, UserProfileEditableFields
from api.services.user_profiles import get_or_create_user_profile_from_token
from api.views.profile import get_profile, update_profile


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


def test_get_profile_returns_identity_and_editable_fields():
    profile = UserProfile(
        id=uuid4(),
        keycloak_sub="keycloak-sub-1",
        email="jane@example.test",
        username="jane",
        first_name="Jane",
        last_name="Example",
        profession="Doctor",
        profession_category="medical_clinical",
        center_address="Geneva",
        action_radius_km=50,
        location_extra="Available for field visits",
        organisation="WHO",
        mother_tongue="fr",
    )
    session = FakeProfileSession(profile)

    response = asyncio.run(get_profile(make_user(), session))

    assert response.email == "jane@example.test"
    assert response.profession == "Doctor"
    assert response.profession_category == "medical_clinical"
    assert response.center_address == "Geneva"
    assert response.action_radius_km == 50
    assert response.location_extra == "Available for field visits"
    assert response.organisation == "WHO"
    assert response.mother_tongue == "fr"
    assert session.commit_count == 0


def test_update_profile_persists_editable_fields():
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

    response = asyncio.run(
        update_profile(
            UserProfileEditableFields(
                profession="WASH engineer",
                profession_category="wash",
                center_address="Unity State camp clinic",
                action_radius_km=25,
                location_extra="Block 4 pump area",
                organisation="Local NGO",
                mother_tongue="ar",
            ),
            make_user(),
            session,
        )
    )

    assert response.profession == "WASH engineer"
    assert profile.profession_category == "wash"
    assert profile.center_address == "Unity State camp clinic"
    assert profile.action_radius_km == 25
    assert profile.location_extra == "Block 4 pump area"
    assert profile.organisation == "Local NGO"
    assert profile.mother_tongue == "ar"
    assert profile.updated_at > original_updated_at
    assert session.added == [profile]
    assert session.commit_count == 1
    assert session.refresh_count == 1


def test_user_profile_updates_from_editable_fields_without_session_work():
    profile = UserProfile(
        id=uuid4(),
        keycloak_sub="keycloak-sub-1",
        email="jane@example.test",
    )
    original_updated_at = profile.updated_at

    profile.update_from_editable_fields(
        UserProfileEditableFields(
            profession="Logistician",
            profession_category="logistics_supply",
            center_address="Kabul warehouse",
            action_radius_km=120,
            location_extra="Can coordinate last-mile delivery",
            organisation="WFP",
            mother_tongue="prs",
        )
    )

    assert profile.profession == "Logistician"
    assert profile.profession_category == "logistics_supply"
    assert profile.center_address == "Kabul warehouse"
    assert profile.action_radius_km == 120
    assert profile.location_extra == "Can coordinate last-mile delivery"
    assert profile.organisation == "WFP"
    assert profile.mother_tongue == "prs"
    assert profile.updated_at > original_updated_at


def test_profile_payload_rejects_invalid_category():
    with pytest.raises(ValidationError):
        UserProfileEditableFields(profession_category="invalid")


def test_profile_payload_rejects_negative_radius():
    with pytest.raises(ValidationError):
        UserProfileEditableFields(action_radius_km=-1)


def test_profile_payload_rejects_unknown_mother_tongue():
    with pytest.raises(ValidationError):
        UserProfileEditableFields(mother_tongue="klingon")
