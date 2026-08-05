"""The magic-link page has to work for people who have never signed up."""

import re

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client

User = get_user_model()

REQUEST_CODE_URL = "/accounts/login/code/"


def _request_code(email, client=None):
    return (client or Client()).post(REQUEST_CODE_URL, data={"email": email})


@pytest.mark.django_db
def test_unknown_email_gets_an_account_and_a_code():
    response = _request_code("newcomer@example.com")

    assert response.status_code == 302
    assert response.url == "/accounts/login/code/confirm/"

    user = User.objects.get(email="newcomer@example.com")
    assert user.username == "newcomer"
    assert not user.has_usable_password()
    assert EmailAddress.objects.filter(user=user, email="newcomer@example.com", primary=True).exists()

    # The code, not the "we have no record of you" rejection.
    assert len(mail.outbox) == 1
    assert "do not have any record" not in mail.outbox[0].body


@pytest.mark.django_db
def test_existing_user_is_reused_not_duplicated():
    existing = User.objects.create_user(username="regular", email="regular@example.com", password="x")

    _request_code("regular@example.com")

    assert User.objects.filter(email="regular@example.com").count() == 1
    assert User.objects.get(email="regular@example.com").pk == existing.pk
    # An existing password must survive a magic-link request.
    assert User.objects.get(pk=existing.pk).has_usable_password()


@pytest.mark.django_db
def test_repeat_requests_do_not_pile_up_accounts():
    _request_code("repeat@example.com")
    _request_code("repeat@example.com")

    assert User.objects.filter(email="repeat@example.com").count() == 1
    assert EmailAddress.objects.filter(email="repeat@example.com").count() == 1


@pytest.mark.django_db
def test_same_local_part_different_domains_get_distinct_usernames():
    _request_code("jeff@example.com")
    _request_code("jeff@other.com")

    usernames = sorted(User.objects.values_list("username", flat=True))
    assert User.objects.count() == 2
    # allauth appends a counter; the exact number is its business, distinctness is ours.
    assert len(set(usernames)) == 2
    assert all(name.startswith("jeff") for name in usernames)


@pytest.mark.django_db
def test_casing_does_not_create_a_second_account():
    _request_code("Mixed@Example.com")
    _request_code("mixed@example.com")

    assert User.objects.count() == 1


@pytest.mark.django_db
def test_invalid_address_creates_nothing():
    response = _request_code("not-an-email")

    assert response.status_code == 200  # redisplayed with errors
    assert User.objects.count() == 0
    assert not mail.outbox


@pytest.mark.django_db
def test_auto_created_user_is_not_staff_or_super():
    _request_code("nobody@example.com")

    user = User.objects.get(email="nobody@example.com")
    assert not user.is_staff
    assert not user.is_superuser
    assert user.is_active


@pytest.mark.django_db
def test_the_emailed_code_actually_logs_the_new_user_in():
    client = Client()
    _request_code("roundtrip@example.com", client=client)

    # Pull the code out of the sign-in link the way a recipient clicking it would.
    match = re.search(r"\?code=(\S+)", mail.outbox[0].body)
    assert match, f"no sign-in link in the email:\n{mail.outbox[0].body}"
    code = match.group(1)

    response = client.post("/accounts/login/code/confirm/", data={"code": code})

    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(User.objects.get(email="roundtrip@example.com").pk)
