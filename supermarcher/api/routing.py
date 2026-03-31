# supermarcher/api/routing.py
from django.urls import re_path
from .consumers import PanierConsumer

websocket_urlpatterns = [
    re_path(r"ws/panier/(?P<user_id>\d+)/$", PanierConsumer.as_asgi()),
]