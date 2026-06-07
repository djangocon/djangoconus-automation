import base64
import hashlib
import hmac
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from titowebhooks.models import TitoWebhookEvent
from titowebhooks.views import (
    EVENT_SLUG,
    JOINER_QUESTION_ID,
    LEADER_QUESTION_ID,
    _extract_historical_sprints,
)

TEST_PAYLOAD = {
    "_type": "ticket",
    "id": 9463489,
    "test_mode": True,
    "name": "Test User",
    "first_name": "Test",
    "last_name": "User",
    "email": "test@example.com",
    "event": {
        "_type": "event",
        "id": 1085033,
        "title": "Test Event",
        "account_slug": "defna",
        "slug": "test-event",
        "start_date": None,
        "end_date": None,
    },
}

TEST_SECURITY_TOKEN = "test-security-token"


def make_signature(payload_bytes, token):
    return base64.b64encode(hmac.new(token.encode(), payload_bytes, hashlib.sha256).digest()).decode().strip()


@pytest.mark.django_db
class TestTitoWebhookView(TestCase):
    def _post_webhook(self, payload_bytes, headers=None):
        default_headers = {
            "HTTP_X_WEBHOOK_NAME": "ticket.created",
            "HTTP_X_WEBHOOK_ENDPOINT_ID": "12345",
        }
        default_headers.update(headers or {})
        return self.client.post(
            "/titowebhook/",
            data=payload_bytes,
            content_type="application/json",
            **default_headers,
        )

    @override_settings(TITO_SECURITY_TOKEN="")
    @patch("titowebhooks.views.async_task")
    def test_webhook_without_token_configured(self, mock_async_task):
        """When no security token is configured, webhooks are accepted without signature."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        response = self._post_webhook(payload_bytes)
        assert response.status_code == 200

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_valid_signature(self, mock_async_task):
        """When security token is configured, valid signatures are accepted."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        signature = make_signature(payload_bytes, TEST_SECURITY_TOKEN)
        response = self._post_webhook(payload_bytes, headers={"HTTP_TITO_SIGNATURE": signature})
        assert response.status_code == 200

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_invalid_signature(self, mock_async_task):
        """When security token is configured, invalid signatures are rejected."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        response = self._post_webhook(payload_bytes, headers={"HTTP_TITO_SIGNATURE": "invalid"})
        assert response.status_code == 403

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_missing_signature(self, mock_async_task):
        """When security token is configured, missing signatures are rejected."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        response = self._post_webhook(payload_bytes)
        assert response.status_code == 403

    @override_settings(TITO_SECURITY_TOKEN=TEST_SECURITY_TOKEN)
    @patch("titowebhooks.views.async_task")
    def test_webhook_with_wrong_token_signature(self, mock_async_task):
        """Signature computed with wrong token is rejected."""
        payload_bytes = json.dumps(TEST_PAYLOAD).encode()
        signature = make_signature(payload_bytes, "wrong-token")
        response = self._post_webhook(payload_bytes, headers={"HTTP_TITO_SIGNATURE": signature})
        assert response.status_code == 403


def _sprint_payload(*, email, release_title, created_at, leading="No", joining="No", name=None):
    return {
        "name": name or email.split("@")[0],
        "email": email,
        "release_title": release_title,
        "created_at": created_at,
        "event": {"slug": EVENT_SLUG},
        "answers": [
            {"question": {"id": LEADER_QUESTION_ID}, "humanized_response": leading},
            {"question": {"id": JOINER_QUESTION_ID}, "humanized_response": joining},
        ],
    }


