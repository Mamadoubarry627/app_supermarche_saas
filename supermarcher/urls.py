from django.conf import settings
from django.urls import path
from . import views
from django.conf.urls.static import static

urlpatterns = [
    path('', views.connexion, name='connexion'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path("inactive/", views.inactive_user_view, name="inactive_user"),
    
    path('dashboard/superadmin/', views.dashboard_superadmin, name='dashboard_superadmin'),
    path('superadmin/utilisateurs/', views.gestion_utilisateurs, name='gestion_utilisateurs'),
    path('superadmin/magasins/creer/', views.creer_magasin, name='creer_magasin'),
    path("magasin/<int:id>/", views.voir_magasin, name="voir_magasin"),
    path("magasin/<int:id>/modifier/", views.modifier_magasin, name="modifier_magasin"),
    path("magasin/<int:id>/toggle/", views.toggle_magasin, name="toggle_magasin"),
    path("magasin/<int:id>/supprimer/", views.supprimer_magasin, name="supprimer_magasin"),
    path("utilisateur/<int:id>/", views.voir_utilisateur, name="voir_utilisateur"),
    path("utilisateur/ajouter/", views.ajouter_utilisateur, name="ajouter_utilisateur"),
    path("utilisateur/modifier/<int:id>/", views.modifier_utilisateur, name="modifier_utilisateur"),
    path("utilisateur/toggle/<int:id>/", views.toggle_utilisateur, name="toggle_utilisateur"),
     path("superadmin/audit-logs/", views.AuditLogListView.as_view(), name="audit_logs"),
    
# ================================================================================================  
    path("ventes/<int:vente_id>/", views.vente_detail, name="vente_detail"),
    path("ventes/<int:vente_id>/imprimer/", views.vente_recu_html, name="vente_recu_html"),
    path("ventes/<int:vente_id>/supprimer/", views.vente_delete, name="vente_delete"),
    path('produits/', views.produits_liste, name='produits_liste'),
    path('produit/<int:pk>/', views.produit_detail, name='produit_detail'),
    path('produit/<int:pk>/edit/', views.produit_edit, name='produit_edit'),
    path('produit/<int:pk>/delete/', views.produit_delete, name='produit_delete'),
    path('produit/nouveau/', views.produit_nouveau, name='produit_nouveau'),
    path('rapports/journalier/', views.rapport_journalier, name='rapport_journalier'),
  
    path('dashboard/', views.dashboard_gerant, name='dashboard_gerant'),
    path('ventes/', views.ventes_liste, name='ventes_liste'),
    path('achats/', views.achats_liste, name='achats_liste'),
    
    path('stock/', views.stock_mouvements, name='stock_mouvements'),
    path('fournisseurs/', views.fournisseurs_liste, name='fournisseurs_liste'),
    path('rapports/', views.DashboardGlobalView.as_view(), name='rapports'),
    path('rapports/ajax/', views.RapportAjaxView.as_view(), name='rapports_ajax'),
    path("rapports/export/pdf/", views.ExportRapportPDFView.as_view(), name="export_rapport_pdf"),
    path('gerant/', views.gerant_liste, name='gerant_liste'),
    path('gerant/nouveau/', views.gerant_create, name='create'),
    path('gerant/<int:pk>/modifier/', views.gerant_update, name='update'),
    path('gerant/<int:pk>/supprimer/', views.gerant_delete, name='delete'),
    path('gerant/<int:pk>/', views.gerant_detail, name='detail'),
    path("toggle-dark-mode/", views.toggle_dark_mode, name="toggle_dark_mode"),
    
    path('parametres/', views.parametres, name='parametres'),
    path('categories/', views.categories_liste, name='categories_liste'),
    path('categories/nouveau/', views.categorie_nouvelle, name='categorie_nouvelle'),
    path('categories/<int:pk>/modifier/', views.categorie_modifier, name='categorie_modifier'),
    path('categories/<int:pk>/supprimer/', views.categorie_supprimer, name='categorie_supprimer'),
    path('fournisseurs/nouveau/', views.fournisseur_nouveau, name='fournisseur_nouveau'),
    path('fournisseurs/<int:pk>/voir/', views.fournisseur_voir, name='fournisseur_voir'),
    path('fournisseurs/<int:pk>/modifier/', views.fournisseur_modifier, name='fournisseur_modifier'),
    path('fournisseurs/<int:pk>/supprimer/', views.fournisseur_supprimer, name='fournisseur_supprimer'),
    path('achats/nouveau/', views.ajouter_achat, name='achat_nouveau'),
    path('achats/<int:pk>/voir/', views.achat_voir, name='achat_voir'),
    path('achats/<int:pk>/supprimer/', views.achat_supprimer, name='achat_supprimer'),
    path('achats/<int:pk>/annuler/', views.achat_annuler, name='achat_annuler'),
    path('ventes/nouvelle/', views.vente_create, name='vente_create'),
    path('ventes/pdf/', views.ventes_pdf, name='ventes_pdf'),
    path("produit/barcode/<str:code>/", views.produit_par_barcode, name="produit_par_barcode"),
    path("ventes/<int:pk>/ticket/", views.ticket_pdf, name="ticket_pdf"),
    path('produit/modifier/<int:produit_id>/', views.produit_modifier_ajax, name='produit_modifier_ajax'),

]

from .api.views import ProduitListAPIView, ScanAPIView, MyTokenObtainPairView, ThemeMagasinView
from rest_framework_simplejwt.views import TokenRefreshView
#api_market/urls.py
urlpatterns += [
    # 🔐 Auth JWT
    path('api/token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    #path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # 📷 Scanner
    path('api/scan/', ScanAPIView.as_view(), name='api_scan'),
    path('api/produits/', ProduitListAPIView.as_view(), name='api_produits'),
    
    #Theme
    path('api/magasins/<int:magasin_id>/theme/', ThemeMagasinView.as_view(), name='magasins_theme'),
]

from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)