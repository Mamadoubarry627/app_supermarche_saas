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