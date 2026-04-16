import logging
from decimal import Decimal, InvalidOperation

from .models import Event, Review, Speaker, Submission, Tag
from .pretalx import get_reviews, get_submissions

logger = logging.getLogger(__name__)


def sync_event(event_slug):
    """Sync submissions and reviews from pretalx for the given event slug.

    Can be called from management commands, views, or scheduled tasks.
    Returns a summary dict.
    """
    try:
        event = Event.objects.get(pretalx_slug=event_slug)
    except Event.DoesNotExist:
        logger.error("Event with pretalx_slug '%s' not found.", event_slug)
        return {"error": f"Event '{event_slug}' not found."}

    if not event.pretalx_token:
        logger.error("No pretalx token configured for event '%s'.", event.name)
        return {"error": f"No pretalx token for '{event.name}'."}

    # Sync submissions
    submissions_data = get_submissions(event.pretalx_slug, event.pretalx_token)
    created_count = 0
    updated_count = 0

    for data in submissions_data:
        code = data.get("code", "")
        pretalx_state = data.get("state", "submitted")
        defaults = {
            "title": data.get("title", ""),
            "track": _extract_track_name(data.get("track")),
            "duration": data.get("duration"),
            "abstract": data.get("abstract", ""),
            "description": data.get("description", ""),
            "notes": data.get("notes", ""),
            "pretalx_state": pretalx_state,
        }

        submission, created = Submission.objects.get_or_create(
            event=event,
            pretalx_id=code,
            defaults=defaults,
        )

        if not created:
            for key, value in defaults.items():
                setattr(submission, key, value)
            submission.save()
            updated_count += 1
        else:
            created_count += 1

        # Sync speakers
        speaker_objects = []
        for speaker_data in data.get("speakers", []):
            if isinstance(speaker_data, dict):
                speaker_code = speaker_data.get("code", "")
                speaker_name = speaker_data.get("name", "")
                speaker_email = speaker_data.get("email", "") or ""
            else:
                speaker_code = str(speaker_data)
                speaker_name = str(speaker_data)
                speaker_email = ""
            if speaker_code:
                defaults = {"name": speaker_name}
                if speaker_email:
                    defaults["email"] = speaker_email
                speaker, _ = Speaker.objects.update_or_create(
                    pretalx_code=speaker_code,
                    defaults=defaults,
                )
                speaker_objects.append(speaker)
        submission.speakers.set(speaker_objects)

        # Sync tags
        tag_objects = []
        for tag_data in data.get("tags", []):
            if isinstance(tag_data, dict):
                tag_name = tag_data.get("tag", "")
                tag_id = str(tag_data.get("id", ""))
            else:
                tag_name = str(tag_data)
                tag_id = None
            if tag_name:
                tag, _ = Tag.objects.update_or_create(
                    name=tag_name,
                    defaults={"pretalx_id": tag_id} if tag_id else {},
                )
                tag_objects.append(tag)
        submission.tags.set(tag_objects)

    # Sync reviews
    reviews_data = get_reviews(event.pretalx_slug, event.pretalx_token)
    submission_map = {s.pretalx_id: s for s in Submission.objects.filter(event=event)}

    reviews_created = 0
    reviews_updated = 0
    reviews_skipped = 0

    for review_data in reviews_data:
        review_id = review_data.get("id")
        submission_code = review_data.get("submission")
        submission_obj = submission_map.get(submission_code)
        if not submission_obj:
            reviews_skipped += 1
            continue

        score = None
        raw_score = review_data.get("score")
        if raw_score is not None:
            try:
                score = Decimal(str(raw_score))
            except (InvalidOperation, ValueError):
                pass

        defaults = {
            "submission": submission_obj,
            "reviewer_name": review_data.get("user") or "",
            "score": score,
            "notes": review_data.get("text") or "",
        }

        _, created = Review.objects.update_or_create(
            pretalx_review_id=review_id,
            defaults=defaults,
        )
        if created:
            reviews_created += 1
        else:
            reviews_updated += 1

    summary = {
        "submissions_total": len(submissions_data),
        "submissions_created": created_count,
        "submissions_updated": updated_count,
        "reviews_total": len(reviews_data),
        "reviews_created": reviews_created,
        "reviews_updated": reviews_updated,
        "reviews_skipped": reviews_skipped,
    }

    logger.info("Sync complete for %s: %s", event_slug, summary)
    return summary


def _extract_track_name(track):
    """Extract track name from expanded track object or plain value."""
    if track is None:
        return ""
    if isinstance(track, dict):
        name = track.get("name", "")
        if isinstance(name, dict):
            return name.get("en", "") or next(iter(name.values()), "")
        return str(name)
    return str(track)
