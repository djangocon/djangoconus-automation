import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoWebhookEvent

User = get_user_model()

URL = "/tito/volunteer-interest/"


def make_event(email, name="Someone", trigger="ticket.completed", answer="Yes!", **extra):
    """Build a Ti.to webhook event shaped like the real payloads."""
    payload = {
        "_type": "ticket",
        "email": email,
        "name": name,
        "company_name": extra.get("company_name", ""),
        "reference": extra.get("reference", "ABCD-1"),
        "release": {"title": extra.get("release_title", "Individual")},
        "created_at": extra.get("created_at", "2026-04-03T12:00:00.000-05:00"),
        "responses": {},
    }
    if answer is not None:
        payload["responses"]["are-you-interested-in-volunteering-at-th"] = answer
    return TitoWebhookEvent.objects.create(trigger=trigger, payload=payload, payload_text="")


@pytest.fixture
def superuser_client(client, db):
    user = User.objects.create_user(
        username="root", email="root@example.com", password="pw12345!", is_staff=True, is_superuser=True
    )
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_requires_superuser_when_anonymous(client):
    response = client.get(URL)
    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_requires_superuser_when_merely_staff(client):
    staff = User.objects.create_user(username="staffer", email="staff@example.com", password="pw12345!", is_staff=True)
    client.force_login(staff)

    response = client.get(URL)

    assert response.status_code in (302, 403)


@pytest.mark.django_db
def test_lists_only_people_who_answered_yes(superuser_client):
    make_event("yes@example.com", name="Yes Person")
    make_event("no@example.com", name="No Person", answer=None)

    response = superuser_client.get(URL)

    assert response.status_code == 200
    assert b"yes@example.com" in response.content
    assert b"no@example.com" not in response.content


@pytest.mark.django_db
def test_deduplicates_multiple_events_for_one_person(superuser_client):
    """Ti.to fires several webhooks per ticket; the person should appear once."""
    make_event("dupe@example.com", name="Dupe Person", trigger="ticket.completed")
    make_event("dupe@example.com", name="Dupe Person", trigger="ticket.updated")
    make_event("dupe@example.com", name="Dupe Person", trigger="ticket.updated")

    response = superuser_client.get(URL)

    assert response.context["total_count"] == 1
    assert response.content.count(b"dupe@example.com") == 2  # mailto href + link text


@pytest.mark.django_db
def test_excludes_people_whose_latest_event_voided_the_ticket(superuser_client):
    make_event("void@example.com", name="Void Person", trigger="ticket.completed")
    make_event("void@example.com", name="Void Person", trigger="ticket.voided")

    response = superuser_client.get(URL)

    assert response.context["total_count"] == 0
    assert b"void@example.com" not in response.content


@pytest.mark.django_db
def test_email_matching_is_case_insensitive(superuser_client):
    make_event("Mixed@Example.com", name="Mixed Case", trigger="ticket.completed")
    make_event("mixed@example.com", name="Mixed Case", trigger="ticket.updated")

    response = superuser_client.get(URL)

    assert response.context["total_count"] == 1


@pytest.mark.django_db
def test_csv_download(superuser_client):
    make_event("csv@example.com", name="CSV Person", company_name="Acme", reference="ZZZZ-1")

    response = superuser_client.get(URL + "?format=csv")

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "volunteer_interest.csv" in response["Content-Disposition"]
    body = response.content.decode()
    assert "csv@example.com" in body
    assert "Acme" in body
    assert "ZZZZ-1" in body


@pytest.mark.django_db
def test_flags_people_who_already_signed_up(superuser_client):
    from volunteers.models import Role, Shift, VolunteerSignup

    volunteer = User.objects.create_user(username="vol", email="signed@example.com", password="pw12345!")
    role = Role.objects.create(name="Room Chair")
    shift = Shift.objects.create(
        role=role,
        starts_at="2026-08-26T09:00:00Z",
        ends_at="2026-08-26T10:00:00Z",
        capacity=2,
    )
    VolunteerSignup.objects.create(shift=shift, user=volunteer)

    make_event("signed@example.com", name="Signed Up")
    make_event("unsigned@example.com", name="Not Signed Up")

    response = superuser_client.get(URL)

    assert response.context["total_count"] == 2
    assert response.context["signed_up_count"] == 1
    assert response.context["not_signed_up_count"] == 1


@pytest.mark.django_db
def test_empty_state(superuser_client):
    response = superuser_client.get(URL)

    assert response.status_code == 200
    assert response.context["total_count"] == 0
