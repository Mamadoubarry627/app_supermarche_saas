from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from supermarcher.models import Produit, ThemeMagasin
from rest_framework.exceptions import AuthenticationFailed
from datetime import date

class ScanAPIView(APIView):
    """
    Endpoint pour scanner un produit via son code-barres.
    Retourne un status 'found' ou 'not_found' pour Flutter.
    """
    
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = request.data.get("code_barre", "").strip()

        if not code:
            return Response({
                "type": "scan",
                "success": False,
                "reason": "missing_code",
                "message": "Code-barres manquant"
            }, status=400)

        user = request.user

        try:
            magasin = user.magasin
        except AttributeError:
            return Response({
                "type": "scan",
                "success": False,
                "reason": "no_store",
                "message": "Utilisateur sans magasin"
            }, status=400)

        produit = Produit.objects.filter(
            magasin=magasin,
            code_barre=code
        ).first()

        # ❌ introuvable
        if not produit:
            return Response({
                "type": "scan",
                "success": False,
                "reason": "not_found",
                "message": f"Produit introuvable ({code})"
            }, status=404)

        # ❌ inactif
        if not produit.actif:
            return Response({
                "type": "scan",
                "success": False,
                "reason": "inactive",
                "message": "Produit inactif ❌"
            }, status=400)

        # ❌ expiré
        if produit.date_expiration and produit.date_expiration < date.today():
            return Response({
                "type": "scan",
                "success": False,
                "reason": "expired",
                "message": "Produit expiré ❌"
            }, status=400)

        # ❌ stock vide
        if produit.quantite_stock <= 0:
            return Response({
                "type": "scan",
                "success": False,
                "reason": "out_of_stock",
                "message": "Stock épuisé ❌"
            }, status=400)

        # ✅ OK
        return Response({
            "type": "scan",
            "success": True,
            "id": produit.id,
            "nom": produit.nom,
            "prix": float(produit.prix_vente),
            "stock": produit.quantite_stock,
            "taux_tva": float(produit.taux_tva),
            "code_barre": produit.code_barre
        })

class ProduitListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        magasin = request.user.magasin

        produits = Produit.objects.filter(magasin=magasin)

        data = []
        for p in produits:
            data.append({
                "id": p.id,
                "nom": p.nom,
                "code_barre": p.code_barre,
                "prix_vente": str(p.prix_vente),
                "prix_achat": str(p.prix_achat),
                "quantite_stock": p.quantite_stock,
                "taux_tva": str(p.taux_tva),
                "categorie": p.categorie.nom if p.categorie else "",
            })

        return Response(data)
    
# api_market/views.py
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .serializers import ThemeMagasinSerializer

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)

        user = self.user

        # 🚫 1. COMPTE DÉSACTIVÉ
        if not user.is_active:
            raise AuthenticationFailed("account_disabled")

        # 🚫 2. PAS DE MAGASIN
        if not user.magasin:
            raise AuthenticationFailed("no_store")

        # 🚫 3. MAGASIN DÉSACTIVÉ (UTILISE TON CHAMP actif)
        if not user.magasin.actif:
            raise AuthenticationFailed("store_disabled")

        # ✅ OK → retourner les infos
        data['id'] = user.id
        data['username'] = user.username
        data['first_name'] = user.first_name
        data['last_name'] = user.last_name
        data['role'] = user.role
        data['magasin_id'] = user.magasin.id
        data['magasin_nom'] = user.magasin.nom

        return data

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": getattr(user, "role", ""),
            "magasin": user.magasin.nom if user.magasin else None,  # ✅ FIX
            "magasin_id": user.magasin.id if user.magasin else None,  # ✅ AJOUT
        })
    
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone

class ThemeMagasinView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, magasin_id):
        theme = get_object_or_404(ThemeMagasin, magasin_id=magasin_id)

        return Response({
            "changed": True,
            "data": {
                "couleur_principale": theme.couleur_principale,
                "mode_sombre": theme.mode_sombre,
                "logo": theme.logo.url if theme.logo else None,
                "last_updated": timezone.now().isoformat()  # ✅ FIX
            }
        })