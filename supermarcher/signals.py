from .middleware import get_request
from .models import AuditLog


def log_action(action, modele, utilisateur=None, objet_id=None, description="", extra=None):

    req = get_request()

    user = utilisateur or getattr(req, "user", None)

    if not user or not hasattr(user, "is_authenticated") or not user.is_authenticated:
        user = None

    ip = getattr(req, "ip", None)
    ua = getattr(req, "ua", "")
    url = getattr(req, "url", "")

    # =========================
    # 🔐 LOGIN CONTEXT
    # =========================
    login_status = None

    if extra:
        login_status = extra.get("login_status")

    # =========================
    # 💾 CREATE LOG
    # =========================
    AuditLog.objects.create(
        utilisateur=user,
        action=action,
        modele=modele,
        objet_id=str(objet_id) if objet_id else None,
        description=description,
        ip_address=ip,
        user_agent=ua,
        url=url,
        login_status=login_status
    )
    
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Magasin, ThemeMagasin

@receiver(post_save, sender=Magasin)
def create_theme(sender, instance, created, **kwargs):
    if created:
        ThemeMagasin.objects.create(
            magasin=instance,
            couleur_principale="#1324db",
            mode_sombre=False
        )