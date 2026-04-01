import threading
#supermarcher/middleware.py
_request = threading.local()

class CurrentRequestMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _request.user = request.user
        _request.ip = self.get_client_ip(request)
        _request.ua = request.META.get("HTTP_USER_AGENT", "")
        _request.url = request.path

        response = self.get_response(request)
        return response

    def get_client_ip(self, request):
        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0]
        return request.META.get("REMOTE_ADDR")


def get_request():
    return _request