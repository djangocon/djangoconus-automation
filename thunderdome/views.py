from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from .models import Event, Submission, Tag


@staff_member_required
def submissions_view(request: HttpRequest) -> HttpResponse:
    submissions = Submission.objects.annotate(
        annotated_review_count=Count("reviews", filter=~Q(reviews__score__isnull=True)),
        annotated_review_mean=Avg("reviews__score"),
    ).prefetch_related("speakers", "tags")

    # Text search (title and speaker name)
    search = request.GET.get("q", "").strip()
    if search:
        submissions = submissions.filter(Q(title__icontains=search) | Q(speakers__name__icontains=search)).distinct()

    # Exclude withdrawn from pretalx by default
    pretalx_state = request.GET.get("pretalx_state")
    if pretalx_state:
        submissions = submissions.filter(pretalx_state=pretalx_state)
    else:
        submissions = submissions.exclude(pretalx_state="withdrawn")

    # Duration filter
    duration = request.GET.get("duration")
    if duration:
        submissions = submissions.filter(duration=duration)

    # Tag filter (supports multiple tags)
    tag_ids = request.GET.getlist("tags")
    if tag_ids:
        for tag_id in tag_ids:
            submissions = submissions.filter(tags__pk=tag_id)
        submissions = submissions.distinct()

    # Thunderdome decision filter
    state = request.GET.get("state")
    if state:
        submissions = submissions.filter(state=state)

    # Sorting
    SORT_OPTIONS = {
        "title": "title",
        "-title": "-title",
        "id": "pretalx_id",
        "-id": "-pretalx_id",
        "duration": "duration",
        "-duration": "-duration",
        "reviews": "annotated_review_count",
        "-reviews": "-annotated_review_count",
        "mean": "annotated_review_mean",
        "-mean": "-annotated_review_mean",
    }
    sort = request.GET.get("sort", "-mean")
    order_field = SORT_OPTIONS.get(sort, "-annotated_review_mean")
    submissions = submissions.order_by(order_field, "title")

    # Decision stats
    state_counts = {}
    for value, label in Submission.STATE_CHOICES:
        state_counts[value] = {"label": label, "count": submissions.filter(state=value).count()}
    total_count = submissions.count()

    context = {
        "submissions": submissions,
        "states": Submission.STATE_CHOICES,
        "pretalx_states": Submission.PRETALX_STATE_CHOICES,
        "tags": Tag.objects.all(),
        "state_counts": state_counts,
        "total_count": total_count,
        "current_search": search,
        "current_duration": duration or "",
        "current_pretalx_state": pretalx_state or "",
        "current_state": state or "",
        "current_tags": [int(t) for t in tag_ids if t.isdigit()],
        "current_sort": sort,
    }

    if request.headers.get("HX-Request"):
        return render(request, "thunderdome/_submissions_table.html", context)

    return render(request, "thunderdome/submissions.html", context)


@staff_member_required
def submission_detail_view(request: HttpRequest, pretalx_id: str) -> HttpResponse:
    submission = get_object_or_404(
        Submission.objects.prefetch_related("speakers", "tags", "reviews__user"),
        pretalx_id=pretalx_id,
    )
    context = {"submission": submission}
    return render(request, "thunderdome/_submission_detail.html", context)


@staff_member_required
def submission_page_view(request: HttpRequest, pretalx_id: str) -> HttpResponse:
    submission = get_object_or_404(
        Submission.objects.prefetch_related("speakers", "tags", "reviews__user"),
        pretalx_id=pretalx_id,
    )
    context = {"submission": submission}
    return render(request, "thunderdome/submission_page.html", context)


@staff_member_required
def submission_set_state_view(request: HttpRequest, pk: int) -> HttpResponse:
    submission = get_object_or_404(Submission, pk=pk)
    new_state = request.POST.get("state", "")

    valid_states = {choice[0] for choice in Submission.STATE_CHOICES}
    if new_state in valid_states:
        submission.state = new_state
        submission.save(update_fields=["state"])

    submission = (
        Submission.objects.annotate(
            annotated_review_count=Count("reviews", filter=~Q(reviews__score__isnull=True)),
            annotated_review_mean=Avg("reviews__score"),
        )
        .prefetch_related("speakers", "tags")
        .get(pk=pk)
    )

    context = {"submission": submission}
    return render(request, "thunderdome/_submission_row.html", context)


@staff_member_required
@require_POST
def bulk_set_state_view(request: HttpRequest) -> HttpResponse:
    selected_pks = request.POST.getlist("selected")
    new_state = request.POST.get("bulk_state", "")

    valid_states = {choice[0] for choice in Submission.STATE_CHOICES}
    if not selected_pks:
        messages.error(request, "No submissions selected.")
    elif new_state not in valid_states:
        messages.error(request, "Please select a decision.")
    else:
        count = Submission.objects.filter(pk__in=selected_pks).update(state=new_state)
        label = dict(Submission.STATE_CHOICES).get(new_state, new_state)
        messages.success(request, f"Updated {count} submission(s) to {label}.")

    return redirect("thunderdome_submissions")


@staff_member_required
@require_POST
def sync_from_pretalx_view(request: HttpRequest) -> HttpResponse:
    events = Event.objects.exclude(pretalx_token="")
    if not events.exists():
        messages.error(request, "No events with pretalx tokens configured.")
        return redirect("thunderdome_submissions")

    for event in events:
        async_task("thunderdome.sync.sync_event", event.pretalx_slug)

    messages.success(request, f"Sync queued for {events.count()} event(s). Data will update shortly.")
    return redirect("thunderdome_submissions")
