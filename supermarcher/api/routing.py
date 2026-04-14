# supermarcher/api/routing.py
from django.urls import re_path
from .consumers import PanierConsumer
from .consumers import ThemeConsumer

websocket_urlpatterns = [
    re_path(r"ws/panier/(?P<user_id>\d+)/$", PanierConsumer.as_asgi()),
    re_path(r'ws/theme/(?P<magasin_id>\d+)/$', ThemeConsumer.as_asgi()),
]

