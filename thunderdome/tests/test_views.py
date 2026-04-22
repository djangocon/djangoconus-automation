import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from thunderdome.models import Event, Speaker, Submission

User = get_user_model()


@pytest.fixture
def event(db):
    return Event.objects.create(
        name="DjangoCon US 2026",
        pretalx_slug="djangocon-us-2026",
        start_date="2026-08-24",
        end_date="2026-08-28",
    )


@pytest.fixture
def staff_client(client, db):
    user = User.objects.create_user(username="staff", password="pass", is_staff=True)
    client.force_login(user)
    return client


@pytest.fixture
def two_submissions(event):
    s1 = Submission.objects.create(pretalx_id="AAA001", event=event, title="Alpha Talk", state="unreviewed")
    s2 = Submission.objects.create(pretalx_id="ZZZ999", event=event, title="Zeta Talk", state="unreviewed")
    return s1, s2


@pytest.mark.django_db
class TestSubmissionSetState:
    def test_set_state_updates_correct_submission(self, staff_client, two_submissions):
        s1, s2 = two_submissions
        url = reverse("thunderdome_submission_set_state", args=[s1.pk])
        response = staff_client.post(url, {"state": "rejected"})
        assert response.status_code == 200
        s1.refresh_from_db()
        s2.refresh_from_db()
        assert s1.state == "rejected"
        assert s2.state == "unreviewed"

    def test_set_state_ignores_extra_state_values(self, staff_client, two_submissions):
        """Posting multiple state values must not bleed over from other rows."""
        s1, s2 = two_submissions
        url = reverse("thunderdome_submission_set_state", args=[s1.pk])
        # Simulate old buggy form that included all rows' state fields
        response = staff_client.post(url, {"state": ["accepted-in-person", "unreviewed"]})
        assert response.status_code == 200
        s1.refresh_from_db()
        assert s1.state == "accepted-in-person"

    def test_invalid_state_not_saved(self, staff_client, two_submissions):
        s1, _ = two_submissions
        url = reverse("thunderdome_submission_set_state", args=[s1.pk])
        staff_client.post(url, {"state": "bogus-state"})
        s1.refresh_from_db()
        assert s1.state == "unreviewed"

    def test_get_not_allowed(self, staff_client, two_submissions):
        s1, _ = two_submissions
        url = reverse("thunderdome_submission_set_state", args=[s1.pk])
        response = staff_client.get(url)
        assert response.status_code == 405

    def test_all_valid_states_accepted(self, staff_client, event):
        for state_value, _ in Submission.STATE_CHOICES:
            sub = Submission.objects.create(
                pretalx_id=f"TST{state_value[:3].upper()}",
                event=event,
                title=f"Talk {state_value}",
            )
            url = reverse("thunderdome_submission_set_state", args=[sub.pk])
            staff_client.post(url, {"state": state_value})
            sub.refresh_from_db()
            assert sub.state == state_value
