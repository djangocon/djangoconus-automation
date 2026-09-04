"""Every volunteer page offers a way back to the main menu."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift
from volunteers.permissions import grant_chair_group

User = get_user_model()

# Every volunteer page, and whether it needs chair access to reach.
PAGES = [
    ("volunteers:shifts", False),
    ("volunteers:my_shifts", False),
    ("volunteers:dashboard", True),
    ("volunteers:volunteers_list", True),
    ("volunteers:schedule_changes", True),
]


@pytest.fixture
def shift(db):
    role = Role.objects.create(name="Room Monitor")
    starts_at = timezone.now() + datetime.timedelta(days=1)
    return Shift.objects.create(
        role=role, title="Room Monitor", starts_at=starts_at, ends_at=starts_at + datetime.timedelta(hours=2)
    )


@pytest.mark.parametrize(("url_name", "needs_chair"), PAGES)
def test_page_links_back_to_the_main_menu(client, shift, url_name, needs_chair):
    user = User.objects.create_user(username="u", email="u@example.com")
    if needs_chair:
        user.groups.add(grant_chair_group())
    client.force_login(user)

    body = client.get(reverse(url_name)).content.decode()

    # Not just base.html's footer link — an in-page way back, above the fold.
    assert "Main menu" in body
