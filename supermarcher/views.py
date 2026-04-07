from multiprocessing import context
from time import time
from urllib import request
from django.db.models import Count, DurationField, ExpressionWrapper
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

from supermarcher.signals import log_action
from supermarcher.utils import theme
from .models import Categorie, Magasin, Utilisateur
from .forms import AchatForm, FournisseurForm, ModifierMagasinForm, UtilisateurForm, ConnexionForm, VenteForm

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from supermarcher import models


def redirect_home_by_role(user):
    """
    Redirige l'utilisateur vers la page adaptée selon son rôle.
    """
    if user.role == 'SUPERADMIN':
        return redirect('dashboard_superadmin')  
    elif user.role == 'GERANT':
        return redirect('dashboard_gerant')  
    elif user.role == 'CAISSIER':
        return redirect('dashboard_gerant')  
    else:
        return redirect('connexion')

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def get_lock_delay(attempts):
    """
    1-3 essais : pas de blocage
    4e : 1 min
    5e : 2 min
    6e : 4 min
    7e : 8 min ...
    """
    if attempts <= 3:
        return 0
    return 60 * (2 ** (attempts - 4))
    
# =================================
# CONNEXION
# =================================
import time
from django.contrib.auth import authenticate, login
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils.timezone import now
#from django_ratelimit.decorators import ratelimit
from .models import Utilisateur
from .forms import ConnexionForm
from .signals import log_action

#@ratelimit(key="ip", rate="5/m", block=True)
def connexion(request):

    if request.user.is_authenticated:
        return redirect_home_by_role(request.user)

    form = ConnexionForm(request.POST or None)

    if request.method != "POST" or not form.is_valid():
        return render(request, "connexion.html", {
            "form": form,
            "lock_until": 0
        })

    username = form.cleaned_data["username"]
    password = form.cleaned_data["password"]

    ip = get_client_ip(request)

    # =========================
    # 🔐 KEYS
    # =========================
    key_user = f"login_user_{username}_{ip}"
    key_ip = f"login_ip_{ip}"

    user_data = cache.get(key_user, {"count": 0, "block_until": 0})
    ip_data = cache.get(key_ip, {"count": 0, "block_until": 0})

    now_ts = now().timestamp()

    # =========================
    # ⛔ BLOCK CHECK (IP GLOBAL)
    # =========================
    if ip_data.get("block_until", 0) > now_ts:
        return render(request, "connexion.html", {
            "form": form,
            "lock_until": ip_data["block_until"],
            "error": "Trop de tentatives. IP temporairement bloquée."
        })

    # =========================
    # 👤 USER CHECK
    # =========================
    user_obj = Utilisateur.objects.filter(username=username).first()

    # =========================
    # 🛡️ BUSINESS RULES
    # =========================
    blocked = False
    error_msg = None

    if user_obj:

        if not user_obj.is_active:
            blocked = True
            error_msg = "Compte désactivé."

        elif user_obj.role != "SUPERADMIN":

            if not user_obj.magasin:
                blocked = True
                error_msg = "Aucun magasin associé."

            elif not user_obj.magasin.actif:
                blocked = True
                error_msg = "Magasin désactivé."

    # =========================
    # 🚫 BUSINESS BLOCK
    # =========================
    if blocked:

        transaction.on_commit(lambda: log_action(
            action="LOGIN_BLOCKED_BUSINESS_RULE",
            modele="AUTH",
            utilisateur=user_obj,
            objet_id=user_obj.id if user_obj else None,
            description=f"Blocage login username={username} reason={error_msg}"
        ))

        return render(request, "connexion.html", {
            "form": form,
            "error": error_msg,
            "lock_until": ip_data.get("block_until", 0)
        })

    # =========================
    # 🔐 AUTH
    # =========================
    user = authenticate(request, username=username, password=password)

    # =========================
    # 🟢 SUCCESS LOGIN
    # =========================
    if user is not None:

        cache.delete(key_user)
        cache.delete(key_ip)

        login(request, user)

        transaction.on_commit(lambda: log_action(
            action="LOGIN_SUCCESS",
            modele="AUTH",
            utilisateur=user,
            objet_id=user.id,
            description=f"Connexion réussie ({user.username})"
        ))

        return redirect_home_by_role(user)

    # =========================
    # 🔴 FAILED LOGIN
    # =========================
    user_data["count"] += 1
    ip_data["count"] += 1

    delay_user = get_lock_delay(user_data["count"])
    delay_ip = get_lock_delay(ip_data["count"])

    # prend le plus fort blocage
    delay = max(delay_user, delay_ip)

    if delay > 0:
        block_until = now_ts + delay
        user_data["block_until"] = block_until
        ip_data["block_until"] = block_until
    else:
        user_data["block_until"] = 0
        ip_data["block_until"] = 0

    cache.set(key_user, user_data, timeout=3600)
    cache.set(key_ip, ip_data, timeout=3600)

    # =========================
    # 🧠 LOGS
    # =========================
    if user_obj:

        transaction.on_commit(lambda: log_action(
            action="LOGIN_FAILED_PASSWORD",
            modele="AUTH",
            utilisateur=user_obj,
            objet_id=user_obj.id,
            description=f"Mauvais mot de passe username={username}"
        ))

    else:

        transaction.on_commit(lambda: log_action(
            action="LOGIN_FAILED_UNKNOWN",
            modele="AUTH",
            utilisateur=None,
            objet_id=None,
            description=f"Tentative inconnue username={username} ip={ip}"
        ))

    # =========================
    # ❌ RESPONSE
    # =========================
    form.add_error(None, "Nom d'utilisateur ou mot de passe incorrect.")

    return render(request, "connexion.html", {
        "form": form,
        "lock_until": max(
            user_data.get("block_until", 0),
            ip_data.get("block_until", 0)
        )
    })
    
    
from django.shortcuts import render

def inactive_user_view(request):
    reason = request.GET.get('reason', 'user')

    if reason == 'magasin':
        message = "Votre magasin est actuellement désactivé. Veuillez contacter l’administrateur."
        titre = "Magasin inactif"
    else:
        message = "Votre compte utilisateur est actuellement désactivé. Veuillez contacter l’administrateur."
        titre = "Compte inactif"

    return render(request, 'accounts/inactive_user.html', {
        'titre': titre,
        'message': message,
    })
    
# =================================
# DECONNEXION
# =================================
@login_required
def deconnexion(request):
    log_action(
        action="LOGOUT",
        modele="Utilisateur",
        objet_id=request.user.id,
        description="Déconnexion utilisateur"
    )
    logout(request)
    return redirect('connexion')

# ===============================
# DASHBOARD SUPERADMIN
# ===============================

from functools import wraps
from django.core.exceptions import PermissionDenied

def superadmin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied()

        # Défense supplémentaire (évite erreurs si user mal formé)
        if not hasattr(request.user, "role") or request.user.role != "SUPERADMIN":
            raise PermissionDenied()

        return view_func(request, *args, **kwargs)
    return _wrapped

from django.core.paginator import Paginator
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
import logging
from django.db.models import Count, Q, Sum, F

logger = logging.getLogger(__name__)


@login_required
def dashboard_superadmin(request):

    # 🔐 AUTH STRICT
    if request.user.role != "SUPERADMIN":
        logger.warning(
            f"[SECURITY] accès refusé dashboard_superadmin par {request.user.username}"
        )
        raise PermissionDenied("Accès refusé")

    # 📊 STATS
    total_magasins = Magasin.objects.count()
    magasins_actifs = Magasin.objects.filter(actif=True).count()
    magasins_inactifs = Magasin.objects.filter(actif=False).count()

    total_gerants = Utilisateur.objects.filter(role="GERANT").count()
    total_caissiers = Utilisateur.objects.filter(role="CAISSIER").count()

    # 🏪 QUERY OPTIMISÉE
    magasins_qs = Magasin.objects.select_related("proprietaire").order_by("-date_creation")

    # 🔢 PAGINATION SAFE
    try:
        page_number = int(request.GET.get("page", 1))
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1

    paginator = Paginator(magasins_qs, 5)
    magasins_page = paginator.get_page(page_number)

    # 🔥 optimisation (évite N+1)
    magasins_ids = [m.id for m in magasins_page]

    produits_counts = Produit.objects.filter(
        magasin_id__in=magasins_ids
    ).values("magasin_id").annotate(total=Count("id"))

    produits_map = {p["magasin_id"]: p["total"] for p in produits_counts}

    for magasin in magasins_page:
        magasin.est_vide = produits_map.get(magasin.id, 0) == 0

    # 🔐 AUDIT LOG
    logger.info(
        f"{request.user.username} a consulté dashboard_superadmin page={page_number}"
    )

    context = {
        "total_magasins": total_magasins,
        "magasins_actifs": magasins_actifs,
        "magasins_inactifs": magasins_inactifs,
        "total_gerants": total_gerants,
        "total_caissiers": total_caissiers,
        "magasins": magasins_page,
    }

    return render(request, "superadmin/dashboard_superadmin.html", context)
    
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)


@login_required
@superadmin_required
def voir_magasin(request, id):

    magasin = get_object_or_404(Magasin, id=id)

    # 🔒 sécurité métier (optionnel mais recommandé)
    if request.user.role != "SUPERADMIN":
        messages.error(request, "Accès interdit ❌")
        raise PermissionDenied()

    # 🔥 Optimisation + sécurité données
    produits = Produit.objects.filter(magasin_id=id)

    nb_produits = produits.count()

    nb_utilisateurs = Utilisateur.objects.filter(
        magasin_id=id
    ).count()

    nb_caissiers = Utilisateur.objects.filter(
        magasin_id=id,
        role="CAISSIER"
    ).count()

    gerant = Utilisateur.objects.filter(
        magasin_id=id,
        role="GERANT"
    ).only("id", "username", "email").first()

    produits_perimes = produits.filter(
        date_expiration__lt=now().date()
    ).count()

    theme = getattr(magasin, "theme", None)

    # 🔐 audit log
    logger.info(
        f"{request.user.username} a consulté le magasin {magasin.id}"
    )

    context = {
        "magasin": magasin,
        "nb_produits": nb_produits,
        "nb_utilisateurs": nb_utilisateurs,
        "nb_caissiers": nb_caissiers,
        "gerant": gerant,
        "produits_perimes": produits_perimes,
        "theme": theme,
    }

    return render(request, "superadmin/voir_magasin.html", context)

from django.shortcuts import redirect
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@login_required
@superadmin_required
def toggle_magasin(request, id):

    magasin = get_object_or_404(Magasin, id=id)

    try:
        with transaction.atomic():

            magasin.actif = not magasin.actif
            magasin.save()

            logger.warning(
                f"[SECURITY] {request.user.username} a modifié l'état du magasin {magasin.id} → actif={magasin.actif}"
            )

            messages.success(request, "État du magasin mis à jour ✅")

    except Exception:
        logger.error("Erreur toggle magasin", exc_info=True)
        messages.error(request, "Erreur lors de l'opération ❌")

    return redirect("dashboard_superadmin")

@login_required
@superadmin_required
@require_POST
def supprimer_magasin(request, id):

    magasin = get_object_or_404(Magasin, id=id)

    # 🔒 protection business critique
    if magasin.produit_set.exists() or magasin.commande_set.exists():
        messages.error(
            request,
            "Impossible de supprimer ce magasin : données existantes."
        )
        return redirect("dashboard_superadmin")

    try:
        with transaction.atomic():

            nom = magasin.nom

            magasin.delete()

            logger.warning(
                f"[SECURITY] {request.user.username} a supprimé le magasin {nom}"
            )

            messages.success(request, "Magasin supprimé avec succès ✅")

    except Exception:
        logger.error("Erreur suppression magasin", exc_info=True)
        messages.error(request, "Erreur lors de la suppression ❌")

    return redirect("dashboard_superadmin")

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import CreationMagasinForm
from .models import Utilisateur
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.contrib import messages
from django.db import transaction, IntegrityError
import logging

logger = logging.getLogger(__name__)

@login_required
@superadmin_required
def creer_magasin(request):

    if request.method == "POST":
        form = CreationMagasinForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():

                    username = form.cleaned_data["gerant_username"].strip()
                    email = form.cleaned_data["gerant_email"].strip()
                    password = form.cleaned_data["gerant_password"]

                    # 🔒 Vérifications fortes
                    if Utilisateur.objects.filter(username=username).exists():
                        form.add_error("gerant_username", "Nom d'utilisateur déjà utilisé")
                        raise ValueError("username_exists")

                    if Utilisateur.objects.filter(email=email).exists():
                        form.add_error("gerant_email", "Email déjà utilisé")
                        raise ValueError("email_exists")

                    # 🔒 Création utilisateur sécurisée
                    gerant = Utilisateur.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        role="GERANT"
                    )

                    # 🔒 Création magasin
                    magasin = form.save(commit=False)
                    magasin.proprietaire = gerant
                    magasin.save()

                    # 🔒 Liaison
                    gerant.magasin = magasin
                    gerant.save()

                    # ✅ Log audit
                    logger.info(
                        f"[SECURITY] {request.user.username} a créé le magasin {magasin.id} "
                        f"avec le gérant {gerant.username}"
                    )

                    messages.success(request, "Magasin créé avec succès ✅")
                    return redirect("dashboard_superadmin")

            except ValueError:
                # erreurs métier déjà ajoutées au form
                pass

            except IntegrityError:
                logger.warning("Erreur DB lors de la création magasin", exc_info=True)
                messages.error(request, "Erreur base de données. Réessayez.")

            except Exception:
                logger.error("Erreur inattendue", exc_info=True)
                messages.error(request, "Une erreur inattendue est survenue.")

        else:
            messages.error(request, "Formulaire invalide ❌")

    else:
        form = CreationMagasinForm()

    return render(request, "superadmin/creer_magasin.html", {"form": form})

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib import messages
import logging

logger = logging.getLogger(__name__)

@login_required
@superadmin_required
def modifier_magasin(request, id):

    magasin = get_object_or_404(Magasin, id=id)

    if request.method == "POST":
        form = ModifierMagasinForm(request.POST, instance=magasin)

        if form.is_valid():
            try:
                with transaction.atomic():

                    magasin = form.save()

                    logger.info(
                        f"[SECURITY] {request.user.username} a modifié le magasin {magasin.id}"
                    )

                    messages.success(request, "Magasin modifié avec succès ✅")
                    return redirect("dashboard_superadmin")

            except Exception:
                logger.error("Erreur modification magasin", exc_info=True)
                messages.error(request, "Erreur lors de la modification")

        else:
            messages.error(request, "Formulaire invalide ❌")

    else:
        form = ModifierMagasinForm(instance=magasin)

    return render(request, "superadmin/creer_magasin.html", {
        "form": form,
        "magasin": magasin,
        "mode": "modifier"
    })

