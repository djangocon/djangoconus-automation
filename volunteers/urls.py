from django.urls import path

from . import views

app_name = "volunteers"

urlpatterns = [
    path("", views.shift_list_view, name="shifts"),
    path("mine/", views.my_shifts_view, name="my_shifts"),
    path("mine/contact/", views.update_contact_view, name="update_contact"),
    path("mine/name/", views.update_name_view, name="update_name"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("dashboard/schedule-changes/", views.schedule_changes_view, name="schedule_changes"),
    path("dashboard/emails.csv", views.export_volunteers_view, name="export_volunteers"),
    path("dashboard/merge/", views.merge_shifts_view, name="merge_shifts"),
    path("dashboard/split/<int:pk>/", views.split_shift_view, name="split_shift"),
    path("dashboard/delete/<int:pk>/", views.delete_shift_view, name="delete_shift"),
    path("volunteers/", views.volunteers_list_view, name="volunteers_list"),
    path("shift/<int:pk>/signup/", views.signup_view, name="signup"),
    path("shift/<int:pk>/cancel/", views.cancel_view, name="cancel"),
    path("calendar/<uuid:token>.ics", views.calendar_feed, name="calendar"),
]
