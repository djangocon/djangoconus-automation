from django.contrib import admin
from django.urls import include, path

from config import __version__
from config.views import email_preview_detail_view, email_preview_index_view, homepage_view
from thunderdome.views import (
    bulk_set_state_view,
    grants_view,
    submission_detail_view,
    submission_page_view,
    submission_set_state_view,
    submissions_view,
    sync_from_pretalx_view,
)
from tickets.views import (
    attendee_email_preview_view,
    claim_ticket_view,
    create_tickets_view,
    online_attendees_view,
    ticket_emails_view,
    tickets_info,
    tickets_list_view,
)
from titowebhooks.views import (
    speakers_report_view,
    sponsors_report_view,
    sprint_tickets_view,
    tito_sales_dashboard_view,
    tito_sync_tickets_view,
    tito_sync_view,
    tito_webhook,
    volunteer_interest_view,
)

admin_header = f"DjangoCon US Automation v{__version__}"
admin.site.enable_nav_sidebar = False
admin.site.site_header = admin_header
admin.site.site_title = admin_header

urlpatterns = [
    path("health/", include("health_check.urls")),
    path("", homepage_view, name="home"),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("staff/emails/", email_preview_index_view, name="email_previews"),
    path("staff/emails/<slug:slug>/", email_preview_detail_view, name="email_preview"),
    path("titowebhook/", tito_webhook),
    path("tickets/", tickets_info, name="tickets_info"),
    path("tickets/create/", create_tickets_view, name="create_tickets"),
    path("tickets/list/", tickets_list_view, name="tickets_list"),
    path("tickets/claim/", claim_ticket_view, name="claim_ticket"),
    path("tickets/attendees/", online_attendees_view, name="online_attendees"),
    path("tickets/attendees/<int:pk>/email/", attendee_email_preview_view, name="attendee_email_preview"),
    path("tickets/emails/", ticket_emails_view, name="ticket_emails"),
    path("sprints/tickets/", sprint_tickets_view, name="sprint_tickets"),
    path("reports/speakers.csv", speakers_report_view, name="report_speakers"),
    path("reports/sponsors.csv", sponsors_report_view, name="report_sponsors"),
    path("tito/sales/", tito_sales_dashboard_view, name="tito_sales_dashboard"),
    path("tito/volunteer-interest/", volunteer_interest_view, name="volunteer_interest"),
    path("tito/sync/", tito_sync_view, name="tito_sync"),
    path("tito/sync/tickets/", tito_sync_tickets_view, name="tito_sync_tickets"),
    path("thunderdome/", submissions_view, name="thunderdome_submissions"),
    path("thunderdome/bulk-state/", bulk_set_state_view, name="thunderdome_bulk_state"),
    path("thunderdome/sync/", sync_from_pretalx_view, name="thunderdome_sync"),
    path("thunderdome/grants/", grants_view, name="thunderdome_grants"),
    path("thunderdome/<int:pk>/set-state/", submission_set_state_view, name="thunderdome_submission_set_state"),
    path("thunderdome/<str:pretalx_id>/", submission_page_view, name="thunderdome_submission_page"),
    path("thunderdome/<str:pretalx_id>/modal/", submission_detail_view, name="thunderdome_submission_detail"),
    path("travel-safety/", include("travel_safety.urls")),
    path("volunteers/", include("volunteers.urls")),
]
