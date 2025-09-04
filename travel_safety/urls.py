from django.urls import path
from . import views

app_name = 'travel_safety'

urlpatterns = [
    path('', views.TravelRegistrationView.as_view(), name='register'),
    path('success/', views.RegistrationSuccessView.as_view(), name='success'),
]