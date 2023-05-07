from apiron import Endpoint
from apiron import JsonEndpoint
from apiron import Service


class Sendy(Service):
    domain = "https://emails.djangocon.us/sendy"

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