@pytest.mark.django_db
class TestSprintTicketsView(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staff", password="x", email="staff@example.com", is_staff=True
        )
        self.client.force_login(self.staff)

    def _create_event(self, payload):
        TitoWebhookEvent.objects.create(trigger="ticket.completed", payload=payload)

    def test_excludes_online_sprints_by_default(self):
        self._create_event(
            _sprint_payload(
                email="inperson@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2026-09-01T10:00:00Z",
                leading="Yes",
            )
        )
        self._create_event(
            _sprint_payload(
                email="onliner@example.com",
                release_title="Online Sprint - Thursday",
                created_at="2026-09-02T10:00:00Z",
            )
        )

        response = self.client.get(reverse("sprint_tickets"))

        assert response.status_code == 200
        emails = [t["email"] for t in response.context["sprint_tickets"]]
        assert "inperson@example.com" in emails
        assert "onliner@example.com" not in emails
        assert response.context["total_count"] == 1

    def test_include_online_query_param_shows_online(self):
        self._create_event(
            _sprint_payload(
                email="inperson@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2026-09-01T10:00:00Z",
            )
        )
        self._create_event(
            _sprint_payload(
                email="onliner@example.com",
                release_title="Online Sprint - Thursday",
                created_at="2026-09-02T10:00:00Z",
            )
        )

        response = self.client.get(reverse("sprint_tickets") + "?include_online=1")

        assert response.status_code == 200
        emails = [t["email"] for t in response.context["sprint_tickets"]]
        assert {"inperson@example.com", "onliner@example.com"} <= set(emails)
        assert response.context["online_count"] == 1
        assert response.context["include_online"] is True

    def test_email_dedup_is_case_insensitive(self):
        self._create_event(
            _sprint_payload(
                email="Mixed@Example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2026-09-01T10:00:00Z",
                leading="Yes",
            )
        )
        self._create_event(
            _sprint_payload(
                email="mixed@example.com",
                release_title="Sprint (In Person) - Friday",
                created_at="2026-09-02T10:00:00Z",
                joining="Yes",
            )
        )

        response = self.client.get(reverse("sprint_tickets"))

        tickets = response.context["sprint_tickets"]
        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket["email"] == "mixed@example.com"
        assert ticket["thursday"] is True
        assert ticket["thursday_leading"] == "Yes"
        assert ticket["friday"] is True
        assert ticket["friday_joining"] == "Yes"

    def test_ignores_other_events_and_non_sprint_releases(self):
        self._create_event(
            _sprint_payload(
                email="other-event@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2026-09-01T10:00:00Z",
            )
            | {"event": {"slug": "djangocon-us-2023"}}
        )
        self._create_event(
            _sprint_payload(
                email="conf-only@example.com",
                release_title="In-person Conference",
                created_at="2026-09-01T10:00:00Z",
            )
        )

        response = self.client.get(reverse("sprint_tickets"))

        assert response.context["total_count"] == 0

    def test_csv_download_excludes_online_by_default(self):
        self._create_event(
            _sprint_payload(
                email="inperson@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2026-09-01T10:00:00Z",
            )
        )
        self._create_event(
            _sprint_payload(
                email="onliner@example.com",
                release_title="Online Sprint - Thursday",
                created_at="2026-09-02T10:00:00Z",
            )
        )

        response = self.client.get(reverse("sprint_tickets") + "?format=csv")

        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        body = response.content.decode()
        assert "inperson@example.com" in body
        assert "onliner@example.com" not in body
        assert "Online" in body.splitlines()[0]


def _historical_payload(*, email, release_title, created_at, year, leading="No", joining="No", name=None):
    slug = f"djangocon-us-{year}"
    return {
        "name": name or email.split("@")[0],
        "email": email,
        "release_title": release_title,
        "created_at": created_at,
        "event": {"slug": slug, "title": f"DjangoCon US {year}"},
        "answers": [
            {"question": {"id": LEADER_QUESTION_ID}, "humanized_response": leading},
            {"question": {"id": JOINER_QUESTION_ID}, "humanized_response": joining},
        ],
    }


