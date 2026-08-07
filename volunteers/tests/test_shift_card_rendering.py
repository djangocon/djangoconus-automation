"""Both pages that draw shift cards have to agree.

The shift list and "my shifts" render the same card from two templates. The
first fix only landed on the shift list, so the page a volunteer reaches from
the reminder email kept stuttering. These tests cover both.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup

User = get_user_model()

ROLE = "In-person sprints welcomer"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture
def shift(db):
    role = Role.objects.create(name=ROLE, documentation_url="https://handbook.example/sprints")
    start = timezone.now() + datetime.timedelta(hours=4)
    return Shift.objects.create(
        role=role,
        title=f"{ROLE} · Thu 9:00 AM",
        location="LaSalle Ballroom",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
    )


@pytest.mark.django_db
class TestShiftListCard:
    def test_the_redundant_title_is_not_rendered(self, client, shift):
        """The role filter legitimately names the role, so target the stutter itself."""
        content = client.get(reverse("volunteers:shifts")).content.decode()
        assert shift.title not in content, "the card still prints '<Role> · <Day> <time>' above the role line"
        assert ROLE in content, "the role name should still head the card"

    def test_the_time_and_place_still_show(self, client, shift):
        content = client.get(reverse("volunteers:shifts")).content.decode()
        assert "LaSalle Ballroom" in content

    def test_documentation_link_does_not_repeat_the_role(self, client, shift):
        content = client.get(reverse("volunteers:shifts")).content.decode()
        assert "Role documentation" in content
        assert f"{ROLE} documentation" not in content


@pytest.mark.django_db
class TestMyShiftsCard:
    @pytest.fixture(autouse=True)
    def signed_up(self, client, user, shift):
        VolunteerSignup.objects.create(shift=shift, user=user)
        client.force_login(user)

    def test_the_redundant_title_is_not_rendered(self, client, shift):
        content = client.get(reverse("volunteers:my_shifts")).content.decode()
        assert shift.title not in content, "the card still prints '<Role> · <Day> <time>' above the role line"
        assert ROLE in content, "the role name should still head the card"
        assert content.count(ROLE) == 1, "the role name is rendered twice on this page"

    def test_the_time_and_place_still_show(self, client):
        content = client.get(reverse("volunteers:my_shifts")).content.decode()
        assert "LaSalle Ballroom" in content

    def test_documentation_link_does_not_repeat_the_role(self, client):
        content = client.get(reverse("volunteers:my_shifts")).content.decode()
        assert "Role documentation" in content
        assert f"{ROLE} documentation" not in content
