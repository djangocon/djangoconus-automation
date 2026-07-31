import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestHomepageVolunteerCTA:
    def test_anonymous_sees_cta_and_signin_hint(self, client):
        response = client.get(reverse("home"))
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse("volunteers:shifts") in content
        assert "Volunteer at DjangoCon US" in content
        assert "sign in when you're ready" in content
        assert reverse("volunteers:my_shifts") not in content

    def test_authenticated_sees_cta_and_my_shifts(self, client):
        user = User.objects.create_user(username="vol", email="vol@example.com", password="pw")
        client.force_login(user)
        response = client.get(reverse("home"))
        assert response.status_code == 200
        content = response.content.decode()
        assert reverse("volunteers:shifts") in content
        assert "Volunteer at DjangoCon US" in content
        assert reverse("volunteers:my_shifts") in content
