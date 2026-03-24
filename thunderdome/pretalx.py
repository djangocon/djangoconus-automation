import logging

import requests

logger = logging.getLogger(__name__)

PRETALX_BASE_URL = "https://pretalx.com/api"


def _headers(token):
    return {"Authorization": f"Token {token}"}


def get_submissions(event_slug, token):
    """Fetch all submissions from pretalx, handling pagination."""
    url = f"{PRETALX_BASE_URL}/events/{event_slug}/submissions/?expand=speakers,tags,track"
    submissions = []

    while url:
        response = requests.get(url, headers=_headers(token), timeout=30)
        response.raise_for_status()
        data = response.json()
        submissions.extend(data.get("results", []))
        url = data.get("next")

    return submissions


def get_reviews(event_slug, token):
    """Fetch all reviews from pretalx, handling pagination."""
    url = f"{PRETALX_BASE_URL}/events/{event_slug}/reviews/"
    reviews = []

    while url:
        response = requests.get(url, headers=_headers(token), timeout=30)
        response.raise_for_status()
        data = response.json()
        reviews.extend(data.get("results", []))
        url = data.get("next")

    return reviews


def accept_submission(event_slug, token, submission_code):
    """POST to accept a submission in pretalx."""
    url = f"{PRETALX_BASE_URL}/events/{event_slug}/submissions/{submission_code}/accept/"
    response = requests.post(url, headers=_headers(token), timeout=30)
    response.raise_for_status()
    return response.json()


def reject_submission(event_slug, token, submission_code):
    """POST to reject a submission in pretalx."""
    url = f"{PRETALX_BASE_URL}/events/{event_slug}/submissions/{submission_code}/reject/"
    response = requests.post(url, headers=_headers(token), timeout=30)
    response.raise_for_status()
    return response.json()


STATE_TO_PRETALX_ACTION = {
    "accepted-in-person": accept_submission,
    "accepted-online": accept_submission,
    "rejected": reject_submission,
}


def push_submission_status(submission_id):
    """Push a single submission's status to pretalx. Called by django-q2."""
    from thunderdome.models import Submission

    submission = Submission.objects.select_related("event").get(pk=submission_id)
    action = STATE_TO_PRETALX_ACTION.get(submission.state)

    if action is None:
        logger.info("State '%s' for submission %s is not pushable to pretalx", submission.state, submission.pretalx_id)
        return

    event = submission.event
    if not event.pretalx_token:
        logger.error("No pretalx token configured for event %s", event.name)
        return

    action(event.pretalx_slug, event.pretalx_token, submission.pretalx_id)
    logger.info("Pushed %s status for submission %s to pretalx", submission.state, submission.pretalx_id)
