from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from config.emails import EMAIL_PREVIEWS, get_preview
from volunteers.permissions import can_view_volunteer_interest


def _is_staff(user) -> bool:
    return user.is_active and user.is_staff


# The CSV exports, listed in one place so the homepage and any future index stay
# in step with each other. Each URL downloads a file directly — no page in
# between — and every report shares the columns in titowebhooks.reports.
#
# ``can_view`` mirrors the decorator on the view itself. The reports don't all
# share one rule — the volunteer interest report is superusers and volunteer
# chairs, not staff at large — so listing a report someone can't open would just
# hand them a 403.
REPORTS = [
    {
        "label": "Online attendees",
        "description": "Who bought an online ticket, their link, and whether we've emailed it.",
        "url_name": "online_attendees",
        "query": "format=csv",
        "can_view": _is_staff,
    },
    {
        "label": "Speakers",
        "description": "Everyone holding a Speaker ticket.",
        "url_name": "report_speakers",
        "can_view": _is_staff,
    },
    {
        "label": "Sponsors",
        "description": "Everyone holding a Sponsor ticket, in person or online.",
        "url_name": "report_sponsors",
        "can_view": _is_staff,
    },
    {
        "label": "Sprint tickets",
        "description": "In-person sprinters for this year, by day.",
        "url_name": "sprint_tickets",
        "query": "format=csv",
        "can_view": _is_staff,
    },
    {
        "label": "Sprint tickets — historical",
        "description": "Sprinters across the last few conference years.",
        "url_name": "sprint_tickets",
        "query": "scope=historical&format=csv",
        "can_view": _is_staff,
    },
    {
        "label": "Volunteer interest",
        "description": "Attendees who said yes to volunteering on their ticket.",
        "url_name": "volunteer_interest",
        "query": "format=csv",
        "can_view": can_view_volunteer_interest,
    },
]


def available_reports(user) -> list[dict]:
    """The reports ``user`` may actually download, with their URLs built."""
    reports = []
    for report in REPORTS:
        if not report["can_view"](user):
            continue
        url = reverse(report["url_name"])
        query = report.get("query")
        reports.append({**report, "url": f"{url}?{query}" if query else url})
    return reports


def homepage_view(request: HttpRequest) -> HttpResponse:
    # The views enforce their own access; this only decides what to link.
    reports = available_reports(request.user) if request.user.is_authenticated else []
    return render(request, "homepage.html", {"reports": reports})


@staff_member_required
def email_preview_index_view(request: HttpRequest) -> HttpResponse:
    return render(request, "staff/email_preview_index.html", {"previews": EMAIL_PREVIEWS})


@staff_member_required
def email_preview_detail_view(request: HttpRequest, slug: str) -> HttpResponse:
    preview = get_preview(slug)
    if preview is None:
        raise Http404(f"No email preview named {slug!r}")

    rendered = preview.render(request)

    # ?part=html serves the HTML body alone, so the iframe below can show it at
    # full width and staff can open it in a tab to test in a real client.
    if request.GET.get("part") == "html":
        if not rendered.html_body:
            raise Http404("This email has no HTML part")
        return HttpResponse(rendered.html_body)

    # Rich and plain are the two things a client might show, so the page shows
    # one at a time rather than stacking them. Text-only emails have no rich
    # version to fall back from.
    view = request.GET.get("view")
    if view not in {"rich", "text"}:
        view = "rich" if rendered.html_body else "text"
    if view == "rich" and not rendered.html_body:
        view = "text"

    return render(
        request,
        "staff/email_preview_detail.html",
        {"preview": preview, "rendered": rendered, "previews": EMAIL_PREVIEWS, "view": view},
    )
