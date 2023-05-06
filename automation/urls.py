from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from automation import __version__
from titowebhooks.views import tito_webhook

admin_header = f"DjangoCon US Automation v{__version__}"
admin.site.enable_nav_sidebar = False
admin.site.site_header = admin_header
admin.site.site_title = admin_header

urlpatterns = [
    path("", TemplateView.as_view(template_name="homepage.html")),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("titowebhook/", tito_webhook),
]
