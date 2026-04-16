from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from config import __version__
from thunderdome.views import (
    bulk_set_state_view,
    grants_view,
    submission_detail_view,
    submission_page_view,
    submission_set_state_view,
    submissions_view,
    sync_from_pretalx_view,
)
from tickets.views import claim_ticket_view, create_tickets_view, tickets_info, tickets_list_view
from titowebhooks.views import sprint_tickets_view, tito_webhook

admin_header = f"DjangoCon US Automation v{__version__}"
admin.site.enable_nav_sidebar = False
admin.site.site_header = admin_header
admin.site.site_title = admin_header

urlpatterns = [
    path("health/", include("health_check.urls")),
    path(
        "",
        TemplateView.as_view(template_name="homepage.html"),
        name="home",
    ),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("titowebhook/", tito_webhook),
    path("tickets/", tickets_info, name="tickets_info"),
    path("tickets/create/", create_tickets_view, name="create_tickets"),
    path("tickets/list/", tickets_list_view, name="tickets_list"),
    path("tickets/claim/", claim_ticket_view, name="claim_ticket"),
    path("sprints/tickets/", sprint_tickets_view, name="sprint_tickets"),
    path("thunderdome/", submissions_view, name="thunderdome_submissions"),
    path("thunderdome/bulk-state/", bulk_set_state_view, name="thunderdome_bulk_state"),
    path("thunderdome/sync/", sync_from_pretalx_view, name="thunderdome_sync"),
    path("thunderdome/grants/", grants_view, name="thunderdome_grants"),
    path("thunderdome/<int:pk>/set-state/", submission_set_state_view, name="thunderdome_submission_set_state"),
    path("thunderdome/<str:pretalx_id>/", submission_page_view, name="thunderdome_submission_page"),
    path("thunderdome/<str:pretalx_id>/modal/", submission_detail_view, name="thunderdome_submission_detail"),
    path("travel-safety/", include("travel_safety.urls")),
]
