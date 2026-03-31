from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from supermarcher.models import Produit, ThemeMagasin

class ScanAPIView(APIView):
    """
    Endpoint pour scanner un produit via son code-barres.
    Retourne un status 'found' ou 'not_found' pour Flutter.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = request.data.get("code_barre", "").strip()
        if not code:
            return Response({"status": "error", "detail": "Code-barres manquant"}, status=400)

        user = request.user

        # Suppose que l'utilisateur a un magasin associé
        try:
            magasin = user.magasin
        except AttributeError:
            return Response({"status": "error", "detail": "Utilisateur non associé à un magasin"}, status=400)

        # Recherche le produit dans ce magasin
        produit = Produit.objects.filter(magasin=magasin, code_barre=code).first()

        if produit:
            return Response({
                "status": "found",
                "id": produit.id,                 # ✅ AJOUT CRITIQUE
                "nom": produit.nom,
                "prix": str(produit.prix_vente),
                "quantite": produit.quantite_stock,
                "taux_tva": str(produit.taux_tva),  # (optionnel mais utile)
                "code_barre": produit.code_barre,   # (optionnel mais clean)
            })
        else:
            return Response({
                "status": "not_found",
                "detail": f"Produit introuvable pour le code-barres {code}"
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
        data['id'] = self.user.id   # ✅ C’EST ÇA QUI MANQUE
        # 🔥 Ajouter dans la réponse JSON
        data['username'] = self.user.username
        data['first_name'] = self.user.first_name
        data['last_name'] = self.user.last_name
        data['role'] = self.user.role
        # 🔥 AJOUT MAGASIN
        data['magasin'] = self.user.magasin.nom if self.user.magasin else None

        return data

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    
class ThemeMagasinView(APIView):

    def get(self, request, magasin_id):
        theme = ThemeMagasin.objects.get(magasin_id=magasin_id)
        serializer = ThemeMagasinSerializer(theme)
        return Response(serializer.data)