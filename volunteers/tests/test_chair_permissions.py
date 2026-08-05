"""The Volunteer Chair group: what it unlocks, and who shows up as a chair."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.permissions import VOLUNTEER_CHAIR_GROUP, grant_chair_group, volunteer_chairs

User = get_user_model()

DASHBOARD = "volunteers:dashboard"
VOLUNTEERS_LIST = "volunteers:volunteers_list"
INTEREST_REPORT = "volunteer_interest"


@pytest.fixture
def chair_group(db):
    """The group migration 0010 seeds.

    Built here rather than read from the migration because the suite runs with
    ``--nomigrations``, so data migrations never execute. Both paths call the
    same ``grant_chair_group`` helper.
    """
    return grant_chair_group()


@pytest.fixture
def chair(db, chair_group):
    user = User.objects.create_user(username="chair", email="chair@example.com", password="pw12345!")
    user.groups.add(chair_group)
    return user


@pytest.fixture
def chair_client(client, chair):
    client.force_login(chair)
    return client


def test_seeding_grants_both_permissions(chair_group):
    assert chair_group.name == VOLUNTEER_CHAIR_GROUP
    codenames = set(chair_group.permissions.values_list("codename", flat=True))
    assert codenames == {"view_volunteer_dashboard", "view_volunteer_interest"}


def test_seeding_is_idempotent(chair_group):
    again = grant_chair_group()

    assert again.pk == chair_group.pk
    assert Group.objects.filter(name=VOLUNTEER_CHAIR_GROUP).count() == 1
    assert again.permissions.count() == 2


@pytest.mark.parametrize("url_name", [DASHBOARD, VOLUNTEERS_LIST, INTEREST_REPORT])
def test_chair_can_reach_coordinator_pages(chair_client, url_name):
    assert chair_client.get(reverse(url_name)).status_code == 200


@pytest.mark.parametrize("url_name", [DASHBOARD, VOLUNTEERS_LIST, INTEREST_REPORT])
def test_plain_volunteer_is_forbidden(client, db, url_name):
    user = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    client.force_login(user)
    assert client.get(reverse(url_name)).status_code == 403


@pytest.mark.parametrize("url_name", [DASHBOARD, VOLUNTEERS_LIST, INTEREST_REPORT])
def test_anonymous_is_sent_to_log_in(client, db, url_name):
    response = client.get(reverse(url_name))
    assert response.status_code == 302
    assert reverse("account_login") in response["Location"]


def test_staff_keep_dashboard_access_without_the_group(client, db):
    """Nothing is taken away from existing staff by the permission switch."""
    staff = User.objects.create_user(username="staff", email="staff@example.com", password="pw12345!", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse(DASHBOARD)).status_code == 200


def test_staff_alone_still_cannot_see_the_interest_report(client, db):
    """The report was superuser-only; being staff is still not enough."""
    staff = User.objects.create_user(username="staff", email="staff@example.com", password="pw12345!", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse(INTEREST_REPORT)).status_code == 403


def test_superusers_keep_access_to_everything(client, db):
    root = User.objects.create_superuser(username="root", email="root@example.com", password="pw12345!")
    client.force_login(root)
    assert client.get(reverse(DASHBOARD)).status_code == 200
    assert client.get(reverse(INTEREST_REPORT)).status_code == 200


def test_chair_can_manage_the_dashboard(chair_client, db):
    """ "Manage," not just "see" — the dashboard's POST actions open up too."""
    role = Role.objects.create(name="Registration Desk")
    shift = Shift.objects.create(
        role=role,
        title="Doomed",
        starts_at="2026-08-26T09:00:00Z",
        ends_at="2026-08-26T10:00:00Z",
    )

    response = chair_client.post(reverse("volunteers:delete_shift", args=[shift.pk]))

    assert response.status_code == 302
    assert not Shift.objects.filter(pk=shift.pk).exists()


def test_chair_can_update_contact_info(chair_client, db):
    response = chair_client.post(reverse("volunteers:update_contact"), {"contact_info": "Find us in #volunteers"})

    assert response.status_code == 302
    assert chair_client.get(reverse("volunteers:my_shifts")).context["contact_info"] == "Find us in #volunteers"


def test_chairs_appear_on_my_shifts(client, db, chair):
    chair.first_name = "Robin"
    chair.last_name = "Chair"
    chair.save(update_fields=["first_name", "last_name"])
    volunteer = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    client.force_login(volunteer)

    response = client.get(reverse("volunteers:my_shifts"))
    body = response.content.decode()

    assert list(response.context["chairs"]) == [chair]
    assert "Robin Chair" in body


def test_chairs_line_uses_the_shared_address_not_personal_email(client, db, chair, settings):
    """Chairs are named, but the mailto is the shared address, not a personal one."""
    settings.VOLUNTEER_CONTACT_EMAIL = "volunteers@example.com"
    volunteer = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    client.force_login(volunteer)

    body = client.get(reverse("volunteers:my_shifts")).content.decode()

    assert "mailto:volunteers@example.com" in body
    assert "chair@example.com" not in body


def test_chairs_line_drops_the_link_when_no_shared_address_is_set(client, db, chair, settings):
    """The default: no address configured, so the names show without a mailto."""
    settings.VOLUNTEER_CONTACT_EMAIL = ""
    volunteer = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    client.force_login(volunteer)

    body = client.get(reverse("volunteers:my_shifts")).content.decode()

    assert "mailto:" not in body
    assert "Volunteer chairs:" in body


def test_only_active_group_members_are_chairs(db, chair, chair_group):
    User.objects.create_user(username="nobody", email="nobody@example.com", password="pw12345!")
    inactive = User.objects.create_user(username="former", email="former@example.com", password="pw12345!")
    inactive.groups.add(chair_group)
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])

    assert list(volunteer_chairs()) == [chair]


def test_chair_needs_no_staff_flag(chair):
    """The whole point: coordinator access without the Django admin."""
    assert not chair.is_staff
    assert not chair.is_superuser


def test_my_shifts_hides_the_contacts_box_when_there_is_nothing_to_show(client, db):
    volunteer = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    client.force_login(volunteer)

    response = client.get(reverse("volunteers:my_shifts"))

    assert not list(response.context["chairs"])
    assert "Volunteer contacts" not in response.content.decode()


def test_chair_sees_the_coordinator_nav_links(chair_client):
    body = chair_client.get("/").content.decode()  # the nav only renders on the homepage

    assert "Volunteer Dashboard" in body
    assert "Volunteer Interest Report" in body


def test_plain_volunteer_does_not_see_the_coordinator_nav_links(client, db):
    volunteer = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    client.force_login(volunteer)

    body = client.get("/").content.decode()

    assert "Volunteer Dashboard" not in body
    assert "Volunteer Interest Report" not in body


def test_roster_still_lists_volunteers_for_a_chair(chair_client, db):
    volunteer = User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")
    role = Role.objects.create(name="Registration Desk")
    shift = Shift.objects.create(
        role=role,
        title="Reg desk",
        starts_at="2026-08-26T09:00:00Z",
        ends_at="2026-08-26T11:00:00Z",
    )
    VolunteerSignup.objects.create(shift=shift, user=volunteer)

    response = chair_client.get(reverse(VOLUNTEERS_LIST))

    assert response.context["total_volunteers"] == 1
