import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestHomepagePanels:
    def test_everyone_sees_both_panels(self, client):
        response = client.get(reverse("home"))
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse("volunteers:shifts") in content
        assert "DjangoCon US Volunteers" in content
        assert reverse("travel_safety:register") in content
        assert "Traveling to DjangoCon US" in content

    def test_anonymous_sees_signin_row(self, client):
        response = client.get(reverse("home"))
        content = response.content.decode()
        assert reverse("account_login") in content
        assert "Sign In or Register" in content
        assert reverse("volunteers:my_shifts") not in content

    def test_authenticated_sees_my_shifts_and_nav(self, client):
        user = User.objects.create_user(username="vol", email="vol@example.com", password="pw")
        client.force_login(user)
        response = client.get(reverse("home"))
        content = response.content.decode()
        assert reverse("volunteers:my_shifts") in content
        assert "Sign In or Register" not in content
        assert reverse("account_logout") in content
