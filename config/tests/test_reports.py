"""Every CSV report shares a column contract, and staff can find them all.

The reports grew up separately: the ticket type was "Release" in one report,
"Ticket Type" in another and absent from a third, the date was "Purchased" or
"Ticket Date" depending, and the historical export led with two extra columns.
Anything reading more than one file had to special-case each. These tests pin
the shared prefix so they can't drift apart again.
"""

import csv
import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import escape

from config.views import REPORTS, available_reports
from tickets.models import OnlineAttendee
from titowebhooks.models import TitoWebhookEvent
from titowebhooks.reports import CORE_COLUMNS
from titowebhooks.views import EVENT_SLUG, VOLUNTEER_QUESTION_SLUG, VOLUNTEER_YES

User = get_user_model()


@pytest.fixture
def staff(db):
    """A superuser: the volunteer interest report is not open to staff at large."""
    return User.objects.create_superuser(username="staff", email="staff@example.com", password="pw12345!")


@pytest.fixture
def plain_staff(db):
    return User.objects.create_user(username="desk", email="desk@example.com", password="pw12345!", is_staff=True)


@pytest.fixture
def civilian(db):
    return User.objects.create_user(username="nobody", email="nobody@example.com", password="pw12345!")


def webhook(email, release, *, trigger="ticket.completed", name="Ada Lovelace", created="2026-01-01T10:00:00Z"):
    return TitoWebhookEvent.objects.create(
        trigger=trigger,
        payload={
            "event": {"slug": EVENT_SLUG, "title": "DjangoCon US 2026"},
            "email": email,
            "name": name,
            "release_title": release,
            "release": {"title": release},
            "created_at": created,
            "reference": "ABCD-1",
            "company_name": "Acme",
            "responses": {VOLUNTEER_QUESTION_SLUG: VOLUNTEER_YES},
        },
    )


@pytest.fixture
def tito_events(db):
    """The same people, seen several times — which is how Ti.to really behaves.

    Ti.to fires a hook per ticket event, so one person arrives repeatedly: a
    completed ticket, an update, a second sprint day, a different case in the
    address. Without this the dedup assertions would pass on an empty file.
    """
    # One sponsor, three hooks, two spellings of the same address.
    webhook("Sponsor@Example.com", "Sponsor")
    webhook("sponsor@example.com", "Sponsor", trigger="ticket.updated", created="2026-01-02T10:00:00Z")
    webhook("SPONSOR@example.com", "Sponsor- Online", created="2026-01-03T10:00:00Z")

    # One speaker, twice.
    webhook("speaker@example.com", "Speaker")
    webhook("speaker@example.com", "Speaker", trigger="ticket.updated", created="2026-01-04T10:00:00Z")

    # One sprinter signed up for both days — two releases, one person.
    webhook("sprinter@example.com", "Sprint (In Person)- Thursday (August 27)")
    webhook("sprinter@example.com", "Sprint (In Person)- Friday (August 28)")

    # An online attendee for the attendees report.
    OnlineAttendee.objects.create(year=2026, email="Online@Example.com", name="Ada", release_title="Online- Individual")
    return None


def header_of(response):
    body = response.content.decode()
    return next(csv.reader(io.StringIO(body)))


@pytest.mark.django_db
class TestNormalizedColumns:
    @pytest.mark.parametrize("report", REPORTS, ids=lambda r: r["url_name"] + "?" + r.get("query", ""))
    def test_every_report_starts_with_the_core_columns(self, client, staff, report):
        client.force_login(staff)
        url = reverse(report["url_name"])
        query = report.get("query")

        response = client.get(f"{url}?{query}" if query else url)

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert header_of(response)[: len(CORE_COLUMNS)] == CORE_COLUMNS

    @pytest.mark.parametrize("report", REPORTS, ids=lambda r: r["url_name"] + "?" + r.get("query", ""))
    def test_every_report_downloads_rather_than_renders(self, client, staff, report):
        client.force_login(staff)
        url = reverse(report["url_name"])
        query = report.get("query")

        response = client.get(f"{url}?{query}" if query else url)

        assert response["Content-Disposition"].startswith("attachment;")
        assert ".csv" in response["Content-Disposition"]

    def test_the_old_column_names_are_gone(self, client, staff):
        """'Release' and 'Purchased' were the two odd ones out."""
        client.force_login(staff)
        header = header_of(client.get(reverse("online_attendees"), {"format": "csv"}))
        assert "Release" not in header
        assert "Purchased" not in header
        assert "Ticket Type" in header
        assert "Ticket Date" in header


@pytest.mark.django_db
class TestReportsOnTheHomepage:
    def test_staff_see_every_report(self, client, staff):
        client.force_login(staff)
        response = client.get(reverse("home"))
        content = response.content.decode()

        assert "Reports" in content
        for report in available_reports(staff):
            # escape(): the historical report's "&" is rendered as "&amp;".
            assert escape(report["url"]) in content, f"{report['label']} is missing from the homepage"

    def test_a_report_someone_cannot_open_is_not_linked(self, client, plain_staff):
        """Volunteer interest is superusers and chairs, not staff at large.

        Listing it for everyone would hand plain staff a 403 on click.
        """
        client.force_login(plain_staff)
        response = client.get(reverse("home"))
        labels = [report["label"] for report in response.context["reports"]]

        assert "Speakers" in labels
        assert "Volunteer interest" not in labels

    def test_non_staff_see_no_reports_panel(self, client, civilian):
        client.force_login(civilian)
        response = client.get(reverse("home"))

        assert response.context["reports"] == []
        assert reverse("report_speakers") not in response.content.decode()

    def test_anonymous_sees_no_reports_panel(self, client, db):
        response = client.get(reverse("home"))
        assert response.context["reports"] == []


@pytest.mark.django_db
class TestReportAccess:
    @pytest.mark.parametrize("url_name", ["report_speakers", "report_sponsors"])
    def test_new_reports_require_staff(self, client, civilian, url_name):
        client.force_login(civilian)
        response = client.get(reverse(url_name))
        assert response.status_code == 302


@pytest.mark.django_db
class TestOneRowPerPerson:
    """A mailing list with the same address twice mails that person twice."""

    @pytest.mark.parametrize("report", REPORTS, ids=lambda r: r["url_name"] + "?" + r.get("query", ""))
    def test_no_report_repeats_an_email_address(self, client, staff, report, tito_events):
        client.force_login(staff)
        url = reverse(report["url_name"])
        query = report.get("query")

        response = client.get(f"{url}?{query}" if query else url)

        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        emails = [row["Email"] for row in rows if row["Email"]]
        if report.get("query") == "scope=historical&format=csv":
            # Historical is deliberately one row per person *per year*.
            pairs = [(row["Email"], row["Year"]) for row in rows if row["Email"]]
            assert len(pairs) == len(set(pairs))
        else:
            assert len(emails) == len(set(emails)), f"{report['label']} repeats an address"

    def test_addresses_are_matched_regardless_of_case(self, client, staff, tito_events):
        """Ti.to and hand-typed addresses disagree on case constantly."""
        client.force_login(staff)
        response = client.get(reverse("report_sponsors"))

        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        emails = [row["Email"] for row in rows]
        assert emails == [email.lower() for email in emails]
        assert len(emails) == len(set(emails))
