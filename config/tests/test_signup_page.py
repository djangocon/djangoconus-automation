import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_signup_page_puts_github_and_magic_link_before_password_form(client):
    response = client.get(reverse("account_signup"))
    assert response.status_code == 200
    content = response.content.decode()

    github = content.index("Sign Up with GitHub")
    magic_link = content.index(reverse("account_request_login_code"))
    divider = content.index("or sign up with email")
    password_form = content.index('action="' + reverse("account_signup"))

    assert github < divider
    assert magic_link < divider
    assert divider < password_form
