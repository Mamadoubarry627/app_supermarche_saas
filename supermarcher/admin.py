from urllib import request

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    AuditLog, Utilisateur, Magasin, Categorie, Produit,
    Fournisseur, Achat, LigneAchat,
    Vente, LigneVente, MouvementStock
)

# =====================================================
# UTILISATEUR
# =====================================================


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = (
        "username", "first_name", "last_name", "email",
        "telephone", "role", "magasin", "is_staff"
    )
    list_filter = ("role", "magasin", "is_staff", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "telephone")
    ordering = ("-date_creation",)
    readonly_fields = ("date_creation",)  # ← ajouté ici

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Infos personnelles", {"fields": ("first_name", "last_name", "email", "telephone")}),
        ("Magasin et rôle", {"fields": ("role", "magasin")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates importantes", {"fields": ("last_login", "date_creation")}),  # affiché en lecture seule
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "first_name", "last_name", "telephone", "role", "magasin", "password1", "password2"),
        }),
    )
    
    def get_readonly_fields(self, request, obj=None):
        if request.user.is_authenticated and request.user.role != 'SUPERADMIN':
            return self.readonly_fields + (
                "is_superuser",
                "is_staff",
                "groups",
                "user_permissions",
            )
        return self.readonly_fields
    
    def save_model(self, request, obj, form, change):
        if request.user.is_authenticated and request.user.role != 'SUPERADMIN':
            if obj.role == 'SUPERADMIN':
                raise PermissionError("Seul un SUPERADMIN peut créer un SUPERADMIN")
        super().save_model(request, obj, form, change)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_authenticated and request.user.role == 'SUPERADMIN':
            return qs
        return qs.filter(magasin=request.user.magasin)
    
    def has_change_permission(self, request, obj=None):
        if request.user.is_authenticated and request.user.role == 'SUPERADMIN':
            return True
        if obj and obj.magasin != request.user.magasin:
            return False
        return True
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role == 'SUPERADMIN'
    
    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.role in ['SUPERADMIN']
    

# =====================================================
# MAGASIN
# =====================================================

@admin.register(Magasin)
class MagasinAdmin(admin.ModelAdmin):
    list_display = ("nom", "proprietaire", "ville", "pays", "devise", "actif", "date_creation")
    list_filter = ("actif", "pays", "devise")
    search_fields = ("nom", "ville", "pays")
    prepopulated_fields = {"slug": ("nom",)}
    ordering = ("-date_creation",)


# =====================================================
# CATEGORIE
# =====================================================

@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "magasin")
    list_filter = ("magasin",)
    search_fields = ("nom",)


# =====================================================
# PRODUIT
# =====================================================

@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = (
        "nom", "magasin", "categorie",
        "prix_vente", "quantite_stock",
        "actif", "date_creation"
    )
    list_filter = ("magasin", "categorie", "actif")
    search_fields = ("nom", "code_barre", "sku")
    list_editable = ("prix_vente", "quantite_stock", "actif")
    ordering = ("-date_creation",)
    readonly_fields = ("date_creation", "date_modification")


# =====================================================
# FOURNISSEUR
# =====================================================

@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ("nom", "magasin", "telephone", "email", "date_creation")
    list_filter = ("magasin",)
    search_fields = ("nom", "telephone", "email")
    ordering = ("-date_creation",)


# =====================================================
# LIGNE ACHAT INLINE
# =====================================================

class LigneAchatInline(admin.TabularInline):
    model = LigneAchat
    extra = 1
    readonly_fields = ("total",)
    fields = ("produit", "quantite", "prix_unitaire", "total")


# =====================================================
# ACHAT
# =====================================================

@admin.register(Achat)
class AchatAdmin(admin.ModelAdmin):
    list_display = ("numero_facture", "magasin", "fournisseur", "montant_total", "statut", "date_creation")
    list_filter = ("statut", "magasin", "date_creation")
    search_fields = ("numero_facture",)
    inlines = [LigneAchatInline]
    ordering = ("-date_creation",)


# =====================================================
# LIGNE VENTE INLINE
# =====================================================

class LigneVenteInline(admin.TabularInline):
    model = LigneVente
    extra = 1
    readonly_fields = ("total",)
    fields = ("produit", "quantite", "prix_unitaire", "total")


# =====================================================
# VENTE
# =====================================================

@admin.register(Vente)
class VenteAdmin(admin.ModelAdmin):
    list_display = (
        "numero_facture", "magasin",
        "montant_total", "mode_paiement",
        "statut", "date_creation"
    )
    list_filter = ("statut", "mode_paiement", "magasin", "date_creation")
    search_fields = ("numero_facture", "client_nom")
    inlines = [LigneVenteInline]
    ordering = ("-date_creation",)


# =====================================================
# MOUVEMENT STOCK
# =====================================================

@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = (
        "produit", "magasin",
        "type_mouvement", "quantite",
        "reference", "date_creation"
    )
    list_filter = ("type_mouvement", "magasin", "date_creation")
    search_fields = ("produit__nom", "reference")
    ordering = ("-date_creation",)
    

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):

    list_display = ("utilisateur", "action", "modele", "objet_id", "date_action")

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.role == 'SUPERADMIN'

    def get_actions(self, request):
        if request.user.is_authenticated and request.user.role != 'SUPERADMIN':
            return None
        return super().get_actions(request)