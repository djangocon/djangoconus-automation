import pytest

from social_monitor.models import PlatformHashTag, SocialPlatform


@pytest.fixture
def social_platform():
    return SocialPlatform.objects.create(
        name="Mastodon",
    )


@pytest.fixture
def hashtags(social_platform):
    return PlatformHashTag.objects.create(
        platform=social_platform,
        query="djangoconus",
    )


@pytest.mark.django_db
class TestSocialPlatform:
    def test_name(self, social_platform):
        assert social_platform.name == "Mastodon"

    def test_mentions(self, social_platform):
        assert social_platform.get_mentions


@pytest.mark.django_db
class TestPlatformHashTag:
    def test_social_platform(self, social_platform, hashtags):
        assert social_platform == hashtags.platform

    def test_query(self, hashtags):
        assert hashtags.query == "djangoconus"

    def test_last_seen(self, hashtags):
        assert hashtags.last_seen is None

    def test_is_active(self, hashtags):
        assert hashtags.is_active
