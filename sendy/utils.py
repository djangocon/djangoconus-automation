from apiron import Endpoint, JsonEndpoint, Service
from django.conf import settings


class Sendy(Service):
    domain = settings.SENDY_ENDPONT_URL

    brands = JsonEndpoint(
        path="/api/brands/get-brands.php",
        default_method="POST",
    )
    lists = JsonEndpoint(
        path="/api/lists/get-lists.php",
        default_method="POST",
    )
    subscribe = Endpoint(
        path="/subscribe",
        default_method="POST",
    )
