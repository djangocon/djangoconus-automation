from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from titowebhooks.views import tito_webhook

urlpatterns = [
    path("", TemplateView.as_view(template_name="homepage.html")),
    path("accounts/", include("allauth.urls")),
    path("admin/", admin.site.urls),
    path("titowebhook/", tito_webhook),
]