@login_required
@superadmin_required
def gestion_utilisateurs(request):

    utilisateurs = Utilisateur.objects.all().only(
        "id", "username", "email", "role", "date_creation"
    ).order_by("-date_creation")

    logger.info(f"{request.user.username} a consulté les utilisateurs")

    return render(request, "superadmin/utilisateurs.html", {
        "utilisateurs": utilisateurs
    })
    
from django.core.exceptions import PermissionDenied

@login_required
@superadmin_required
def voir_utilisateur(request, id):

    user = get_object_or_404(
        Utilisateur.objects.only(
            "id", "username", "email", "role", "date_creation"
        ),
        id=id
    )

    logger.info(
        f"{request.user.username} a consulté le profil utilisateur {user.id}"
    )

    return render(request, "superadmin/voir_utilisateur.html", {
        "user_detail": user
    })
    
    
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@login_required
@superadmin_required
def toggle_utilisateur(request, id):

    user = get_object_or_404(Utilisateur, id=id)

    # 🔒 Empêche auto-désactivation
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte ❌")
        raise PermissionDenied()

    # 🔒 Empêche désactivation d’un SUPERADMIN
    if user.role == "SUPERADMIN":
        messages.error(request, "Impossible de modifier un SUPERADMIN ❌")
        raise PermissionDenied()

    try:
        with transaction.atomic():

            user.is_active = not user.is_active
            user.save()

            logger.warning(
                f"[SECURITY] {request.user.username} a changé l'état de l'utilisateur "
                f"{user.username} → is_active={user.is_active}"
            )

            messages.success(request, "Statut utilisateur mis à jour ✅")

    except Exception:
        logger.error("Erreur toggle utilisateur", exc_info=True)
        messages.error(request, "Erreur lors de l'opération ❌")

    return redirect("gestion_utilisateurs")

from django.shortcuts import render, get_object_or_404, redirect
from .models import Utilisateur, Magasin
from django.contrib import messages

# =========================
# AJOUT UTILISATEUR
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@login_required
@superadmin_required
def ajouter_utilisateur(request):

    magasins = Magasin.objects.all()

    if request.method == "POST":
        form = UtilisateurForm(request.POST)

        if form.is_valid():
            try:
                with transaction.atomic():

                    user = form.save(commit=False)

                    # 🔒 sécurité : assignation contrôlée côté serveur
                    user.role = request.POST.get("role", "USER")

                    magasin_id = request.POST.get("magasin")
                    user.magasin = Magasin.objects.filter(id=magasin_id).first()

                    user.is_active = True  # 🔒 force backend (pas POST)

                    user.save()

                    logger.info(
                        f"{request.user.username} a créé l'utilisateur {user.username}"
                    )

                    messages.success(request, "Utilisateur créé avec succès ✅")
                    return redirect("gestion_utilisateurs")

            except Exception:
                logger.error("Erreur création utilisateur", exc_info=True)
                messages.error(request, "Erreur lors de la création ❌")

        else:
            messages.error(request, "Formulaire invalide ❌")

    else:
        form = UtilisateurForm()

    return render(request, "superadmin/form_utilisateur.html", {
        "form": form,
        "magasins": magasins
    })

# =========================
# MODIFIER UTILISATEUR
# =========================
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


@login_required
@superadmin_required
def modifier_utilisateur(request, id):

    user = get_object_or_404(Utilisateur, id=id)
    magasins = Magasin.objects.all()

    if request.method == "POST":
        try:
            with transaction.atomic():

                # 🔒 champs contrôlés serveur (PAS POST brut)
                user.username = request.POST.get("username", user.username).strip()
                user.first_name = request.POST.get("first_name", "").strip()
                user.last_name = request.POST.get("last_name", "").strip()
                user.email = request.POST.get("email", user.email).strip().lower()
                user.telephone = request.POST.get("telephone", user.telephone).strip()

                # 🔥 PROTECTION CRITIQUE : rôle limité
                new_role = request.POST.get("role")

                if new_role == "SUPERADMIN" and request.user.role != "SUPERADMIN":
                    raise PermissionDenied("Action interdite")

                # 🔒 seuls SUPERADMIN peuvent changer rôle
                if request.user.role == "SUPERADMIN":
                    user.role = new_role

                # 🔒 magasin sécurisé
                magasin_id = request.POST.get("magasin")
                user.magasin = Magasin.objects.filter(id=magasin_id).first() if magasin_id else None

                # 🔒 is_active contrôlé
                if request.user.role == "SUPERADMIN":
                    user.is_active = bool(request.POST.get("is_active"))

                user.save()

                logger.info(
                    f"{request.user.username} a modifié l'utilisateur {user.username}"
                )

                messages.success(request, "Utilisateur modifié avec succès ✅")
                return redirect("gestion_utilisateurs")

        except Exception:
            logger.error("Erreur modification utilisateur", exc_info=True)
            messages.error(request, "Erreur lors de la modification ❌")

    return render(request, "superadmin/form_utilisateur.html", {
        "user": user,
        "magasins": magasins
    })
    
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.core.exceptions import PermissionDenied
import logging

logger = logging.getLogger(__name__)


@login_required
@superadmin_required
@require_POST  # 🔒 interdit GET
def supprimer_utilisateur(request, id):

    user = get_object_or_404(Utilisateur, id=id)

    # 🔒 protection auto-suppression
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        raise PermissionDenied()

    # 🔒 protection SUPERADMIN
    if user.role == "SUPERADMIN":
        messages.error(request, "Impossible de supprimer un Super Admin.")
        raise PermissionDenied()

    # 🔒 vérification dépendances métier
    if user.vente.exists() or user.achat.exists() or user.mouvementstock.exists():
        messages.error(
            request,
            "Impossible de supprimer cet utilisateur (historique existant)."
        )
        return redirect("gestion_utilisateurs")

    try:
        with transaction.atomic():

            username = user.username  # pour log

            user.delete()

            logger.warning(
                f"[SECURITY] {request.user.username} a supprimé l'utilisateur {username}"
            )

            messages.success(request, "Utilisateur supprimé avec succès ✅")

    except Exception:
        logger.error("Erreur suppression utilisateur", exc_info=True)
        messages.error(request, "Erreur lors de la suppression ❌")

    return redirect("gestion_utilisateurs")


from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.views.generic import ListView
from .models import AuditLog

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView
from django.utils import timezone
from datetime import datetime
from .models import AuditLog
from django.db.models import Q
from django.db.models import Q
from django.utils import timezone
from datetime import datetime

class AuditLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = AuditLog
    template_name = "superadmin/auditlogs/auditlog_list.html"
    context_object_name = "logs"
    paginate_by = 5

    def test_func(self):
        return self.request.user.is_staff or self.request.user.is_superuser

    def get_queryset(self):

        qs = (
            AuditLog.objects
            .select_related("utilisateur")
            .order_by("-date_action")
        )

        # =========================
        # 🔍 PARAMS
        # =========================
        user_id = self.request.GET.get("user")
        action = self.request.GET.get("action")
        date_from = self.request.GET.get("from")
        date_to = self.request.GET.get("to")
        search = self.request.GET.get("search")

        # =========================
        # 👤 USER FILTER SAFE
        # =========================
        if user_id and user_id.isdigit():
            qs = qs.filter(utilisateur_id=int(user_id))

        # =========================
        # ⚡ ACTION FILTER
        # =========================
        if action:
            qs = qs.filter(action=action)

        # =========================
        # 📅 DATE FILTER SAFE
        # =========================
        try:
            if date_from:
                qs = qs.filter(
                    date_action__date__gte=datetime.strptime(date_from, "%Y-%m-%d").date()
                )

            if date_to:
                qs = qs.filter(
                    date_action__date__lte=datetime.strptime(date_to, "%Y-%m-%d").date()
                )

        except ValueError:
            pass

        # =========================
        # 🔎 GLOBAL SEARCH (SAFETY + LOGIN INTELLIGENT)
        # =========================
        if search:
            qs = qs.filter(
                Q(modele__icontains=search) |
                Q(description__icontains=search) |
                Q(action__icontains=search) |
                Q(ip_address__icontains=search) |
                Q(utilisateur__first_name__icontains=search) |
                Q(utilisateur__last_name__icontains=search) |
                Q(utilisateur__username__icontains=search)
            )

        return qs
    
########################### Fin Superadmin ###################################

#====================================================================
#           PARTIE MAGAGIN
#====================================================================
# ---------------------------
# Liste Produits (gerant)
# ---------------------------

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Produit, Categorie


@login_required
def produits_liste(request):
    magasin = request.user.magasin
    produits = Produit.objects.filter(magasin=magasin)

    # ===== FILTRES =====

    search = request.GET.get("search")
    categorie_id = request.GET.get("categorie")
    prix_min = request.GET.get("prix_min")
    prix_max = request.GET.get("prix_max")
    stock_min = request.GET.get("stock_min")
    actif = request.GET.get("actif")
    alerte = request.GET.get("alerte")
    tri = request.GET.get("tri")

    if search:
        produits = produits.filter(
            Q(nom__icontains=search)
        )

    if categorie_id:
        produits = produits.filter(categorie_id=categorie_id)

    if prix_min:
        produits = produits.filter(prix_vente__gte=prix_min)

    if prix_max:
        produits = produits.filter(prix_vente__lte=prix_max)

    if stock_min:
        produits = produits.filter(quantite_stock__gte=stock_min)

    if actif == "1":
        produits = produits.filter(actif=True)

    if actif == "0":
        produits = produits.filter(actif=False)

    if alerte == "1":
        produits = produits.filter(quantite_stock__lte=models.F('seuil_alerte'))

    # ===== TRI =====
    if tri in ["nom", "-nom", "prix_vente", "-prix_vente", "quantite_stock", "-quantite_stock"]:
        produits = produits.order_by(tri)
    else:
        produits = produits.order_by("nom")

    categories = Categorie.objects.filter(magasin=magasin)

    context = {
        "produits": produits,
        "magasin": magasin,
        "categories": categories,
    }

    return render(request, "gerant/produits_liste.html", context)

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json, time

@login_required
@csrf_exempt
def produit_modifier_ajax(request, produit_id):
    if request.method == "POST":
        magasin = request.user.magasin
        produit = get_object_or_404(Produit, id=produit_id, magasin=magasin)

        try:
            data = json.loads(request.body)
            field = data.get("field")
            value = data.get("value")
        except:
            return JsonResponse({"success": False, "error": "Données invalides"})

        response = {"success": False}

        # ===== Modification de la quantité de stock =====
        if field == "quantite_stock":
            try:
                value = int(value)
                diff = value - produit.quantite_stock

                if diff != 0:
                    # Crée le mouvement d'ajustement avec la différence
                    MouvementStock.objects.create(
                        magasin=magasin,
                        produit=produit,
                        type_mouvement="AJUSTEMENT",
                        quantite=diff,
                        reference=f"AJS-{produit.id}-{int(time.time())}",
                        cree_par=request.user
                    )

                    # Mise à jour du stock du produit
                    produit.quantite_stock = value
                    produit.save()

                response["success"] = True
            except Exception as e:
                response["error"] = str(e)

        # ===== Modification du prix de vente =====
        elif field == "prix_vente":
            try:
                produit.prix_vente = float(value)
                produit.save()
                response["success"] = True
            except Exception as e:
                response["error"] = str(e)

        return JsonResponse(response)

    return JsonResponse({"success": False, "error": "Méthode non autorisée"})


@login_required
def produit_detail(request, pk):
    produit = get_object_or_404(Produit, pk=pk, magasin=request.user.magasin)
    return render(request, "gerant/produit_detail.html", {"produit": produit, "magasin": request.user.magasin})

from .forms import ProduitForm

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import ProduitForm
from .models import Produit

# Ajouter un produit
from django.db import IntegrityError
from django.db import IntegrityError

@login_required
def produit_nouveau(request):
    magasin = request.user.magasin

    if request.method == 'POST':
        form = ProduitForm(request.POST)

        if form.is_valid():
            produit = form.save(commit=False)
            produit.magasin = magasin

            try:
                produit.save()

                log_action(
                    action="CREATE",
                    modele="Produit",
                    objet_id=produit.id,
                    description=f"Création produit {produit.nom}"
                )

                messages.success(request, "Produit ajouté avec succès.")
                return redirect('produits_liste')

            except IntegrityError:
                # 🔥 ERREUR GLOBALE (PAS SKU)
                messages.error(
                    request,
                    "Ce produit existe déjà dans ce magasin. Vérifiez les informations du produit."
                )
    else:
        form = ProduitForm()

    return render(request, 'gerant/produit_form.html', {
        'form': form,
        'magasin': magasin
    })
    
