# accounts/auth_backend.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

Utilisateur = get_user_model()

class ActiveMagasinBackend(ModelBackend):
    """
    Autorise la connexion seulement si l'utilisateur et son magasin sont actifs.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = Utilisateur.objects.get(username=username)

            if not user.check_password(password):
                return None

            if not user.is_active:
                return None

            if hasattr(user, "magasin") and user.magasin and not user.magasin.actif:
                return None

            return user

        except Utilisateur.DoesNotExist:
            return None