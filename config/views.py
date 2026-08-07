from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from config.emails import EMAIL_PREVIEWS, get_preview


def homepage_view(request: HttpRequest) -> HttpResponse:
    return render(request, "homepage.html")


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
