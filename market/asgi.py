"""
ASGI config for market project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

# il ne pas dans supermarcher mais dans market si ça ne marche pas il faut que je le déplacer dans supermarcher?
# il est dans meme emplacement que settings.py et wsgi.py
# /asgi.py

# market/asgi.py
import os
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from accounts.middleware import JWTAuthMiddleware
from supermarcher.api import routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "market.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddleware(
        URLRouter(routing.websocket_urlpatterns)
    ),
})