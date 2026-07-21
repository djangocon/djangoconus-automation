from django.urls import path

from . import views

app_name = "volunteers"

urlpatterns = [
    path("", views.shift_list_view, name="shifts"),
    path("mine/", views.my_shifts_view, name="my_shifts"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("dashboard/sync/", views.sync_schedule_view, name="sync_schedule"),
    path("volunteers/", views.volunteers_list_view, name="volunteers_list"),
    path("shift/<int:pk>/signup/", views.signup_view, name="signup"),
    path("shift/<int:pk>/cancel/", views.cancel_view, name="cancel"),
    path("calendar/<uuid:token>.ics", views.calendar_feed, name="calendar"),
]
