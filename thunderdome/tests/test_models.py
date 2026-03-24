from decimal import Decimal

import pytest

from thunderdome.models import Event, Review, Speaker, Submission


@pytest.fixture
def event():
    return Event.objects.create(
        name="DjangoCon US 2026",
        pretalx_slug="djangocon-us-2026",
        start_date="2026-08-24",
        end_date="2026-08-28",
    )


@pytest.fixture
def speaker():
    return Speaker.objects.create(name="Test Speaker", pretalx_code="ABCDEF")


@pytest.fixture
def submission(event, speaker):
    sub = Submission.objects.create(
        pretalx_id="TEST01",
        event=event,
        title="Test Talk",
        abstract="A great talk about testing.",
    )
    sub.speakers.add(speaker)
    return sub


@pytest.mark.django_db
class TestSubmission:
    def test_str(self, submission):
        assert str(submission) == "TEST01: Test Talk"

    def test_review_count_no_reviews(self, submission):
        assert submission.review_count == 0

    def test_review_mean_no_reviews(self, submission):
        assert submission.review_mean is None

    def test_review_median_no_reviews(self, submission):
        assert submission.review_median is None

    def test_unique_together(self, event):
        Submission.objects.create(pretalx_id="UNIQ01", event=event, title="Talk 1")
        with pytest.raises(Exception):
            Submission.objects.create(pretalx_id="UNIQ01", event=event, title="Talk 2")


@pytest.mark.django_db
class TestReview:
    def test_review_scores(self, submission):
        Review.objects.create(submission=submission, reviewer_name="Alice", score=Decimal("2.00"))
        Review.objects.create(submission=submission, reviewer_name="Bob", score=Decimal("1.00"))
        Review.objects.create(submission=submission, reviewer_name="Charlie", score=Decimal("0.00"))

        assert submission.review_count == 3
        assert submission.review_mean == Decimal("1.0")
        assert submission.review_median == Decimal("1.00")

    def test_pretalx_review_import(self, submission):
        Review.objects.create(
            submission=submission,
            reviewer_name="pretalx_user",
            pretalx_review_id=12345,
            score=Decimal("1.50"),
            notes="Good talk",
        )
        assert submission.review_count == 1
        assert submission.reviews.first().display_name == "pretalx_user"

    def test_null_scores_excluded(self, submission):
        Review.objects.create(submission=submission, reviewer_name="Scorer", score=Decimal("2.00"))
        Review.objects.create(submission=submission, reviewer_name="Unscored", score=None)

        assert submission.review_count == 1
        assert submission.review_mean == Decimal("2.0")