@login_required
def produit_edit(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    magasin = request.user.magasin

    if request.method == 'POST':
        form = ProduitForm(request.POST, instance=produit)

        if form.is_valid():
            try:
                produit = form.save()

                log_action(
                    action="UPDATE",
                    modele="Produit",
                    objet_id=produit.id,
                    description=f"Modification produit {produit.nom}"
                )

                messages.success(request, "Produit modifié avec succès.")
                return redirect('produits_liste')

            except IntegrityError:
                # 🔥 ERREUR GLOBALE
                messages.error(
                    request,
                    "Conflit détecté : ce produit existe déjà (SKU, nom ou code-barres)."
                )
    else:
        form = ProduitForm(instance=produit)

    return render(request, 'gerant/produit_form.html', {
        'form': form,
        'magasin': magasin
    })
    
# Supprimer un produit
def produit_delete(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    if request.method == 'POST':
        log_action(
        action="DELETE",
        modele="Produit",
        objet_id=produit.id,
        description=f"Suppression produit {produit.nom}"
    )
        produit.delete()
        messages.success(request, "Produit supprimé avec succès.")
        return redirect('produits_liste')
    return redirect('produits_liste')


import pandas as pd
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import Produit, Categorie, Magasin

@login_required
def telecharger_modele_produit(request):
    # Colonnes du fichier Excel
    columns = [
        "nom",
        "categorie",
        "code_barre",
        "sku",
        "description",
        "prix_achat",
        "prix_vente",
        "taux_tva",
        "quantite_stock",
        "seuil_alerte",
        "date_fabrication",
        "date_expiration",
    ]

    df = pd.DataFrame(columns=columns)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="modele_produits.xlsx"'
    df.to_excel(response, index=False)

    return response


import pandas as pd
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .models import Produit, Categorie

@login_required
def importer_produits(request):
    if request.method == "POST":
        fichier = request.FILES.get("fichier")

        if not fichier:
            messages.error(request, "Veuillez sélectionner un fichier")
            return redirect("import_produits")

        try:
            df = pd.read_excel(fichier)

            magasin = request.user.magasin

            erreurs = []
            produits_a_creer = []
            lignes_erreur = []

            for index, row in df.iterrows():
                try:
                    # 🔒 VALIDATIONS
                    if not row.get("nom"):
                        raise ValueError("Nom obligatoire")

                    # Catégorie
                    categorie = None
                    if row.get("categorie"):
                        categorie = Categorie.objects.filter(
                            nom=row["categorie"]
                        ).first()

                    # Vérifier SKU unique
                    if row.get("sku") and Produit.objects.filter(
                        magasin=magasin, sku=row.get("sku")
                    ).exists():
                        raise ValueError("SKU déjà existant")

                    produit = Produit(
                        magasin=magasin,
                        nom=row["nom"],
                        categorie=categorie,
                        code_barre=row.get("code_barre"),
                        sku=row.get("sku"),
                        description=row.get("description"),
                        prix_achat=row.get("prix_achat") or 0,
                        prix_vente=row.get("prix_vente") or 0,
                        taux_tva=row.get("taux_tva") or 0,
                        quantite_stock=row.get("quantite_stock") or 0,
                        seuil_alerte=row.get("seuil_alerte") or 5,
                        date_fabrication=row.get("date_fabrication"),
                        date_expiration=row.get("date_expiration"),
                    )

                    produits_a_creer.append(produit)

                except Exception as e:
                    erreur_msg = str(e)

                    erreurs.append(f"Ligne {index+2}: {erreur_msg}")

                    # Sauvegarder ligne + erreur
                    ligne_dict = row.to_dict()
                    ligne_dict["erreur"] = erreur_msg
                    lignes_erreur.append(ligne_dict)

            # ✅ IMPORT PARTIEL
            with transaction.atomic():
                Produit.objects.bulk_create(produits_a_creer, ignore_conflicts=True)

            # 🔥 SI ERREURS → GENERER FICHIER EXCEL
            if lignes_erreur:
                df_erreurs = pd.DataFrame(lignes_erreur)

                response = HttpResponse(
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                response["Content-Disposition"] = 'attachment; filename="erreurs_import.xlsx"'

                df_erreurs.to_excel(response, index=False)

                messages.warning(
                    request,
                    f"{len(produits_a_creer)} produits importés, {len(lignes_erreur)} erreurs"
                )

                return response  # ⬅ téléchargement auto

            messages.success(
                request,
                f"{len(produits_a_creer)} produits importés avec succès ✅"
            )

            return redirect("produits_liste")

        except Exception as e:
            messages.error(request, f"Erreur fichier: {str(e)}")

    return render(request, "gerant/produits_liste.html")


from django.db.models import F
# ===============================
# DASHBOARD GERANT
# ===============================
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth
from django.utils.timezone import now
from datetime import timedelta, date
import json

from .models import Produit, Vente, LigneVente


@login_required
def dashboard_gerant(request):

    magasin = request.user.magasin
    today = now().date()

    # =========================
    # STATISTIQUES GENERALES
    # =========================
    produits_count = Produit.objects.filter(magasin=magasin).count()

    ventes_count = Vente.objects.filter(
        magasin=magasin
    ).count()

    alertes_stock = Produit.objects.filter(
        magasin=magasin,
        quantite_stock__lte=F("seuil_alerte")
    ).count()

    # =========================
    # CHIFFRE DU JOUR
    # =========================
    ventes_jour = Vente.objects.filter(
        magasin=magasin,
        date_creation__date=today,
        statut=Vente.Statut.COMPLETEE
    )

    chiffre_jour = ventes_jour.aggregate(
        total=Sum("montant_total")
    )["total"] or 0

    # =========================
    # BENEFICE DU JOUR
    # =========================
    benefice_jour = 0

    lignes = LigneVente.objects.filter(
        vente__magasin=magasin,
        vente__date_creation__date=today
    )

    for ligne in lignes:
        benefice_jour += (
            (ligne.prix_unitaire - ligne.produit.prix_achat)
            * ligne.quantite
        )

    # =========================
    # TOP PRODUITS
    # =========================
    top_produits = (
        LigneVente.objects
        .filter(vente__magasin=magasin)
        .values("produit__nom")
        .annotate(total_vendu=Sum("quantite"))
        .order_by("-total_vendu")[:5]
    )

    # =========================
    # DERNIERES VENTES
    # =========================
    ventes_recentes = (
        Vente.objects
        .filter(magasin=magasin)
        .order_by("-date_creation")[:5]
    )

    # =========================
    # TOP CAISSIERS
    # =========================
    top_caissiers = (
        Vente.objects
        .filter(
            magasin=magasin,
            statut=Vente.Statut.COMPLETEE,
            date_creation__date=today
        )
        .values("cree_par__first_name", "cree_par__last_name")
        .annotate(total_ventes=Count("id"))
        .order_by("-total_ventes")[:5]
    )

    # =========================
    # PRODUITS BIENTOT EXPIRES
    # =========================
    date_limite = date.today() + timedelta(days=120)

    produits_expiration = (
        Produit.objects
        .filter(
            magasin=magasin,
            date_expiration__lte=date_limite,
            date_expiration__gte=date.today()
        )
        .order_by("date_expiration")[:5]
    )

    produits_expires = Produit.objects.filter(
        magasin=magasin,
        date_expiration__lt=date.today()
    )[:5]
    
    # =========================
    # PRODUITS STOCK FAIBLE
    # =========================
    produits_stock_faible = (
        Produit.objects
        .filter(
            magasin=magasin,
            quantite_stock__lte=F("seuil_alerte")
        )[:5]
    )

    # =========================
    # GRAPHIQUE 6 MOIS
    # =========================
    six_mois = now() - timedelta(days=180)

    ventes_par_mois = (
        Vente.objects
        .filter(
            magasin=magasin,
            date_creation__gte=six_mois
        )
        .annotate(mois=TruncMonth("date_creation"))
        .values("mois")
        .annotate(total=Sum("montant_total"))
        .order_by("mois")
    )

    chart_labels = []
    chart_data = []

    for item in ventes_par_mois:
        chart_labels.append(item["mois"].strftime("%b %Y"))
        chart_data.append(float(item["total"] or 0))

    context = {
        "magasin": magasin,
        "produits_count": produits_count,
        "ventes_count": ventes_count,
        "alertes_stock": alertes_stock,
        "chiffre_jour": chiffre_jour,
        "benefice_jour": benefice_jour,
        "top_produits": top_produits,
        "ventes_recentes": ventes_recentes,
        "top_caissiers": top_caissiers,
        "produits_expiration": produits_expiration,
        "produits_expires":produits_expires,
        "produits_stock_faible": produits_stock_faible,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
    }

    return render(request, "gerant/dashboard_gerant.html", context)

from django.db.models import Q
from django.utils import timezone


def get_ventes_filtrees(request):
    magasin = request.user.magasin
    ventes = Vente.objects.filter(magasin=magasin).order_by('-date_creation')

    search = request.GET.get('search')
    if search:
        ventes = ventes.filter(
            Q(numero_facture__icontains=search) |
            Q(client_nom__icontains=search) |
            Q(lignes__produit__nom__icontains=search)
        ).distinct()

    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    if date_debut and date_fin:
        ventes = ventes.filter(date_creation__date__range=[date_debut, date_fin])

    filtre = request.GET.get('filtre')
    today = timezone.now().date()

    if filtre == "today":
        ventes = ventes.filter(date_creation__date=today)

    elif filtre == "month":
        ventes = ventes.filter(
            date_creation__year=today.year,
            date_creation__month=today.month
        )

    elif filtre == "year":
        ventes = ventes.filter(date_creation__year=today.year)

    montant_min = request.GET.get('montant_min')
    montant_max = request.GET.get('montant_max')

    if montant_min:
        ventes = ventes.filter(montant_total__gte=montant_min)

    if montant_max:
        ventes = ventes.filter(montant_total__lte=montant_max)

    statut = request.GET.get('statut')
    if statut:
        ventes = ventes.filter(statut=statut)

    return ventes.distinct()
    
@login_required
def ventes_liste(request):
    ventes = get_ventes_filtrees(request)
    
    magasin = request.user.magasin
    
    return render(request, 'gerant/ventes_liste.html', {
        'ventes': ventes,
        "magasin": magasin
    })


from django.db.models import Sum
from django.utils import timezone
from django.template.loader import get_template
from django.http import HttpResponse
from weasyprint import HTML


def format_gnf(value):
    return "{:,.0f}".format(value).replace(",", " ")


@login_required
def ventes_pdf(request):
    ventes = get_ventes_filtrees(request)
    magasin = request.user.magasin

    total_ventes = ventes.count()
    total_ca = ventes.aggregate(total=Sum('montant_total'))['total'] or 0
    total_tva = ventes.aggregate(total=Sum('montant_tva'))['total'] or 0
    total_remise = ventes.aggregate(total=Sum('remise'))['total'] or 0
    ventes_annulees = ventes.filter(statut='ANNULEE').count()

    total_articles = sum(
        ligne.quantite
        for vente in ventes
        for ligne in vente.lignes.all()
    )

    template = get_template("gerant/rapport_ventes.html")

    html = template.render({
        "ventes": ventes,
        "magasin": magasin,
        "date_generation": timezone.now(),
        "total_ventes": total_ventes,
        "total_ca": format_gnf(total_ca),
        "total_tva": format_gnf(total_tva),
        "total_remise": format_gnf(total_remise),
        "ventes_annulees": ventes_annulees,
        "total_articles": total_articles,
        "format_gnf": format_gnf,
    })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=rapport_ventes.pdf"

    HTML(string=html).write_pdf(response)

    return response

from django.http import JsonResponse
from .models import Produit
from django.contrib.auth.decorators import login_required

def produit_par_barcode(request, code):
    magasin = request.user.magasin

    # 🔥 nettoyage complet
    code = code.strip().replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")

    print("CODE FINAL:", repr(code))  # debug

    try:
        produit = Produit.objects.get(
            code_barre__iexact=code,
            magasin=magasin,
            actif=True
        )

        return JsonResponse({
            "success": True,
            "id": produit.id,
            "nom": produit.nom,
            "prix": float(produit.prix_vente),
            "taux_tva": float(produit.taux_tva),
            "stock": produit.quantite_stock,
        })

    except Produit.DoesNotExist:
        return JsonResponse({
            "success": False,
            "message": f"Produit introuvable ({code})"
        }, status=404)

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Table
from reportlab.lib.pagesizes import A4
from django.http import HttpResponse
from .models import Vente

@login_required
def ticket_pdf(request, pk):
    vente = Vente.objects.get(pk=pk, magasin=request.user.magasin)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket_{vente.numero_facture}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4)
    elements = []

    elements.append(Paragraph(f"Supermarché - Guinée", ParagraphStyle(name='Normal')))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Facture: {vente.numero_facture}", ParagraphStyle(name='Normal')))
    elements.append(Spacer(1, 12))

    data = [["Produit", "Qté", "Total (GNF)"]]

    for ligne in vente.lignes.all():
        data.append([
            ligne.produit.nom,
            str(ligne.quantite),
            f"{ligne.total:,.0f}"
        ])

    table = Table(data)
    elements.append(table)

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Total: {vente.montant_total:,.0f} GNF", ParagraphStyle(name='Normal')))

    doc.build(elements)
    return response

from rest_framework_simplejwt.tokens import RefreshToken

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
    
import json
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse

from .services.vente_service import creer_vente
@login_required
@transaction.atomic
def vente_create(request):
    magasin = request.user.magasin
    produits_disponibles = magasin.produits.filter(
        actif=True,
        quantite_stock__gt=0
    )

    token_data = {}
    if request.user.is_authenticated:
        #from .utils import get_tokens_for_user  # ou le fichier où tu as défini la fonction
        token_data = get_tokens_for_user(request.user)
        
    panier_initial = []

    if request.method == "POST":
        form_data = request.POST
        panier_json = form_data.get("panier_data")

        if not panier_json:
            return render(request, "gerant/vente_create.html", {
                "produits_disponibles": produits_disponibles,
                "error": "Le panier est vide !",
                "jwt_access": token_data.get('access')
            })

        try:
            panier = json.loads(panier_json)
        except json.JSONDecodeError:
            return render(request, "gerant/vente_create.html", {
                "produits_disponibles": produits_disponibles,
                "error": "Erreur panier invalide.",
                "jwt_access": token_data.get('access')
            })

        if not isinstance(panier, list) or len(panier) == 0:
            return render(request, "gerant/vente_create.html", {
                "produits_disponibles": produits_disponibles,
                "error": "Impossible de créer une vente vide.",
                "jwt_access": token_data.get('access')
            })

        try:
            panier_filtre = []
            for item in panier:
                try:
                    q = int(item.get("quantite", 0))
                    if q > 0:
                        panier_filtre.append(item)
                except (TypeError, ValueError):
                    continue
        except (TypeError, ValueError):
            return render(request, "gerant/vente_create.html", {
                "produits_disponibles": produits_disponibles,
                "error": "Certaines quantités du panier sont invalides.",
                "panier_initial": panier,
                "jwt_access": token_data.get('access')
            })

        if not panier_filtre:
            return render(request, "gerant/vente_create.html", {
                "produits_disponibles": produits_disponibles,
                "error": "Le panier ne contient aucun produit valide.",
                "panier_initial": panier,
                "jwt_access": token_data.get('access')
            })

        # 🔥 Reconstruction complète du panier pour template/JS
        panier_initial = []
        lignes = []

        for item in panier_filtre:
            produit_id = item.get("id")
            if not produit_id:
                continue  # évite crash si pas d'id

            try:
                produit = Produit.objects.select_for_update().get(
                    id=int(produit_id),
                    magasin=magasin
                )
            except (Produit.DoesNotExist, ValueError):
                continue

            quantite = int(item.get("quantite", 0))
            lignes.append({
                "produit": produit,
                "quantite": quantite,
                "prix_unitaire": produit.prix_vente,
            })

            # panier_initial contient toutes les infos nécessaires au JS
            panier_initial.append({
                "id": produit.id,
                "nom": produit.nom,
                "prix_vente": produit.prix_vente,
                "taux_tva": produit.taux_tva,
                "quantite": quantite,
                "quantite_stock": produit.quantite_stock,
            })

        if not lignes:
            return render(request, "gerant/vente_create.html", {
                "produits_disponibles": produits_disponibles,
                "error": "Aucun produit valide dans le panier.",
                "panier_initial": panier_initial,
                "magasin": magasin,
                "jwt_access": token_data.get('access')
            })

        # Vérification stock avant création vente
        for ligne in lignes:
            produit = ligne["produit"]
            quantite = ligne["quantite"]
            if quantite > produit.quantite_stock:
                raise ValidationError(
                    f"Stock insuffisant pour {produit.nom} "
                    f"(disponible: {produit.quantite_stock})"
                )

        # Création de la vente
        vente = creer_vente(
            magasin=magasin,
            cree_par=request.user,
            lignes=lignes,
            mode_paiement=form_data.get("mode_paiement", "ESPECES"),
            client_nom=form_data.get("client_nom", "").strip() or None,
            remise=Decimal(form_data.get("remise", "0") or "0"),
        )

        if request.user.is_authenticated:
            token_data = get_tokens_for_user(request.user)
            access_token = token_data.get('access')

        return redirect(
            f"{reverse('vente_create')}?vente_id={vente.id}&token={access_token}"
        )
 
    return render(request, "gerant/vente_create.html", {
        "produits_disponibles": produits_disponibles,
        "panier_initial": panier_initial,
        "magasin": magasin,
        'jwt_access': token_data.get('access')
    })
    
@login_required
def vente_detail(request, vente_id):
    magasin = request.user.magasin
    vente = get_object_or_404(Vente, id=vente_id, magasin=magasin)
    return render(request, "gerant/vente_detail.html", {"vente": vente, "magasin": magasin})

from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
import qrcode
import base64
from io import BytesIO
from .models import Vente

@login_required
def vente_recu_html(request, vente_id):
    magasin = request.user.magasin
    vente = get_object_or_404(Vente, id=vente_id, magasin=magasin)

    qr_text = f"""
        Reçu n°: {vente.numero_facture}
        Date: {vente.date_creation.strftime('%d/%m/%Y %H:%M')}
        Client: {vente.client_nom or '-'}
        Magasin: {magasin.nom}
        Adresse: {magasin.adresse or '-'}
        Tél: {magasin.telephone or '-'}

        Sous-total: {vente.sous_total:,} GNF
        TVA: {vente.montant_tva:,} GNF
        Remise: {vente.remise:,} GNF
        TOTAL: {vente.montant_total:,} GNF
    """

    qr = qrcode.QRCode(
        version=1,
        box_size=10,
        border=4
    )
    qr.add_data(qr_text.strip())
    qr.make(fit=True)

    img = qr.make_image(fill='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

    # 🔥 LOG AUDIT IMPORTANT
    transaction.on_commit(lambda: log_action(
        action="PRINT",
        modele="Vente",
        objet_id=vente.id,
        description=f"Impression reçu #{vente.numero_facture}"
    ))

    return render(request, "gerant/vente_recu.html", {
        "vente": vente,
        "qr_code_base64": qr_code_base64,
        "magasin": magasin
    })
    
@login_required
def vente_delete(request, vente_id):
    magasin = request.user.magasin
    vente = get_object_or_404(Vente, id=vente_id, magasin=magasin)

    if vente.statut != Vente.Statut.ANNULEE:
        messages.error(request, "Impossible de supprimer une vente non annulée.")
        return redirect("ventes_liste")

    transaction.on_commit(lambda: log_action(
        action="DELETE",
        modele="Vente",
        objet_id=vente.id,
        description=f"Suppression vente #{vente.numero_facture}"
    ))

    vente.delete()

    messages.success(request, "Vente supprimée avec succès.")
    return redirect("ventes_liste")

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Achat
@login_required
def achats_liste(request):
    magasin = request.user.magasin

    achats = Achat.objects.filter(magasin=magasin).order_by('-date_creation')

    statut = request.GET.get("statut", "")
    search = request.GET.get("search", "")

    if statut:
        achats = achats.filter(statut=statut)

    if search:
        from django.db.models import Q
        achats = achats.filter(
            Q(numero_facture__icontains=search) |
            Q(fournisseur__nom__icontains=search)
        )

    return render(request, "gerant/achats_liste.html", {
        "achats": achats,
        "magasin": magasin,
        "statut": statut,
        "search": search,
    })

from django.shortcuts import render, redirect
from django.db import transaction, DatabaseError
from django.contrib import messages
from .models import Produit, MouvementStock
from .forms import AchatForm, LigneAchatFormSet


def ajouter_achat(request):
    magasin = request.user.magasin
    produits = Produit.objects.filter(magasin=magasin)

    token_data = {}
    if request.user.is_authenticated:
        token_data = get_tokens_for_user(request.user)
    
    if request.method == 'POST':
        form = AchatForm(request.POST)
        formset = LigneAchatFormSet(request.POST)

        try:
            # ❌ VALIDATION FORM
            if not form.is_valid():
                messages.error(request, "Veuillez corriger les informations de l'achat.")
                return render(request, 'gerant/achat_form.html', {
                    'form': form,
                    'formset': formset,
                    'produits': produits,
                    'magasin': magasin,
                    'jwt_access': token_data.get('access')
                })

            if not formset.is_valid():
                messages.error(request, "Veuillez corriger les lignes de produits.")
                return render(request, 'gerant/achat_form.html', {
                    'form': form,
                    'formset': formset,
                    'produits': produits,
                    'magasin': magasin,
                    'jwt_access': token_data.get('access')
                })

            with transaction.atomic():

                achat = form.save(commit=False)
                achat.magasin = magasin
                achat.cree_par = request.user
                achat.save()

                formset.instance = achat

                total = 0

                for form_ligne in formset:
                    if not form_ligne.cleaned_data:
                        continue

                    if form_ligne.cleaned_data.get("DELETE"):
                        continue

                    ligne = form_ligne.save(commit=False)
                    ligne.achat = achat

                    produit = ligne.produit

                    if ligne.quantite <= 0:
                        raise ValueError(f"Quantité invalide pour {produit.nom}")

                    produit.quantite_stock += ligne.quantite
                    produit.prix_achat = ligne.prix_unitaire
                    produit.save()

                    MouvementStock.objects.create(
                        magasin=magasin,
                        produit=produit,
                        type_mouvement='ENTREE',
                        quantite=ligne.quantite,
                        reference=f"Achat #{achat.numero_facture}",
                        cree_par=request.user
                    )

                    total += ligne.quantite * ligne.prix_unitaire

                    ligne.save()

                # 🔥 sécurité
                if total == 0:
                    raise ValueError("Veuillez ajouter au moins un produit.")

                achat.montant_total = total
                achat.statut = getattr(Achat.Statut, "TERMINE", "TERMINE")
                transaction.on_commit(lambda: log_action(
                action="CREATE",
                modele="Achat",
                objet_id=achat.id,
                description=f"Création achat #{achat.numero_facture}"
            ))
                achat.save()

                messages.success(request, "Achat enregistré avec succès.")
                return redirect('achat_nouveau')

        # ⚠️ ERREUR LOGIQUE
        except ValueError as e:
            messages.error(request, str(e))

        # ⚠️ ERREUR BASE DE DONNÉES
        except DatabaseError:
            messages.error(request, "La facture existe déjà. Veuillez le modifier puis ressayer")

        # ⚠️ ERREUR GÉNÉRALE
        except Exception as e:
            messages.error(request, f"Une erreur inattendue est survenue : {str(e)}")

    else:
        form = AchatForm()
        formset = LigneAchatFormSet()

    return render(request, 'gerant/achat_form.html', {
        'form': form,
        'formset': formset,
        'produits': produits,
        'magasin': magasin,
        'jwt_access': token_data.get('access')
    })
    
    
@login_required
def achat_voir(request, pk):
    magasin = request.user.magasin
    achat = get_object_or_404(Achat, pk=pk, magasin=magasin)
    return render(request, 'gerant/achat_voir.html',{
        'achat': achat, 
        'magasin': magasin
        })
    
from django.db import transaction
from supermarcher.signals import log_action
@login_required
def achat_supprimer(request, pk):
    magasin = request.user.magasin
    achat = get_object_or_404(Achat, pk=pk, magasin=magasin)

    if request.method == 'POST':

        achat_id = achat.id
        achat_ref = achat.numero_facture

        transaction.on_commit(lambda: log_action(
            action="DELETE",
            modele="Achat",
            objet_id=achat_id,
            description=f"Suppression achat #{achat_ref}"
        ))

        achat.delete()
        return redirect('achats_liste')

    # ❌ plus de template de confirmation
    return redirect('achats_liste')

from django.db import transaction
from supermarcher.signals import log_action

@login_required
def achat_annuler(request, pk):
    magasin = request.user.magasin
    achat = get_object_or_404(Achat, pk=pk, magasin=magasin)

    if achat.statut == 'TERMINE':
        messages.error(request, "Impossible d'annuler un achat déjà terminé.")
        return redirect('achats_liste')

    achat.statut = 'EN_ATTENTE'
    achat.save()

    transaction.on_commit(lambda: log_action(
        action="CANCEL",
        modele="Achat",
        objet_id=achat.id,
        description=f"Annulation achat #{achat.numero_facture}"
    ))

    messages.success(request, f"L'achat {achat.numero_facture} a été annulé.")
    return redirect('achats_liste')


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import MouvementStock
from django.core.paginator import Paginator
from django.db.models import Q
from datetime import datetime, date

@login_required
def stock_mouvements(request):
    magasin = request.user.magasin
    mouvements = MouvementStock.objects.filter(magasin=magasin).order_by('-date_creation')

    # ----- FILTRES -----
    search = request.GET.get('search', '').strip()
    type_mouvement = request.GET.get('type', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    today = request.GET.get('today', '')
    page_number = int(request.GET.get('page', 1))
    afficher_restantes = request.GET.get('restantes', '')

    if search:
        mouvements = mouvements.filter(
            Q(produit__nom__icontains=search) |
            Q(reference__icontains=search) |
            Q(cree_par__username__icontains=search)
        )

    if type_mouvement in ['ENTREE', 'SORTIE', 'AJUSTEMENT']:
        mouvements = mouvements.filter(type_mouvement=type_mouvement)

    if today == '1':
        mouvements = mouvements.filter(date_creation__date=date.today())
    else:
        if date_debut:
            try:
                mouvements = mouvements.filter(date_creation__date__gte=datetime.strptime(date_debut, "%Y-%m-%d"))
            except:
                pass
        if date_fin:
            try:
                mouvements = mouvements.filter(date_creation__date__lte=datetime.strptime(date_fin, "%Y-%m-%d"))
            except:
                pass
    periode = request.GET.get('periode', '')

    if periode == "today":
        mouvements = mouvements.filter(date_creation__date=date.today())

    elif periode == "yesterday":
        mouvements = mouvements.filter(date_creation__date=date.today() - timedelta(days=1))

    elif periode == "7days":
        mouvements = mouvements.filter(date_creation__date__gte=date.today() - timedelta(days=7))

    elif periode == "30days":
        mouvements = mouvements.filter(date_creation__date__gte=date.today() - timedelta(days=30))

    else:
        if date_debut:
            mouvements = mouvements.filter(date_creation__date__gte=date_debut)

        if date_fin:
            mouvements = mouvements.filter(date_creation__date__lte=date_fin)
            
    # ----- PAGINATION -----
    paginator = Paginator(mouvements, 10)  # 10 par page

    if afficher_restantes == "1":
        # On affiche toutes les pages restantes (à partir de la page courante)
        paginated_mouvements = mouvements[(page_number-1)*10:]
        show_pagination = True
    else:
        paginated_mouvements = paginator.get_page(page_number)
        show_pagination = True

    context = {
        'mouvements': paginated_mouvements,
        'magasin': magasin,
        'filters': {
            'search': search,
            'type': type_mouvement,
            'periode': periode,
            'date_debut': date_debut,
            'date_fin': date_fin,
            'today': today
        },
        'show_pagination': show_pagination,
        'paginator': paginator,
        'current_page': page_number,
        'afficher_restantes': afficher_restantes
    }
    return render(request, 'gerant/stock_mouvements.html', context)

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Fournisseur
from django.core.paginator import Paginator

@login_required
def fournisseurs_liste(request):
    magasin = request.user.magasin
    fournisseurs = Fournisseur.objects.filter(magasin=magasin)

    # filtres
    search = request.GET.get("search", "")
    telephone = request.GET.get("telephone", "")
    email = request.GET.get("email", "")

    if search:
        fournisseurs = fournisseurs.filter(nom__icontains=search)

    if telephone:
        fournisseurs = fournisseurs.filter(telephone__icontains=telephone)

    if email:
        fournisseurs = fournisseurs.filter(email__icontains=email)

    fournisseurs = fournisseurs.order_by("nom")

    # pagination
    paginator = Paginator(fournisseurs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "magasin": magasin,
        "fournisseurs": page_obj,
        "page_obj": page_obj,
        "filters": {
            "search": search,
            "telephone": telephone,
            "email": email,
        }
    }

    return render(request, "gerant/fournisseurs_liste.html", context)

from django.db import transaction
from supermarcher.signals import log_action

@login_required
def fournisseur_nouveau(request):
    magasin = request.user.magasin

    if request.method == 'POST':
        form = FournisseurForm(request.POST, magasin=magasin)
        if form.is_valid():
            fournisseur = form.save(commit=False)
            fournisseur.magasin = magasin
            fournisseur.save()

            transaction.on_commit(lambda: log_action(
                action="CREATE",
                modele="Fournisseur",
                objet_id=fournisseur.id,
                description=f"Création fournisseur {fournisseur.nom}"
            ))

            messages.success(request, "Fournisseur ajouté avec succès.")
            return redirect('fournisseurs_liste')

        else:
            messages.error(request, "Ce fournisseur existe déjà ou les informations sont invalides.")
    
    else:
            form = FournisseurForm(magasin=magasin)

    return render(request, 'gerant/fournisseur_form.html', {
        'form': form,
        'titre': "Ajouter un fournisseur",
        'magasin': magasin
    })
    
@login_required
def fournisseur_voir(request, pk):
    magasin = request.user.magasin
    fournisseur = get_object_or_404(Fournisseur, pk=pk, magasin=magasin)

    # Les 5 derniers achats de ce fournisseur
    derniers_achats = (
        Achat.objects
        .filter(magasin=magasin, fournisseur=fournisseur)
        .order_by('-date_creation')[:5]
    )

    return render(request, 'gerant/fournisseur_voir.html', {
        'fournisseur': fournisseur,
        'derniers_achats': derniers_achats,
        'magasin': magasin,
    })

from django.db import transaction
from supermarcher.signals import log_action
@login_required
def fournisseur_modifier(request, pk):
    magasin = request.user.magasin
    fournisseur = get_object_or_404(Fournisseur, pk=pk, magasin=magasin)

    form = FournisseurForm(instance=fournisseur, magasin=magasin)

    if request.method == 'POST':
        form = FournisseurForm(request.POST, instance=fournisseur, magasin=magasin)

        if form.is_valid():

            # 🧠 CAS : aucune modification
            if not form.has_changed():
                messages.success(request, "Aucune modification effectuée.")
                return redirect('fournisseurs_liste')

            # 🧠 CAS : modification réelle
            form.save()

            transaction.on_commit(lambda: log_action(
                action="UPDATE",
                modele="Fournisseur",
                objet_id=fournisseur.id,
                description=f"Modification fournisseur {fournisseur.nom}"
            ))

            messages.success(request, "Fournisseur modifié avec succès.")
            return redirect('fournisseurs_liste')

        else:
            messages.error(request, "Conflit : fournisseur déjà existant.")

    return render(request, 'gerant/fournisseur_form.html', {
        'form': form,
        'titre': "Modifier le fournisseur",
        'magasin': magasin
    })
    
from django.db import transaction
from supermarcher.signals import log_action

@login_required
def fournisseur_supprimer(request, pk):
    magasin = request.user.magasin
    fournisseur = get_object_or_404(Fournisseur, pk=pk, magasin=magasin)

    achats_count = fournisseur.achat_set.count()

    if request.method == 'POST' and achats_count == 0:

        fournisseur_id = fournisseur.id
        fournisseur_nom = fournisseur.nom

        transaction.on_commit(lambda: log_action(
            action="DELETE",
            modele="Fournisseur",
            objet_id=fournisseur_id,
            description=f"Suppression fournisseur {fournisseur_nom}"
        ))

        fournisseur.delete()
        messages.success(request, "Fournisseur supprimé.")
        return redirect('fournisseurs_liste')

    return render(request, 'gerant/fournisseur_confirm_delete.html', {
        'fournisseur': fournisseur,
        'achats_count': achats_count,
    })
    
from django.views import View
from django.shortcuts import render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from datetime import timedelta
from django.db.models import F, Sum, Count, Avg, Value
from django.db.models.functions import Concat

from .models import (
    Vente, LigneVente, Produit, Achat, MouvementStock, Utilisateur, Magasin, LigneAchat
)

# =======================================
# DASHBOARD GLOBAL (Page complète)
# =======================================
class DashboardGlobalView(View):
    template_name = "gerant/rapports.html"

    def get(self, request):
        magasin_id = request.GET.get('magasin')
        utilisateur_id = request.GET.get('utilisateur')
        date_debut = request.GET.get('date_debut')
        date_fin = request.GET.get('date_fin')
        type_rapport = request.GET.get('type_rapport', '')

        user_magasin = getattr(request.user, 'magasin', None)

        if request.user.role == 'SUPERADMIN' and magasin_id:
            magasin = Magasin.objects.filter(id=magasin_id).first()
        else:
            magasin = user_magasin

        ventes = Vente.objects.all()
        achats = Achat.objects.all()
        produits = Produit.objects.all()
        mouvements = MouvementStock.objects.all()
        
        jour = request.GET.get('jour')
    
        # Filtrage magasin
        if magasin:
            ventes = ventes.filter(magasin=magasin)
            achats = achats.filter(magasin=magasin)
            produits = produits.filter(magasin=magasin)
            mouvements = mouvements.filter(magasin=magasin)

        # Filtrage par rôle
        if request.user.role == 'CAISSIER':
            ventes = ventes.filter(cree_par=request.user)
            achats = achats.filter(cree_par=request.user)
            mouvements = mouvements.filter(cree_par=request.user)

        # Filtrage par formulaire pour gérants/SUPERADMIN
        utilisateur_id = request.GET.get('utilisateur')
        if utilisateur_id and request.user.role != 'CAISSIER':
            ventes = ventes.filter(cree_par_id=utilisateur_id)
            achats = achats.filter(cree_par_id=utilisateur_id)
            mouvements = mouvements.filter(cree_par_id=utilisateur_id)
    
        if jour:
            try:
                jour_date = datetime.strptime(jour, "%Y-%m-%d").date()
                debut = datetime.combine(jour_date, datetime.min.time(), tzinfo=timezone.get_current_timezone())
                fin = datetime.combine(jour_date, datetime.max.time(), tzinfo=timezone.get_current_timezone())
                ventes = ventes.filter(date_creation__range=(debut, fin))
                achats = achats.filter(date_creation__range=(debut, fin))
                mouvements = mouvements.filter(date_creation__range=(debut, fin))
            except ValueError:
                pass
            
        if date_debut:
            debut = datetime.combine(datetime.strptime(date_debut, "%Y-%m-%d"), datetime.min.time(), tzinfo=timezone.get_current_timezone())
            ventes = ventes.filter(date_creation__gte=debut)
            achats = achats.filter(date_creation__gte=debut)
            mouvements = mouvements.filter(date_creation__gte=debut)

        if date_fin:
            fin = datetime.combine(datetime.strptime(date_fin, "%Y-%m-%d"), datetime.max.time(), tzinfo=timezone.get_current_timezone())
            ventes = ventes.filter(date_creation__lte=fin)
            achats = achats.filter(date_creation__lte=fin)
            mouvements = mouvements.filter(date_creation__lte=fin)
        
        
        if request.user.role == 'SUPERADMIN':
            magasins_list = Magasin.objects.all()
        else:
            magasins_list = Magasin.objects.filter(id=user_magasin.id) if user_magasin else Magasin.objects.none()

        context = {
            'magasins': magasins_list,
            'utilisateurs': Utilisateur.objects.filter(magasin=magasin) if magasin else Utilisateur.objects.none(),
            'selected_magasin': magasin_id,
            'selected_utilisateur': utilisateur_id,
            'selected_date_debut': date_debut,
            'selected_date_fin': date_fin,
            'type_rapport': type_rapport,
            'magasin': magasin,
        }

        # -----------------------
        # RAPPORTS DYNAMIQUES
        # -----------------------
        # VENTES
        if type_rapport == "produits_plus_vendus":
            lignes = LigneVente.objects.filter(vente__in=ventes)
            context['produits_plus_vendus'] = lignes.values('produit__nom').annotate(
                total_vendu=Sum('quantite')
            ).order_by('-total_vendu')[:10]

        elif type_rapport == "performance_caissier":
            context['performance_caissier'] = ventes.values('cree_par__username').annotate(
                total_ventes=Sum('montant_total'),
                nb_ventes=Count('id'),
                ventes_annulees=Count('id', filter=Q(statut='ANNULEE'))
            )

        elif type_rapport == "chiffres_cles":
            total_ca = ventes.aggregate(total=Sum('montant_total'))['total'] or 0
            total_tva = ventes.aggregate(total=Sum('montant_tva'))['total'] or 0
            total_remises = ventes.aggregate(total=Sum('remise'))['total'] or 0
            ventes_annulees = ventes.filter(statut='ANNULEE').count()
            stats = ventes.aggregate(total=Sum('montant_total'), count=Count('id'))
            panier_moyen = (stats['total'] or 0) / (stats['count'] or 1)
            lignes = LigneVente.objects.filter(vente__in=ventes).annotate(
                benefice=(F('prix_unitaire') - F('produit__prix_achat')) * F('quantite')
            )
            benefice_total = lignes.aggregate(total=Sum('benefice'))['total'] or 0
            context.update({
                'total_ca': total_ca,
                'total_tva': total_tva,
                'total_remises': total_remises,
                'ventes_annulees': ventes_annulees,
                'panier_moyen': panier_moyen,
                'benefice_total': benefice_total,
            })

        # Produits vendus
        elif type_rapport == "produits_vendus":

            lignes = LigneVente.objects.filter(vente__in=ventes)

            produits_vendus = lignes.values(
                'produit__id',
                'produit__nom',
                'produit__prix_vente'
            ).annotate(
                quantite_totale=Sum('quantite'),
                total_ventes=Sum('total')
            ).order_by('-quantite_totale')

            context['produits_vendus'] = produits_vendus

            # total basé sur les filtres
            total_jour = lignes.aggregate(total=Sum('total'))['total'] or 0
            context['total_jour'] = total_jour

            # pour la devise
            context['magasin'] = magasin

        elif type_rapport == "ventes_annulees":
            context['ventes_annulees'] = ventes.filter(statut='ANNULEE')

        # NOUVEAUX RAPPORTS VENTES
        elif type_rapport == "ventes_par_categorie":
            context['ventes_par_categorie'] = LigneVente.objects.filter(vente__in=ventes).values(
                'produit__categorie__nom'
            ).annotate(total_ventes=Sum('total')).order_by('-total_ventes')

        elif type_rapport == "ventes_par_mode_paiement":
            context['ventes_par_mode_paiement'] = ventes.values('mode_paiement').annotate(
                total_ventes=Sum('montant_total')
            )

        elif type_rapport == "ventes_par_client":
            context['ventes_par_client'] = ventes.values('client_nom').annotate(
                total_ventes=Sum('montant_total'), nb_ventes=Count('id')
            ).order_by('-total_ventes')

        # PRODUITS
        elif type_rapport == "produits_reapprovisionnement":
            context['produits_reapprovisionnement'] = produits.filter(
                quantite_stock__lte=F('seuil_alerte')
            )

        elif type_rapport == "produits_proches_peremption":
            context['produits_proches_peremption'] = produits.filter(
                date_expiration__lte=timezone.now() + timedelta(days=7)
            )

        elif type_rapport == "produits_expire":
            context['produits_expire'] = produits.filter(
                date_expiration__lt=timezone.now()
            )

        elif type_rapport == "produits_jamais_vendus":
            context['produits_jamais_vendus'] = produits.exclude(
                id__in=LigneVente.objects.values_list('produit_id', flat=True)
            )

        # NOUVEAUX RAPPORTS PRODUITS
        elif type_rapport == "produits_plus_rentables":
            lignes = LigneVente.objects.filter(vente__in=ventes).annotate(
                marge=(F('prix_unitaire') - F('produit__prix_achat')) * F('quantite')
            )
            context['produits_plus_rentables'] = lignes.values('produit__nom').annotate(
                total_marge=Sum('marge')
            ).order_by('-total_marge')[:10]

        elif type_rapport == "rotation_stock":
            lignes = LigneVente.objects.filter(vente__in=ventes)
            context['rotation_stock'] = lignes.values('produit__nom').annotate(
                total_vendu=Sum('quantite')
            ).order_by('-total_vendu')

        # STOCK
        elif type_rapport == "stock_actuel":
            context['stock_actuel'] = produits

        elif type_rapport == "mouvements_stock":
            context['mouvements_stock'] = mouvements.order_by('-date_creation')

        # FOURNISSEURS
        elif type_rapport == "achats_par_fournisseur":
            context['achats_par_fournisseur'] = achats.values('fournisseur__nom').annotate(
                total_achats=Sum('montant_total')
            ).order_by('-total_achats')

        # NOUVEAUX RAPPORTS FOURNISSEURS
        elif type_rapport == "delai_livraison_fournisseur":
            # Exemple simple : moyenne des délais
            context['delai_livraison_fournisseur'] = achats.values('fournisseur__nom').annotate(
                delai_moyen=Sum(F('date_creation') - F('date_creation'))  # placeholder
            )

        elif type_rapport == "historique_prix_fournisseur":
            context['historique_prix_fournisseur'] = achats.values('fournisseur__nom', 'numero_facture', 'montant_total')

        # FINANCES
        elif type_rapport == "ca_par_categorie":
            lignes = LigneVente.objects.filter(vente__in=ventes)
            context['ca_par_categorie'] = lignes.values('produit__categorie__nom').annotate(
                total_ca=Sum('total')
            ).order_by('-total_ca')

        elif type_rapport == "marge_par_produit":
            lignes = LigneVente.objects.filter(vente__in=ventes).annotate(
                marge=(F('prix_unitaire') - F('produit__prix_achat')) * F('quantite')
            )
            context['marge_par_produit'] = lignes.values('produit__nom').annotate(
                total_marge=Sum('marge')
            ).order_by('-total_marge')

        elif type_rapport == "panier_moyen":
            stats = ventes.aggregate(total=Sum('montant_total'), count=Count('id'))
            context['panier_moyen'] = (stats['total'] or 0) / (stats['count'] or 1)

        elif type_rapport == "ca_par_magasin":
            context['ca_par_magasin'] = ventes.values('magasin__nom').annotate(
                total_ca=Sum('montant_total')
            ).order_by('-total_ca')

        # CLIENTS
        elif type_rapport == "clients_fideles":
            context['clients_fideles'] = ventes.values('client_nom').annotate(
                nb_achats=Count('id')
            ).order_by('-nb_achats')

        elif type_rapport == "frequence_achat":
            context['frequence_achat'] = ventes.values('client_nom').annotate(
                nb_achats=Count('id')
            )

        elif type_rapport == "valeur_client":
            context['valeur_client'] = ventes.values('client_nom').annotate(
                total_depense=Sum('montant_total')
            )

        return render(request, self.template_name, context)


## =======================================
# RAPPORT AJAX (Pour tous les rapports)
# =======================================
class RapportAjaxView(View):

    RAPPORTS = {
        # VENTES
        "produits_plus_vendus": {"template": "rapports/produits_plus_vendus.html"},
        "performance_caissier": {"template": "rapports/performance_caissier.html"},
        "chiffres_cles": {"template": "rapports/chiffres_cles.html"},
        "produits_vendus": {"template": "rapports/produits_vendus.html"},
        "ventes_annulees": {"template": "rapports/ventes_annulees.html"},
        "ventes_par_categorie": {"template": "rapports/ventes_par_categorie.html"},
        "ventes_par_mode_paiement": {"template": "rapports/ventes_par_mode_paiement.html"},
        "ventes_par_client": {"template": "rapports/ventes_par_client.html"},

        # PRODUITS
        "produits_reapprovisionnement": {"template": "rapports/produits_reapprovisionnement.html"},
        "produits_proches_peremption": {"template": "rapports/produits_proches_peremption.html"},
        "produits_expire": {"template": "rapports/produits_expire.html"},
        "produits_jamais_vendus": {"template": "rapports/produits_jamais_vendus.html"},
        "produits_plus_rentables": {"template": "rapports/produits_plus_rentables.html"},
        "rotation_stock": {"template": "rapports/rotation_stock.html"},

        # STOCK
        "stock_actuel": {"template": "rapports/produits_stock_actuel.html"},
        "mouvements_stock": {"template": "rapports/mouvements_stock.html"},
        "valeur_stock": {"template": "rapports/valeur_stock.html"},

        # FOURNISSEURS
        "achats_par_fournisseur": {"template": "rapports/achats_par_fournisseur.html"},
        "delai_livraison_fournisseur": {"template": "rapports/delai_livraison_fournisseur.html"},
        "historique_prix_fournisseur": {"template": "rapports/historique_prix_fournisseur.html"},

        # FINANCES
        "ca_par_categorie": {"template": "rapports/ca_par_categorie.html"},
        "marge_par_produit": {"template": "rapports/marge_par_produit.html"},
        "panier_moyen": {"template": "rapports/panier_moyen.html"},
        "ca_par_magasin": {"template": "rapports/ca_par_magasin.html"},

        # CLIENTS
        "clients_fideles": {"template": "rapports/clients_fideles.html"},
        "frequence_achat": {"template": "rapports/frequence_achat.html"},
        "valeur_client": {"template": "rapports/valeur_client.html"},
    }

    def get(self, request):
        type_rapport = request.GET.get("type_rapport")
        utilisateur_id = request.GET.get("utilisateur")
        date_debut = request.GET.get("date_debut")
        date_fin = request.GET.get("date_fin")
        magasin = getattr(request.user, "magasin", None)

        ventes = Vente.objects.all()
        produits = Produit.objects.all()
        achats = Achat.objects.all()
        mouvements = MouvementStock.objects.all()

        # Filtrage magasin
        if magasin:
            ventes = ventes.filter(magasin=magasin)
            achats = achats.filter(magasin=magasin)
            produits = produits.filter(magasin=magasin)
            mouvements = mouvements.filter(magasin=magasin)

        # Filtrage par rôle
        if request.user.role == 'CAISSIER':
            ventes = ventes.filter(cree_par=request.user)
            achats = achats.filter(cree_par=request.user)
            mouvements = mouvements.filter(cree_par=request.user)

        # Filtrage par formulaire pour gérants/SUPERADMIN
        utilisateur_id = request.GET.get('utilisateur')
        if utilisateur_id and request.user.role != 'CAISSIER':
            ventes = ventes.filter(cree_par_id=utilisateur_id)
            achats = achats.filter(cree_par_id=utilisateur_id)
            mouvements = mouvements.filter(cree_par_id=utilisateur_id)
            
        jour = request.GET.get('jour')
        if jour:
            try:
                jour_date = datetime.strptime(jour, "%Y-%m-%d").date()
                debut = datetime.combine(jour_date, datetime.min.time(), tzinfo=timezone.get_current_timezone())
                fin = datetime.combine(jour_date, datetime.max.time(), tzinfo=timezone.get_current_timezone())
                ventes = ventes.filter(date_creation__range=(debut, fin))
                achats = achats.filter(date_creation__range=(debut, fin))
                mouvements = mouvements.filter(date_creation__range=(debut, fin))
            except ValueError:
                pass
            
        if date_debut:
            debut = datetime.combine(datetime.strptime(date_debut, "%Y-%m-%d"), datetime.min.time(), tzinfo=timezone.get_current_timezone())
            ventes = ventes.filter(date_creation__gte=debut)
            achats = achats.filter(date_creation__gte=debut)
            mouvements = mouvements.filter(date_creation__gte=debut)

        if date_fin:
            fin = datetime.combine(datetime.strptime(date_fin, "%Y-%m-%d"), datetime.max.time(), tzinfo=timezone.get_current_timezone())
            ventes = ventes.filter(date_creation__lte=fin)
            achats = achats.filter(date_creation__lte=fin)
            mouvements = mouvements.filter(date_creation__lte=fin)

        context = {}
        
        # -----------------------
        # LOGIQUE RAPPORT
        # -----------------------
        if type_rapport in ["produits_plus_vendus", "performance_caissier", "chiffres_cles",
                            "produits_vendus", "ventes_annulees",
                            "ventes_par_categorie", "ventes_par_mode_paiement", "ventes_par_client"]:
            # Ventes dynamiques
            lignes = LigneVente.objects.filter(vente__in=ventes)
            if type_rapport == "produits_plus_vendus":
                context["produits_plus_vendus"] = lignes.values("produit__nom").annotate(
                    total_vendu=Sum("quantite")
                ).order_by("-total_vendu")[:10]
            elif type_rapport == "performance_caissier":
                context["performance_caissier"] = ventes.values("cree_par__username").annotate(
                    total_ventes=Sum("montant_total"),
                    nb_ventes=Count("id"),
                    ventes_annulees=Count("id", filter=Q(statut="ANNULEE"))
                )
            elif type_rapport == "chiffres_cles":
                total_ca = ventes.aggregate(total=Sum("montant_total"))["total"] or 0
                total_tva = ventes.aggregate(total=Sum("montant_tva"))["total"] or 0
                total_remises = ventes.aggregate(total=Sum("remise"))["total"] or 0
                ventes_annulees = ventes.filter(statut="ANNULEE").count()
                stats = ventes.aggregate(total=Sum("montant_total"), count=Count("id"))
                panier_moyen = (stats["total"] or 0) / (stats["count"] or 1)
                lignes_benefice = lignes.annotate(
                    benefice=(F("prix_unitaire") - F("produit__prix_achat")) * F("quantite")
                )
                benefice_total = lignes_benefice.aggregate(total=Sum("benefice"))["total"] or 0
                context.update({
                    "total_ca": total_ca,
                    "total_tva": total_tva,
                    "total_remises": total_remises,
                    "ventes_annulees": ventes_annulees,
                    "panier_moyen": panier_moyen,
                    "benefice_total": benefice_total,
                })
            # Dans RapportAjaxView.get
            elif type_rapport == "produits_vendus":
                lignes = LigneVente.objects.filter(vente__in=ventes)

                produits_vendus = lignes.values(
                    'produit__id',
                    'produit__nom',
                    'produit__prix_vente'
                ).annotate(
                    quantite_totale=Sum('quantite'),
                    total_ventes=Sum('total')
                ).order_by('-quantite_totale')

                context['produits_vendus'] = produits_vendus

                # total dépend des filtres
                total_jour = lignes.aggregate(total=Sum('total'))['total'] or 0
                context['total_jour'] = total_jour

                # pour la devise
                context['magasin'] = magasin
            elif type_rapport == "ventes_annulees":
                ventes_annulees = ventes.filter(statut='ANNULEE')
                context['ventes_annulees'] = ventes_annulees
                context['magasin'] = magasin
            elif type_rapport == "ventes_par_categorie":
                context['ventes_par_categorie'] = lignes.values(
                    'produit__categorie__nom'
                ).annotate(
                    total_ventes=Sum('total'),
                    nombre_ventes=Count('vente_id', distinct=True)
                ).order_by('-total_ventes')

                context['magasin'] = magasin
            elif type_rapport == "ventes_par_mode_paiement":
                data = ventes.values('mode_paiement').annotate(
                    total=Sum('montant_total'), count=Count('id')
                )
                context['ventes_par_mode_paiement'] = data
                #template = "rapports/ventes_par_mode_paiement.html"
                context['ventes_par_mode_paiement'] = data
                context['magasin'] = magasin
            elif type_rapport == "ventes_par_client":
                data = ventes.values('client_nom').annotate(
                    total=Sum('montant_total'), count=Count('id')
                )
                context['ventes_par_client'] = data
                #template = "rapports/ventes_par_client.html"
                context['magasin'] = magasin

        # Produits
        elif type_rapport in ["produits_reapprovisionnement", "produits_proches_peremption",
                              "produits_expire", "produits_jamais_vendus",
                              "produits_plus_rentables", "rotation_stock"]:
            lignes = LigneVente.objects.filter(vente__in=ventes)
            if type_rapport == "produits_reapprovisionnement":
                context["produits_reapprovisionnement"] = produits.filter(
                    quantite_stock__lte=F("seuil_alerte")
                )
            elif type_rapport == "produits_proches_peremption":
                context["produits_proches_peremption"] = produits.filter(
                    date_expiration__lte=timezone.now() + timedelta(days=7)
                )
            elif type_rapport == "produits_expire":
                context["produits_expire"] = produits.filter(
                    date_expiration__lt=timezone.now()
                )
            elif type_rapport == "produits_jamais_vendus":
                context["produits_jamais_vendus"] = produits.exclude(
                    id__in=LigneVente.objects.values_list("produit_id", flat=True)
                )
            elif type_rapport == "produits_plus_rentables":
                lignes_marge = lignes.annotate(
                    marge=(F("prix_unitaire") - F("produit__prix_achat")) * F("quantite")
                )
                context['produits_plus_rentables'] = lignes_marge.values('produit__nom').annotate(
                    total_marge=Sum('marge')
                ).order_by('-total_marge')[:10]
            elif type_rapport == "rotation_stock":
                lignes = LigneVente.objects.filter(vente__in=ventes)
                data = lignes.values('produit__nom').annotate(
                    total_vendu=Sum('quantite'),
                    stock_actuel=F('produit__quantite_stock')
                )
                context['rotation_stock'] = data
                #template = "rapports/rotation_stock.html"

        # Stock
        elif type_rapport in ["stock_actuel", "mouvements_stock", "valeur_stock"]:
            if type_rapport == "stock_actuel":
                context["stock_actuel"] = produits
            elif type_rapport == "mouvements_stock":
                context["mouvements_stock"] = mouvements.order_by('-date_creation')
            elif type_rapport == "valeur_stock":
                produits_stock = produits.annotate(
                    valeur=F('quantite_stock') * F('prix_vente')
                )
                context['valeur_stock'] = produits_stock
                #template = "rapports/valeur_stock.html"

        # Fournisseurs
        elif type_rapport in ["achats_par_fournisseur", "delai_livraison_fournisseur",
                              "historique_prix_fournisseur"]:
            if type_rapport == "achats_par_fournisseur":
                # queryset annoté avec total et nombre d'achats
                fournisseurs = Fournisseur.objects.filter(
                    magasin=magasin
                ).annotate(
                    total=Sum('achat__montant_total'),
                    nb=Count('achat')
                )

                context['fournisseurs'] = fournisseurs

                #template = "rapports/achats_par_fournisseur.html"
            elif type_rapport == "delai_livraison_fournisseur":
                context["delai_livraison_fournisseur"] = achats.values(
                    "fournisseur__nom",
                    "fournisseur__prenom"
                ).annotate(
                    delai_moyen=Sum(F('date_creation') - F('date_creation'))
                )
            elif type_rapport == "historique_prix_fournisseur":
                context["historique_prix_fournisseur"] = achats.values(
                    "fournisseur__nom",
                    "fournisseur__prenom",
                    "numero_facture",
                    "montant_total"
                )

        # Finances
        elif type_rapport in ["ca_par_categorie", "marge_par_produit", "panier_moyen", "ca_par_magasin"]:
            lignes = LigneVente.objects.filter(vente__in=ventes)
            if type_rapport == "ca_par_categorie":
                context['ca_par_categorie'] = lignes.values('produit__categorie__nom').annotate(
                    total_ca=Sum('total')
                ).order_by('-total_ca')
            elif type_rapport == "marge_par_produit":
                lignes_marge = lignes.annotate(
                    marge=(F("prix_unitaire") - F("produit__prix_achat")) * F("quantite")
                )

                context['marge_par_produit'] = lignes_marge.values(
                    nom=F('produit__nom'),
                    prix_achat=F('produit__prix_achat'),
                    prix_vente=F('prix_unitaire')
                ).annotate(
                    marge=Sum('marge'),
                    quantite=Sum('quantite')
                ).order_by('-marge')
            elif type_rapport == "panier_moyen":
                # On regroupe les ventes par caissier
                panier_caissiers = ventes.values('cree_par__username').annotate(
                    total_ca=Sum('montant_total'),
                    nb_ventes=Count('id')
                )

                # Calcul du panier moyen par caissier
                panier_moyen_par_caissier = []
                for p in panier_caissiers:
                    panier_moyen = (p['total_ca'] or 0) / (p['nb_ventes'] or 1)
                    panier_moyen_par_caissier.append({
                        'caissier': p['cree_par__username'],
                        'panier_moyen': panier_moyen
                    })

                context['panier_moyen_par_caissier'] = panier_moyen_par_caissier

        # Clients
        elif type_rapport in ["clients_fideles", "frequence_achat", "valeur_client"]:
            if type_rapport == "clients_fideles":
                context['clients_fideles'] = ventes.values('client_nom').annotate(
                    nb_achats=Count('id')
                ).order_by('-nb_achats')
            elif type_rapport == "frequence_achat":
                context['frequence_achat'] = ventes.values('client_nom').annotate(
                    nb_achats=Count('id')
                )
            elif type_rapport == "valeur_client":
                context['valeur_client'] = ventes.values('client_nom').annotate(
                    total_depense=Sum('montant_total')
                )

        else:
            return JsonResponse({"html": "<p>Aucun rapport disponible</p>"})

        template = self.RAPPORTS.get(type_rapport, {}).get("template")
        if not template:
            return JsonResponse({"html": "<p>Template manquant pour ce rapport</p>"})

        html = render_to_string(template, context, request=request)
        return JsonResponse({"html": html})
    
    
from django.db.models import Sum, F, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from django.views import View
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML

from django.db.models import Sum, F, Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Vente, LigneVente, Produit, MouvementStock, Achat

def get_context_filtre(request, type_rapport):
    """
    Retourne le contexte filtré pour tous les types de rapports,
    uniformisé pour correspondre au web.
    """
    magasin = getattr(request.user, "magasin", None)
    utilisateur_id = request.GET.get("utilisateur")
    date_debut = request.GET.get("date_debut")
    date_fin = request.GET.get("date_fin")
    jour = request.GET.get("jour")

    # Base QuerySets
    ventes = Vente.objects.all()
    lignes = LigneVente.objects.all()
    produits = Produit.objects.all()
    mouvements = MouvementStock.objects.all()
    achats = Achat.objects.all()

    # ======== FILTRES ========
    if magasin:
        ventes = ventes.filter(magasin=magasin)
        lignes = lignes.filter(vente__magasin=magasin)
        produits = produits.filter(magasin=magasin)
        mouvements = mouvements.filter(magasin=magasin)
        achats = achats.filter(magasin=magasin)

    if utilisateur_id:
        ventes = ventes.filter(cree_par_id=utilisateur_id)
        lignes = lignes.filter(vente__cree_par_id=utilisateur_id)
        mouvements = mouvements.filter(cree_par_id=utilisateur_id)
        achats = achats.filter(cree_par_id=utilisateur_id)

    if jour:
        try:
            jour_date = datetime.strptime(jour, "%Y-%m-%d").date()
            debut = datetime.combine(jour_date, datetime.min.time(), tzinfo=timezone.get_current_timezone())
            fin = datetime.combine(jour_date, datetime.max.time(), tzinfo=timezone.get_current_timezone())
            ventes = ventes.filter(date_creation__range=(debut, fin))
            lignes = lignes.filter(vente__date_creation__range=(debut, fin))
            mouvements = mouvements.filter(date_creation__range=(debut, fin))
            achats = achats.filter(date_creation__range=(debut, fin))
        except ValueError:
            pass

    if date_debut:
        debut = datetime.strptime(date_debut, "%Y-%m-%d")
        ventes = ventes.filter(date_creation__date__gte=debut)
        lignes = lignes.filter(vente__date_creation__date__gte=debut)
        mouvements = mouvements.filter(date_creation__date__gte=debut)
        achats = achats.filter(date_creation__date__gte=debut)

    if date_fin:
        fin = datetime.strptime(date_fin, "%Y-%m-%d")
        ventes = ventes.filter(date_creation__date__lte=fin)
        lignes = lignes.filter(vente__date_creation__date__lte=fin)
        mouvements = mouvements.filter(date_creation__date__lte=fin)
        achats = achats.filter(date_creation__date__lte=fin)

    # ======== CONTEXT INITIAL ========
    context = {
        "magasin": magasin,
        "data": [],
        "total_jour": 0,
        "message_vide": "",
        "type_rapport": type_rapport
    }

    # ======== INFOS HEADER / FOOTER POUR PDF ========
    gerant = Utilisateur.objects.filter(
            magasin=magasin,
            role="GERANT"
        ).first()
    theme = getattr(magasin, "theme", None)
    
    if theme and theme.logo:
        context["logo_magasin"] = request.build_absolute_uri(theme.logo.url)
    else:
        context["logo_magasin"] = ""
        
    context.update({
        "base_url": request.build_absolute_uri("/"),
        "nom_directeur": f"{gerant.first_name} {gerant.last_name}" if gerant else "",
        "nom_magasin": magasin.nom if magasin else "",        
        "adresse_magasin": magasin.adresse if magasin else "",
        "ville_magasin": magasin.ville if magasin else "",
        "pays_magasin": magasin.pays if magasin else "",
        "telephone_magasin": magasin.telephone if magasin else "",
        "email_magasin": magasin.email if magasin else "",

        "periode": f"{date_debut or 'Début'} → {date_fin or 'Fin'}",

        "date_generation": timezone.now(),

        "utilisateur_generation": request.user.username,

        "page_title": type_rapport.replace("_", " ").capitalize(),
    })

    # ======== RAPPORTS PRODUITS ========
    if type_rapport == "produits_vendus":
        context["data"] = lignes.values("produit__nom", "prix_unitaire").annotate(
            quantite_totale=Sum("quantite"),
            total_ventes=Sum("total")
        ).order_by("-quantite_totale")
        context["total_jour"] = context["data"].aggregate(Sum("total_ventes"))["total_ventes__sum"] or 0

    elif type_rapport == "produits_expire":
        context["data"] = list(
            produits.filter(date_expiration__lt=timezone.now())
                    .values("nom", "quantite_stock", "date_expiration")
        )

    elif type_rapport == "produits_proches_peremption":
        context["data"] = list(
            produits.filter(date_expiration__lte=timezone.now() + timedelta(days=7))
                    .values(
                        "nom",
                        "date_fabrication",
                        "date_expiration",
                        "quantite_stock"
                    )
        )

    elif type_rapport == "produits_jamais_vendus":
        context["data"] = list(
            produits.exclude(id__in=LigneVente.objects.values_list("produit_id", flat=True))
                    .values("nom", "quantite_stock", "prix_vente")
        )

    elif type_rapport == "produits_reapprovisionnement":
        context["data"] = list(
            produits.filter(quantite_stock__lte=F("seuil_alerte"))
                    .values("nom", "quantite_stock", "prix_vente")
        )

    elif type_rapport == "rotation_stock":
        context["data"] = lignes.values("produit__nom").annotate(
            total_vendu=Sum("quantite"),
            stock_actuel=F("produit__quantite_stock")
        ).order_by("-total_vendu")

    elif type_rapport == "produits_plus_rentables":
        lignes_marge = lignes.annotate(
            marge=(F("prix_unitaire") - F("produit__prix_achat")) * F("quantite")
        )
        context["data"] = lignes_marge.values("produit__nom", "produit__prix_achat", "prix_unitaire").annotate(
            total_marge=Sum("marge"), quantite=Sum("quantite")
        ).order_by("-total_marge")[:10]

    # ======== RAPPORTS VENTES ========
    elif type_rapport == "produits_plus_vendus":
        context["data"] = lignes.values("produit__nom").annotate(
            quantite=Sum("quantite")
        ).order_by("-quantite")[:10]

    elif type_rapport == "performance_caissier":
        context["data"] = ventes.values("cree_par__username").annotate(
            total_ventes=Sum("montant_total"),
            nb_ventes=Count("id"),
            ventes_annulees=Count("id", filter=Q(statut="ANNULEE"))
        ).order_by("-total_ventes")

    elif type_rapport == "chiffres_cles":
        total_ventes = ventes.aggregate(total=Sum("montant_total"))["total"] or 0
        total_tva = ventes.aggregate(tva=Sum("montant_tva"))["tva"] or 0
        total_remises = ventes.aggregate(remise=Sum("remise"))["remise"] or 0
        nb_ventes = ventes.count()
        panier_moyen = (total_ventes / nb_ventes) if nb_ventes else 0

        # Bénéfice = total ventes - total achats
        total_benefice = 0
        for vente in ventes.prefetch_related("lignes"):
            for ligne in vente.lignes.all():
                total_benefice += (ligne.prix_unitaire - ligne.produit.prix_achat) * ligne.quantite

        ventes_annulees = ventes.filter(statut="ANNULEE").count()

        context["data"] = [
            {
                "Chiffre d'affaires": total_ventes,
                "TVA collectée": total_tva,
                "Remises appliquées": total_remises,
                "Panier moyen": round((total_ventes / nb_ventes) if nb_ventes else 0, 0),
                "Bénéfice total": total_benefice,
                "Ventes annulées": ventes_annulees
            }
        ]

    elif type_rapport == "ventes_annulees":
        context["data"] = ventes.filter(statut=True)

    elif type_rapport == "ventes_par_categorie":
        context["data"] = lignes.values("produit__categorie__nom").annotate(
            total_ventes=Sum("total"),
            nombre_ventes=Count("vente_id", distinct=True)
        )

    elif type_rapport == "ventes_par_mode_paiement":
        context["data"] = ventes.values("mode_paiement").annotate(
            total_ventes=Sum("montant_total"),
            nb_ventes=Count("id")
        )

    elif type_rapport == "ventes_par_client":
        context["data"] = ventes.values("client_nom").annotate(
            total_ventes=Sum("montant_total"),
            nb_ventes=Count("id")
        ).order_by("-total_ventes")

    # ======== RAPPORTS STOCK ========
    elif type_rapport == "stock_actuel":
        context["data"] = produits.values("nom", "quantite_stock", "prix_vente")

    elif type_rapport == "mouvements_stock":
        context["data"] = mouvements.order_by("-date_creation").values(
            "produit__nom", "quantite", "type_mouvement", "date_creation"
        )
        context["data_columns"] = ["produit__nom", "quantite", "type_mouvement", "date_creation"]

    elif type_rapport == "valeur_stock":
        context["data"] = produits.annotate(
            valeur=F("quantite_stock") * F("prix_achat")
        ).values("nom", "quantite_stock", "prix_achat", "valeur")
        context["data_columns"] = ["nom", "quantite_stock", "prix_achat", "valeur"]
        
    # ======== RAPPORTS FOURNISSEURS ========
    elif type_rapport == "achats_par_fournisseur":
        # Nom + prénom du fournisseur dans une seule colonne
        context["data"] = achats.annotate(
            fournisseur_nom_complet=Concat(
                F("fournisseur__nom"), Value(" "), F("fournisseur__prenom")
            )
        ).values(
            "fournisseur_nom_complet"
        ).annotate(
            total_achats=Sum("montant_total"),
            nb_achats=Count("id")
        ).order_by("-total_achats")


    elif type_rapport == "delai_livraison_fournisseur":
        # On suppose que date_livraison existe sinon on peut utiliser date_creation
        # Exemple: ici on met juste 0 pour éviter erreur, à adapter si date_livraison existe
        context["data"] = Achat.objects.values(
            fournisseur_nom_complet=Concat(
                F("fournisseur__nom"),
                Value(" "),
                F("fournisseur__prenom")
            )
        ).annotate(
            # Si date_livraison existe : F("date_livraison") - F("date_creation")
            delai_moyen=Avg(
                ExpressionWrapper(
                    F("date_creation") - F("date_creation"),  # temporaire
                    output_field=DurationField()
                )
            )
        )

    elif type_rapport == "historique_prix_fournisseur":
        context["data"] = LigneAchat.objects.values(
            fournisseur_nom_complet=Concat(
                F("achat__fournisseur__nom"),
                Value(" "),
                F("achat__fournisseur__prenom")
            ),
            produit_nom=F("produit__nom"),
            prix_unitaire_achat=F("prix_unitaire"),  # renommer pour éviter conflit
            numero_facture=F("achat__numero_facture")
        )
    
    # ======== RAPPORTS FINANCES ========
    elif type_rapport == "ca_par_categorie":
        context["data"] = lignes.values("produit__categorie__nom").annotate(
            total_ca=Sum("total")
        )

    elif type_rapport == "marge_par_produit":
        lignes_marge = lignes.annotate(
            marge=(F("prix_unitaire") - F("produit__prix_achat")) * F("quantite")
        )
        context["data"] = lignes_marge.values(
            "produit__nom", "prix_unitaire", "produit__prix_achat"
        ).annotate(
            total_marge=Sum("marge"), quantite=Sum("quantite")
        )

    elif type_rapport == "panier_moyen":
        panier_clients = ventes.values("cree_par__username").annotate(
            total_ca=Sum("montant_total"), nb_ventes=Count("id")
        )
        context["data"] = [
            {
                "caissier": p["cree_par__username"],
                "panier_moyen": (p["total_ca"] or 0) / (p["nb_ventes"] or 1)
            }
            for p in panier_clients
        ]

    # ======== RAPPORTS CLIENTS ========
    elif type_rapport == "clients_fideles":
        context["data"] = ventes.values("client_nom").annotate(
            nb_achats=Count("id")
        ).order_by("-nb_achats")

    elif type_rapport == "frequence_achat":
        context["data"] = ventes.values("client_nom").annotate(
            nb_achats=Count("id")
        )

    elif type_rapport == "valeur_client":
        context["data"] = ventes.values("client_nom").annotate(
            total_depense=Sum("montant_total")
        ).order_by("-total_depense")

    # ======== MESSAGE VIDE ========
    if not context["data"]:
        messages_generiques = {
            "produits_vendus": "Aucun produit vendu",
            "produits_expire": "Aucun produit expiré",
            "produits_proches_peremption": "Aucun produit proche de la date d'expiration",
            "produits_jamais_vendus": "Tous les produits ont été vendus au moins une fois",
            "produits_reapprovisionnement": "Aucun produit à réapprovisionner",
            "rotation_stock": "Aucune vente enregistrée",
            "produits_plus_rentables": "Aucune vente pour calculer la rentabilité",
            "produits_plus_vendus": "Aucun produit vendu",
            "performance_caissier": "Aucune vente enregistrée",
            "chiffres_cles": "Aucune donnée de vente",
            "ventes_annulees": "Aucune vente annulée",
            "ventes_par_categorie": "Aucune vente par catégorie",
            "ventes_par_mode_paiement": "Aucune vente par mode de paiement",
            "ventes_par_client": "Aucune vente par client",
            "stock_actuel": "Aucun produit en stock",
            "mouvements_stock": "Aucun mouvement de stock",
            "valeur_stock": "Aucune valeur de stock",
            "achats_par_fournisseur": "Aucun achat par fournisseur",
            "delai_livraison_fournisseur": "Aucun délai de livraison",
            "historique_prix_fournisseur": "Aucun historique de prix",
            "ca_par_categorie": "Aucun chiffre d'affaires",
            "marge_par_produit": "Aucune marge calculable",
            "panier_moyen": "Aucun panier moyen calculable",
            "clients_fideles": "Aucun client fidèle",
            "frequence_achat": "Aucune fréquence d'achat",
            "valeur_client": "Aucune valeur client calculable",
        }
        context["message_vide"] = messages_generiques.get(type_rapport, "Aucune donnée disponible")
        
    return context


class ExportRapportPDFView(View):
    """
    Vue pour exporter n'importe quel rapport filtré en PDF.
    """
    def get(self, request):
        type_rapport = request.GET.get("type_rapport")
        if not type_rapport:
            return HttpResponse("Type de rapport manquant", status=400)

        # Récupération du contexte filtré
        context = get_context_filtre(request, type_rapport)

        # Couleur principale
        context["couleur_principale"] = (
            context["magasin"].theme.couleur_principale
            if context["magasin"] and hasattr(context["magasin"], "theme")
            else "#3b82f6"
        )
        context["mode"] = "pdf"   # 👈 IMPORTANT
        # Rendu PDF
        html_string = render_to_string("rapports/pdf_template.html", context)
        pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{type_rapport}.pdf"'
        return response
            
class PrintRapportView(View):
    def get(self, request):
        type_rapport = request.GET.get("type_rapport")
        if not type_rapport:
            return HttpResponse("Type de rapport manquant", status=400)

        context = get_context_filtre(request, type_rapport)

        # 🔥 AJOUT MANQUANT
        context["couleur_principale"] = (
            context["magasin"].theme.couleur_principale
            if context.get("magasin") and hasattr(context["magasin"], "theme")
            else "#3b82f6"
        )

        context["mode"] = "print"

        return render(request, "rapports/pdf_template.html", context)     
                   
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Utilisateur


@login_required
def gerant_liste(request):
    
    magasin = request.user.magasin

    utilisateurs = Utilisateur.objects.filter(magasin=magasin)

    search = request.GET.get("search", "")
    role = request.GET.get("role", "")

    # recherche nom ou téléphone
    if search:
        utilisateurs = utilisateurs.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(telephone__icontains=search)
        )

    # filtre rôle
    if role:
        utilisateurs = utilisateurs.filter(role=role)

    utilisateurs = utilisateurs.order_by("role", "username")

    paginator = Paginator(utilisateurs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "magasin": magasin,
        "utilisateurs": page_obj,
        "page_obj": page_obj,
        "filters": {
            "search": search,
            "role": role
        }
    }

    return render(request, "gerant/utilisateurs_liste.html", context)

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import UtilisateurForm
from .models import Utilisateur

from django.db import transaction
from supermarcher.signals import log_action

@login_required
def gerant_create(request):
    magasin = request.user.magasin

    if request.method == 'POST':
        form = UtilisateurForm(request.POST)

        if form.is_valid():
            data = form.cleaned_data

            user = Utilisateur.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                telephone=data['telephone'],
                role='CAISSIER',
                magasin=magasin,
                is_active=True
            )

            transaction.on_commit(lambda: log_action(
                action="CREATE",
                modele="Utilisateur",
                objet_id=user.id,
                description=f"Création caissier {user.username}"
            ))

            messages.success(request, "Caissier créé avec succès.")
            return redirect('gerant_liste')

        else:
            messages.error(request, "Erreur : vérifiez les informations.")

    else:
        form = UtilisateurForm()

    return render(request, 'gerant/utilisateur_form.html', {
        'form': form,
        'magasin': magasin
    })

from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseForbidden
from .forms import UtilisateurForm
from .models import Utilisateur

from django.db import transaction
from supermarcher.signals import log_action

@login_required
def gerant_update(request, pk):
    magasin = request.user.magasin

    utilisateur = get_object_or_404(
        Utilisateur,
        pk=pk,
        magasin=magasin
    )

    if utilisateur.role != 'CAISSIER':
        return HttpResponseForbidden("Action non autorisée")

    form = UtilisateurForm(instance=utilisateur)

    if request.method == 'POST':
        form = UtilisateurForm(request.POST, instance=utilisateur)

        if form.is_valid():

            # 🧠 aucune modification
            if not form.has_changed():
                messages.info(request, "Aucune modification effectuée.")
                return redirect('gerant_liste')

            user = form.save(commit=False)

            user.role = 'CAISSIER'
            user.magasin = magasin

            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)

            user.save()

            transaction.on_commit(lambda: log_action(
                action="UPDATE",
                modele="Utilisateur",
                objet_id=user.id,
                description=f"Modification caissier {user.username}"
            ))

            messages.success(request, "Caissier modifié avec succès.")
            return redirect('gerant_liste')

        else:
            messages.error(request, "Erreur : vérifiez les champs.")

    return render(request, 'gerant/utilisateur_form.html', {
        'form': form,
        'magasin': magasin
    })

from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseForbidden
from .models import Utilisateur

from django.db import transaction
from supermarcher.signals import log_action
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render, redirect

@login_required
def gerant_delete(request, pk):
    magasin = request.user.magasin
    utilisateur = get_object_or_404(Utilisateur, pk=pk, magasin=magasin)

    # 🔒 Vérifier rôle
    if utilisateur.role != 'CAISSIER':
        return HttpResponseForbidden("Impossible de supprimer cet utilisateur")

    # 🔒 Vérifier qu'il n'a pas d'opérations
    if utilisateur.operations.exists():
        return render(request, 'gerant/utilisateur_cannot_delete.html', {
            'object': utilisateur
        })

    if request.method == 'POST':

        user_id = utilisateur.id
        username = utilisateur.username

        transaction.on_commit(lambda: log_action(
            action="DELETE",
            modele="Utilisateur",
            objet_id=user_id,
            description=f"Suppression caissier {username}"
        ))

        utilisateur.delete()

        return redirect('gerant_liste')

    return render(request, 'gerant/utilisateur_confirm_delete.html', {
        'object': utilisateur
    })
    
# views.py
from django.shortcuts import render, get_object_or_404
from .models import Utilisateur, Achat, Vente, MouvementStock

def gerant_detail(request, pk):
    utilisateur = get_object_or_404(Utilisateur, pk=pk)

    # Récupérer les dernières opérations (limit 5) côté serveur
    derniers_achats = Achat.objects.filter(cree_par=utilisateur).order_by('-date_creation')[:5]
    dernieres_ventes = Vente.objects.filter(cree_par=utilisateur).order_by('-date_creation')[:5]
    derniers_mouvements = MouvementStock.objects.filter(cree_par=utilisateur).order_by('-date_creation')[:5]

    context = {
        'utilisateur': utilisateur,
        'derniers_achats': derniers_achats,
        'dernieres_ventes': dernieres_ventes,
        'derniers_mouvements': derniers_mouvements,
        'magasin': utilisateur.magasin
    }
    return render(request, 'gerant/utilisateur_detail.html', context)
    
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Magasin, ThemeMagasin
from .forms import MagasinForm, ThemeMagasinForm


@login_required
def parametres(request):

    magasin = request.user.magasin

    theme, created = ThemeMagasin.objects.get_or_create(
        magasin=magasin,
        defaults={"couleur_principale": "#16a34a"}
    )

    # ✅ TOUJOURS définir les forms
    form_magasin = MagasinForm(instance=magasin)
    form_theme = ThemeMagasinForm(instance=theme)
    
    if request.method == "POST":

        form_magasin = MagasinForm(request.POST, instance=magasin)
        form_theme = ThemeMagasinForm(request.POST, request.FILES, instance=theme)

        if form_magasin.is_valid() and form_theme.is_valid():

            # 🔥 sécurité anti désactivation accidentelle
            magasin_obj = form_magasin.save(commit=False)
            magasin_obj.actif = magasin.actif
            magasin_obj.save()

            theme_obj = form_theme.save(commit=False)

            if not theme_obj.couleur_principale:
                theme_obj.couleur_principale = "#16a34a"

            theme_obj.save()

            return redirect("parametres")

    return render(request, "gerant/parametres.html", {
        "magasin": magasin,
        "theme": theme,
        "form_magasin": form_magasin,
        "form_theme": form_theme,
    })

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

@login_required
def toggle_dark_mode(request):

    magasin = request.user.magasin
    theme = magasin.theme

    theme.mode_sombre = not theme.mode_sombre
    theme.save()

    return JsonResponse({
        "dark": theme.mode_sombre
    })
    
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q

@login_required
def categories_liste(request):
    magasin = request.user.magasin

    # Récupérer les catégories du magasin
    categories = magasin.categories.all()

    # Annoter le nombre de produits par catégorie
    categories = categories.annotate(nb_produits=Count('produit'))

    # ===== FILTRES =====
    search = request.GET.get("search")
    min_produits = request.GET.get("min_produits")
    max_produits = request.GET.get("max_produits")
    statut = request.GET.get("statut")
    tri = request.GET.get("tri")

    if search:
        categories = categories.filter(
            Q(nom__icontains=search) |
            Q(description__icontains=search)
        )

    if min_produits:
        categories = categories.filter(nb_produits__gte=int(min_produits))

    if max_produits:
        categories = categories.filter(nb_produits__lte=int(max_produits))

    if statut == "avec":
        categories = categories.filter(nb_produits__gt=0)
    elif statut == "vide":
        categories = categories.filter(nb_produits=0)

    if tri in ["nom", "-nom", "nb_produits", "-nb_produits"]:
        categories = categories.order_by(tri)
    else:
        categories = categories.order_by("nom")

    return render(request, 'gerant/categories_liste.html', {
        'categories': categories,
        'magasin': magasin,
        'filters': {
            'search': search or '',
            'min_produits': min_produits or '',
            'max_produits': max_produits or '',
            'statut': statut or '',
            'tri': tri or ''
        }
    })

from .forms import CategorieForm
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from supermarcher.signals import log_action

@login_required
def categorie_nouvelle(request):
    magasin = request.user.magasin

    if request.method == 'POST':
        form = CategorieForm(request.POST, magasin=magasin)

        if form.is_valid():
            categorie = form.save(commit=False)
            categorie.magasin = magasin
            categorie.save()

            transaction.on_commit(lambda: log_action(
                action="CREATE",
                modele="Categorie",
                objet_id=categorie.id,
                description=f"Création catégorie {categorie.nom}"
            ))

            messages.success(request, "Catégorie ajoutée avec succès.")
            return redirect('categories_liste')

        else:
            # 🔥 ERREUR GLOBALE TOAST
            messages.error(request, "Cette catégorie existe déjà ou est invalide.")

    else:
        form = CategorieForm(magasin=magasin)

    return render(request, 'gerant/categorie_form.html', {
        'form': form,
        'titre': "Nouvelle catégorie",
        'magasin': magasin
    })
    
@login_required
def categorie_modifier(request, pk):
    magasin = request.user.magasin

    categorie = get_object_or_404(
        Categorie,
        pk=pk,
        magasin=magasin
    )

    if request.method == 'POST':
        form = CategorieForm(request.POST, instance=categorie, magasin=magasin)

        if form.is_valid():
            categorie = form.save()

            transaction.on_commit(lambda: log_action(
                action="UPDATE",
                modele="Categorie",
                objet_id=categorie.id,
                description=f"Modification catégorie {categorie.nom}"
            ))

            messages.success(request, "Catégorie modifiée avec succès.")
            return redirect('categories_liste')

        else:
            messages.error(request, "Erreur : catégorie déjà existante ou invalide.")

    else:
        form = CategorieForm(instance=categorie)

    return render(request, 'gerant/categorie_form.html', {
        'form': form,
        'titre': "Modifier la catégorie",
        'magasin': magasin
    })
    
from django.db import transaction
from supermarcher.signals import log_action

@login_required
def categorie_supprimer(request, pk):
    magasin = request.user.magasin

    categorie = get_object_or_404(
        Categorie,
        pk=pk,
        magasin=magasin
    )

    if categorie.produit_set.exists():
        messages.error(
            request,
            "Impossible de supprimer : cette catégorie contient des produits."
        )
        return redirect('categories_liste')

    if request.method == 'POST':

        cat_id = categorie.id
        cat_nom = categorie.nom

        transaction.on_commit(lambda: log_action(
            action="DELETE",
            modele="Categorie",
            objet_id=cat_id,
            description=f"Suppression catégorie {cat_nom}"
        ))

        categorie.delete()

        messages.success(request, "Catégorie supprimée.")
        return redirect('categories_liste')

    return render(request, 'gerant/categorie_confirm_delete.html', {
        'categorie': categorie
    })

#====================================================

def rapport_journalier(request):
    # Récupération du magasin connecté
    magasin = request.user.magasin

    # Date ciblée
    jour_str = request.GET.get('jour')
    if jour_str:
        jour = datetime.strptime(jour_str, "%Y-%m-%d").date()
    else:
        jour = datetime.today().date()

    debut_jour = datetime.combine(jour, datetime.min.time())
    fin_jour = datetime.combine(jour, datetime.max.time())

    # --------------------------
    # RAPPORT VENTES
    # --------------------------
    ventes = Vente.objects.filter(magasin=magasin, date_creation__range=(debut_jour, fin_jour))

    # 🔒 Filtrer par caissier si l'utilisateur connecté est un CAISSIER
    if request.user.role == 'CAISSIER':
        ventes = ventes.filter(cree_par=request.user)

    total_ventes = ventes.count()
    montant_total = ventes.aggregate(
        total=Sum(F('sous_total') + F('montant_tva') - F('remise'))
    )['total'] or 0

    produits_vendus = LigneVente.objects.filter(vente__in=ventes)\
        .values('produit__nom')\
        .annotate(quantite=Sum('quantite'))\
        .order_by('-quantite')

    mode_paiement = ventes.values('mode_paiement').annotate(
        total=Sum(F('sous_total') + F('montant_tva') - F('remise'))
    )

    performance_caissier = ventes.values('cree_par__username').annotate(
        total_ventes=Count('id'),
        montant_total=Sum(F('sous_total') + F('montant_tva') - F('remise'))
    )

    # --------------------------
    # RAPPORT PRODUITS
    # --------------------------
    produits_stock_faible = Produit.objects.filter(magasin=magasin, quantite_stock__lte=5)
    produits_jamais_vendus = Produit.objects.filter(magasin=magasin)\
        .exclude(lignevente__vente__in=ventes)  # utiliser le queryset filtré par caissier

    produits_plus_vendus = produits_vendus[:10]

    # --------------------------
    # RAPPORT FINANCES
    # --------------------------
    panier_moyen = ventes.aggregate(
        panier_moyen=Sum(F('sous_total') + F('montant_tva') - F('remise')) / Count('id')
    )['panier_moyen'] or 0

    marge_par_produit = LigneVente.objects.filter(vente__in=ventes)\
        .values('produit__nom')\
        .annotate(marge=Sum(F('prix_unitaire') - F('produit__prix_achat')))

    context = {
        'magasin': magasin,
        'jour': jour,
        'total_ventes': total_ventes,
        'montant_total': montant_total,
        'produits_vendus': produits_vendus,
        'mode_paiement': mode_paiement,
        'performance_caissier': performance_caissier,
        'produits_stock_faible': produits_stock_faible,
        'produits_jamais_vendus': produits_jamais_vendus,
        'produits_plus_vendus': produits_plus_vendus,
        'panier_moyen': panier_moyen,
        'marge_par_produit': marge_par_produit,
    }
    return render(request, "gerant/rapport_journalier.html", context)