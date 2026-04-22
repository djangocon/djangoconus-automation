from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def homepage_view(request: HttpRequest) -> HttpResponse:
    return render(request, "homepage.html")