@pytest.mark.django_db
class TestHistoricalSprintTicketsCsv(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staff", password="x", email="staff@example.com", is_staff=True
        )
        self.client.force_login(self.staff)

    def _create_event(self, payload):
        TitoWebhookEvent.objects.create(trigger="ticket.completed", payload=payload)

    def _download(self, query=""):
        response = self.client.get(reverse("sprint_tickets") + "?scope=historical&format=csv" + query)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        assert "sprint_tickets_historical.csv" in response["Content-Disposition"]
        return response.content.decode()

    def test_spans_multiple_years_with_event_and_year_columns(self):
        self._create_event(
            _historical_payload(
                email="alice@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2024-09-01T10:00:00Z",
                year=2024,
            )
        )
        self._create_event(
            _historical_payload(
                email="bob@example.com",
                release_title="Sprint (In Person) - Friday",
                created_at="2026-09-01T10:00:00Z",
                year=2026,
            )
        )

        body = self._download()

        header = body.splitlines()[0]
        assert header.startswith("Year,Event,Name,Email")
        assert "DjangoCon US 2024" in body
        assert "DjangoCon US 2026" in body
        assert "alice@example.com" in body
        assert "bob@example.com" in body

    def test_excludes_online_sprints_by_default(self):
        self._create_event(
            _historical_payload(
                email="inperson@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2025-09-01T10:00:00Z",
                year=2025,
            )
        )
        self._create_event(
            _historical_payload(
                email="onliner@example.com",
                release_title="Online Sprint - Thursday",
                created_at="2025-09-02T10:00:00Z",
                year=2025,
            )
        )

        body = self._download()

        assert "inperson@example.com" in body
        assert "onliner@example.com" not in body

    def test_include_online_query_param_shows_online(self):
        self._create_event(
            _historical_payload(
                email="onliner@example.com",
                release_title="Online Sprint - Thursday",
                created_at="2025-09-02T10:00:00Z",
                year=2025,
            )
        )

        body = self._download(query="&include_online=1")

        assert "onliner@example.com" in body

    def test_one_row_per_person_per_year_merges_days(self):
        self._create_event(
            _historical_payload(
                email="repeat@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2025-09-01T10:00:00Z",
                year=2025,
                leading="Yes",
            )
        )
        self._create_event(
            _historical_payload(
                email="repeat@example.com",
                release_title="Sprint (In Person) - Friday",
                created_at="2025-09-02T10:00:00Z",
                year=2025,
                joining="Yes",
            )
        )
        # Same person, different year -> separate row.
        self._create_event(
            _historical_payload(
                email="repeat@example.com",
                release_title="Sprint (In Person) - Thursday",
                created_at="2024-09-01T10:00:00Z",
                year=2024,
            )
        )

        body = self._download()
        rows = [line for line in body.splitlines()[1:] if "repeat@example.com" in line]
        assert len(rows) == 2
        merged_2025 = next(r for r in rows if r.startswith("2025"))
        # Both Thursday (leading) and Friday (joining) captured on one row.
        assert merged_2025.count("Yes") >= 2

    def test_window_anchored_to_current_calendar_year(self):
        for year in (2021, 2022, 2023, 2024, 2025, 2026):
            self._create_event(
                _historical_payload(
                    email=f"y{year}@example.com",
                    release_title="Sprint (In Person) - Thursday",
                    created_at=f"{year}-09-01T10:00:00Z",
                    year=year,
                )
            )

        # current_year - years (3) = 2023, so 2023 and newer are kept regardless of
        # which year happens to be the most recent one present in the data.
        rows = _extract_historical_sprints(current_year=2026)
        years = {r["year"] for r in rows}
        assert years == {2023, 2024, 2025, 2026}

    def test_window_stable_when_current_year_data_missing(self):
        # No 2026 webhooks captured (e.g. coverage gap); the window must still be
        # anchored to the current calendar year, not the newest year in the data.
        for year in (2022, 2023, 2024):
            self._create_event(
                _historical_payload(
                    email=f"y{year}@example.com",
                    release_title="Sprint (In Person) - Thursday",
                    created_at=f"{year}-09-01T10:00:00Z",
                    year=year,
                )
            )

        rows = _extract_historical_sprints(current_year=2026)
        years = {r["year"] for r in rows}
        # Anchored to 2026: cutoff 2023, so 2022 drops even though it is recent in the data.
        assert years == {2023, 2024}
