"""The preview page has to show both parts of a multipart email.

Staff use these pages to sign off on wording before a send, so "what would the
rich version look like" and "what does it degrade to" both have to be reachable,
and text-only emails must not offer a rich tab that renders nothing.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()

MULTIPART = "shift-reminder"
TEXT_ONLY = "login-code"


@pytest.fixture
def staff_client(client, db):
    user = User.objects.create_user(username="staff", email="staff@example.com", password="pw12345!", is_staff=True)
    client.force_login(user)
    return client


@pytest.mark.django_db
class TestEmailPreviewDetail:
    def test_multipart_email_defaults_to_the_rich_version(self, staff_client):
        response = staff_client.get(reverse("email_preview", args=[MULTIPART]))
        assert response.status_code == 200
        assert response.context["view"] == "rich"
        assert b"<iframe" in response.content

    def test_plain_text_version_is_reachable(self, staff_client):
        response = staff_client.get(reverse("email_preview", args=[MULTIPART]), {"view": "text"})
        assert response.status_code == 200
        assert response.context["view"] == "text"
        assert b"<iframe" not in response.content

    def test_text_only_email_falls_back_to_text(self, staff_client):
        """No HTML part, so asking for rich must not render an empty frame."""
        response = staff_client.get(reverse("email_preview", args=[TEXT_ONLY]), {"view": "rich"})
        assert response.status_code == 200
        assert response.context["view"] == "text"
        assert b"<iframe" not in response.content

    def test_a_nonsense_view_falls_back_rather_than_erroring(self, staff_client):
        response = staff_client.get(reverse("email_preview", args=[MULTIPART]), {"view": "sideways"})
        assert response.status_code == 200
        assert response.context["view"] == "rich"

    def test_standalone_html_part_is_served_raw(self, staff_client):
        response = staff_client.get(reverse("email_preview", args=[MULTIPART]), {"part": "html"})
        assert response.status_code == 200
        assert response.content.strip().startswith(b"<!DOCTYPE html>")

    def test_standalone_html_404s_for_a_text_only_email(self, staff_client):
        response = staff_client.get(reverse("email_preview", args=[TEXT_ONLY]), {"part": "html"})
        assert response.status_code == 404

    def test_preview_requires_staff(self, client, db):
        user = User.objects.create_user(username="nobody", email="nobody@example.com", password="pw12345!")
        client.force_login(user)
        response = client.get(reverse("email_preview", args=[MULTIPART]))
        assert response.status_code == 302
