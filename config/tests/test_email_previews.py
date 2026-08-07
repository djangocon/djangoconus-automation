"""Tests for the staff email preview pages.

The important one is ``test_every_email_template_is_registered``: it walks the
repo for email templates and fails when one isn't in ``EMAIL_PREVIEWS``, so an
email added later can't quietly skip the preview page.
"""

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from config.emails import EMAIL_PREVIEWS, get_preview

User = get_user_model()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Subject lines and the shared bases aren't emails in their own right.
NOT_AN_EMAIL_BODY = ("_subject.txt", "base_message.txt", "base_notification.txt")

# Neither is shared chrome: templates/email/ holds the HTML skeleton every rich
# email extends plus the partials they include. A leading underscore marks a
# partial, the same convention the site templates use.
SHARED_CHROME = {"base.html"}


@pytest.fixture
def staff(db):
    return User.objects.create_user(username="staffer", email="staff@example.com", password="pw12345!", is_staff=True)


@pytest.fixture
def volunteer(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


def find_email_templates() -> set[str]:
    """Every template under a templates/**/email/ directory, as a template name."""
    found = set()
    for base in REPO_ROOT.glob("**/templates"):
        if ".venv" in base.parts or "node_modules" in base.parts:
            continue
        for path in base.glob("**/email/*"):
            if not path.is_file() or path.name.endswith(NOT_AN_EMAIL_BODY):
                continue
            if path.name.startswith("_") or path.name in SHARED_CHROME:
                continue
            found.add(str(path.relative_to(base)))
    return found


@pytest.mark.django_db
class TestEmailPreviewAccess:
    def test_anonymous_is_redirected(self, client):
        response = client.get(reverse("email_previews"))
        assert response.status_code == 302
        assert "/admin/login/" in response["Location"]

    def test_non_staff_is_redirected(self, client, volunteer):
        client.force_login(volunteer)
        response = client.get(reverse("email_previews"))
        assert response.status_code == 302

    def test_staff_sees_the_index(self, client, staff):
        client.force_login(staff)
        response = client.get(reverse("email_previews"))
        assert response.status_code == 200
        content = response.content.decode()
        for preview in EMAIL_PREVIEWS:
            assert preview.label in content

    def test_non_staff_cannot_read_a_detail_page(self, client, volunteer):
        client.force_login(volunteer)
        response = client.get(reverse("email_preview", args=["login-code"]))
        assert response.status_code == 302


@pytest.mark.django_db
class TestEmailPreviewRendering:
    @pytest.mark.parametrize("slug", [preview.slug for preview in EMAIL_PREVIEWS])
    def test_every_preview_renders(self, client, staff, slug):
        client.force_login(staff)
        response = client.get(reverse("email_preview", args=[slug]))
        assert response.status_code == 200
        content = response.content.decode()
        # Every email is branded, so this doubles as a smoke test that a body rendered.
        assert "DjangoCon US" in content

    def test_unknown_slug_is_404(self, client, staff):
        client.force_login(staff)
        assert client.get(reverse("email_preview", args=["nope"])).status_code == 404

    def test_html_part_is_served_standalone(self, client, staff):
        client.force_login(staff)
        response = client.get(reverse("email_preview", args=["ticket-link-initial"]), {"part": "html"})
        assert response.status_code == 200
        assert response.content.decode().lstrip().startswith("<!DOCTYPE html>")

    def test_html_iframe_body_is_escaped(self, client, staff):
        """render_to_string returns a SafeString.

        Interpolated bare into srcdoc, the email's own quotes close the
        attribute early and the iframe renders blank — so the body must arrive
        escaped, with no raw markup loose in the page.
        """
        client.force_login(staff)
        response = client.get(reverse("email_preview", args=["ticket-link-initial"]))
        content = response.content.decode()
        assert 'srcdoc="&lt;!DOCTYPE html&gt;' in content
        # The unescaped body would leave a second <html> tag loose in the page.
        assert content.count("<html") == 1
        # Django's {# #} comment is single-line only; a multi-line one renders as page text.
        assert "force_escape is required" not in content

    def test_html_part_404s_for_text_only_email(self, client, staff):
        """The allauth emails are still text-only; the volunteer ones are not."""
        client.force_login(staff)
        response = client.get(reverse("email_preview", args=["login-code"]), {"part": "html"})
        assert response.status_code == 404

    def test_previews_use_no_real_data(self, client, staff, volunteer):
        """Sample context is fabricated; a preview must not reach into the database."""
        client.force_login(staff)
        for preview in EMAIL_PREVIEWS:
            response = client.get(reverse("email_preview", args=[preview.slug]))
            assert volunteer.email not in response.content.decode()

    def test_reissue_and_resend_differ_from_initial(self):
        initial = get_preview("ticket-link-initial").render().text_body
        resend = get_preview("ticket-link-resend").render().text_body
        reissue = get_preview("ticket-link-reissue").render().text_body
        assert initial != resend != reissue
        assert "no longer works" in reissue
        assert "same link we sent you before" in resend


class TestRegistryCoverage:
    def test_every_email_template_is_registered(self):
        registered = {template for preview in EMAIL_PREVIEWS for template in preview.all_templates}
        missing = find_email_templates() - registered
        assert not missing, (
            f"These email templates have no preview registered in config/emails.py: {sorted(missing)}. "
            "Add an EmailPreview for each so staff can see it at /staff/emails/."
        )

    def test_the_scanner_actually_finds_templates(self):
        """Guard the guard: a broken glob would make the test above vacuously pass."""
        found = find_email_templates()
        assert "tickets/email/ticket_link.txt" in found
        assert "volunteers/email/shift_reminder.txt" in found
        assert len(found) >= 4

    def test_slugs_are_unique(self):
        slugs = [preview.slug for preview in EMAIL_PREVIEWS]
        assert len(slugs) == len(set(slugs))
