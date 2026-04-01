from django.shortcuts import redirect
#accounts/middleware.py
class CheckUserAndMagasinActifMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        allowed_paths = [
            '/inactive/',
            '/connexion/',
            '/deconnexion/',
            '/static/',  # pour les fichiers statiques
            '/media/',   # pour les fichiers médias
            '/admin/',
            '/parametres/',
            '/toggle-dark-mode/',
        ]

        if not any(request.path.startswith(path) for path in allowed_paths):
            if request.user.is_authenticated:

                if not request.user.is_active:
                    return redirect('/inactive/')

                magasin = getattr(request.user, "magasin", None)

                if magasin and not magasin.actif:
                    return redirect('/inactive/')

        response = self.get_response(request)
        return response

    
# accounts/middleware.py
import jwt
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware

@database_sync_to_async
def get_user(user_id):
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import AnonymousUser

    User = get_user_model()
    try:
        return User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return AnonymousUser()
    
class JWTAuthMiddleware(BaseMiddleware):
    """Middleware Channels pour authentification JWT via query string ou header"""

    async def __call__(self, scope, receive, send):
        from django.contrib.auth.models import AnonymousUser
        # ✅ Import retardé de SimpleJWT
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        from django.conf import settings

        scope['user'] = AnonymousUser()
        token = None

        # Récupération token depuis query string
        qs = parse_qs(scope.get("query_string", b"").decode())
        if "token" in qs:
            token = qs["token"][0]
            print(f"Token trouvé dans query string: {token}")

        # Sinon depuis header Authorization
        if not token:
            headers = dict(scope.get("headers", []))
            auth = headers.get(b'authorization', None)
            if auth:
                auth_str = auth.decode()
                if auth_str.startswith("Bearer "):
                    token = auth_str.split(" ")[1]
                    print(f"Token trouvé dans header: {token}")
                print(f"Header Authorization: {auth_str}")

        # Vérifie et décode le token
        if token:
            try:
                UntypedToken(token)  # valide le token
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get('user_id') or payload.get('sub')
                if user_id:
                    scope['user'] = await get_user(user_id)
                    print(f"Utilisateur authentifié: {scope['user']}")
            except (InvalidToken, TokenError, jwt.DecodeError, KeyError):
                scope['user'] = AnonymousUser()
                print("Erreur d'authentification avec le token.")
        return await super().__call__(scope, receive, send)
    