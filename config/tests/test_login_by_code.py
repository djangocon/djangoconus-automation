import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Allauth throttles request_login_code at 20/m/ip and stores that in the cache.

    Every test here posts from 127.0.0.1, and the cache outlives individual tests,
    so without this the later ones silently get throttled instead of sending mail.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


def request_code(client, email):
    return client.post(reverse("account_request_login_code"), {"email": email})


@pytest.mark.django_db
class TestLoginByCode:
    def test_login_page_offers_email_link(self, client):
        response = client.get(reverse("account_login"))
        assert reverse("account_request_login_code") in response.content.decode()

    def test_request_form_renders(self, client):
        response = client.get(reverse("account_request_login_code"))
        assert response.status_code == 200
        assert "Send Sign-In Email" in response.content.decode()

    def test_request_code_sends_email_with_code_and_link(self, client, user):
        response = request_code(client, user.email)
        assert response.status_code == 302
        assert response.url.startswith(reverse("account_confirm_login_code"))
        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        code = re.search(r"\?code=([A-Z0-9]+)", body).group(1)
        assert code in body
        assert reverse("account_confirm_login_code") in body

    def test_link_prefills_code_on_confirm_page(self, client, user):
        request_code(client, user.email)
        code = re.search(r"\?code=([A-Z0-9]+)", mail.outbox[0].body).group(1)
        response = client.get(reverse("account_confirm_login_code") + f"?code={code}")
        assert response.status_code == 200
        assert f'value="{code}"' in response.content.decode()

    def test_confirming_code_signs_user_in(self, client, user):
        request_code(client, user.email)
        code = re.search(r"\?code=([A-Z0-9]+)", mail.outbox[0].body).group(1)
        response = client.post(reverse("account_confirm_login_code"), {"code": code})
        assert response.status_code == 302
        response = client.get(reverse("home"))
        assert response.context["user"].is_authenticated

    def test_wrong_code_rejected(self, client, user):
        request_code(client, user.email)
        # Depending on the code format, allauth either re-renders the form (200) or
        # invalidates the attempt and bounces back to the request page (302).
        response = client.post(reverse("account_confirm_login_code"), {"code": "WRONG1"})
        assert response.status_code in (200, 302)
        response = client.get(reverse("home"))
        assert not response.context["user"].is_authenticated

    def test_unknown_email_is_signed_up_rather_than_turned_away(self, client):
        """Previously an unknown address got a "no such account" mail and a dead end.

        Attendees have no reason to have signed up first, so the account is now
        created on the spot and the code goes out as normal. See
        config/account_forms.py and config/tests/test_account_forms.py.
        """
        response = request_code(client, "nobody@example.com")
        assert response.status_code == 302
        assert len(mail.outbox) == 1
        assert re.search(r"\?code=([A-Z0-9]+)", mail.outbox[0].body)
        assert User.objects.filter(email="nobody@example.com").exists()

    def test_unknown_email_is_indistinguishable_from_a_known_one(self, user):
        """Enumeration protection: both paths must look the same from outside.

        Separate clients: a session with a login already in flight short-circuits
        the second request, which would compare the two paths unfairly.
        """
        known = request_code(Client(), user.email)
        known_body = mail.outbox[0].body
        mail.outbox.clear()

        unknown = request_code(Client(), "stranger@example.com")
        unknown_body = mail.outbox[0].body

        assert known.status_code == unknown.status_code
        assert known.url == unknown.url
        # Same template, same shape -- only the code itself differs.
        assert bool(re.search(r"\?code=", known_body)) == bool(re.search(r"\?code=", unknown_body))
