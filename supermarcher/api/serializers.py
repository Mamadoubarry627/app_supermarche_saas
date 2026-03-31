from rest_framework import serializers
from django.core.exceptions import ValidationError
from decimal import Decimal

from supermarcher.models import (
    Produit, Categorie, Fournisseur, Achat, LigneAchat, ThemeMagasin,
    Vente, LigneVente, Utilisateur
)
from supermarcher.services.achat_service import creer_achat
from supermarcher.services.vente_service import creer_vente

# -------------------
# PRODUIT
# -------------------
class ProduitSerializer(serializers.ModelSerializer):
    categorie = serializers.CharField(source='categorie.nom', read_only=True)

    class Meta:
        model = Produit
        fields = ['id', 'nom', 'code_barre', 'prix_vente', 'prix_achat', 'quantite_stock', 'taux_tva', 'categorie']
        read_only_fields = ['quantite_stock', 'prix_vente', 'prix_achat', 'taux_tva']


# -------------------
# LIGNE ACHAT
# -------------------
class LigneAchatSerializer(serializers.ModelSerializer):
    produit_id = serializers.PrimaryKeyRelatedField(
        queryset=Produit.objects.all(),
        source='produit'
    )

    class Meta:
        model = LigneAchat
        fields = ['produit_id', 'quantite', 'prix_unitaire', 'total']
        read_only_fields = ['total']

    def validate_quantite(self, value):
        if value <= 0:
            raise serializers.ValidationError("La quantité doit être supérieure à 0.")
        return value

    def validate_prix_unitaire(self, value):
        if value < 0:
            raise serializers.ValidationError("Le prix unitaire ne peut pas être négatif.")
        return value


# -------------------
# ACHAT
# -------------------
class AchatSerializer(serializers.ModelSerializer):
    lignes = LigneAchatSerializer(many=True)

    class Meta:
        model = Achat
        fields = ['id', 'magasin', 'fournisseur', 'numero_facture', 'montant_total', 'statut', 'lignes']
        read_only_fields = ['montant_total', 'statut', 'magasin']

    def validate(self, attrs):
        user = self.context['request'].user
        if user.role == 'CAISSIER':
            raise serializers.ValidationError("Vous n'avez pas la permission de créer un achat.")
        return attrs

    def create(self, validated_data):
        lignes_data = validated_data.pop('lignes')
        user = self.context['request'].user
        magasin = user.magasin

        return creer_achat(
            magasin=magasin,
            cree_par=user,
            lignes=lignes_data,
            fournisseur=validated_data.get('fournisseur'),
            numero_facture=validated_data.get('numero_facture')
        )


# -------------------
# LIGNE VENTE
# -------------------
class LigneVenteSerializer(serializers.ModelSerializer):
    produit_id = serializers.PrimaryKeyRelatedField(
        queryset=Produit.objects.all(),
        source='produit'
    )

    class Meta:
        model = LigneVente
        fields = ['produit_id', 'quantite', 'prix_unitaire', 'total']
        read_only_fields = ['total']

    def validate_quantite(self, value):
        if value <= 0:
            raise serializers.ValidationError("La quantité doit être supérieure à 0.")
        return value

    def validate_prix_unitaire(self, value):
        if value < 0:
            raise serializers.ValidationError("Le prix unitaire ne peut pas être négatif.")
        return value


# -------------------
# VENTE
# -------------------
class VenteSerializer(serializers.ModelSerializer):
    lignes = LigneVenteSerializer(many=True)

    class Meta:
        model = Vente
        fields = ['id', 'magasin', 'client_nom', 'remise', 'sous_total', 'montant_tva', 'montant_total', 'mode_paiement', 'statut', 'lignes']
        read_only_fields = ['sous_total', 'montant_tva', 'montant_total', 'statut', 'magasin']

    def validate(self, attrs):
        user = self.context['request'].user
        if user.role == 'CAISSIER':
            raise serializers.ValidationError("Vous n'avez pas la permission de créer une vente.")
        return attrs

    def create(self, validated_data):
        lignes_data = validated_data.pop('lignes')
        user = self.context['request'].user
        magasin = user.magasin

        remise = Decimal(validated_data.get('remise', 0))
        client_nom = validated_data.get('client_nom')
        mode_paiement = validated_data.get('mode_paiement', 'ESPECES')

        return creer_vente(
            magasin=magasin,
            cree_par=user,
            lignes=lignes_data,
            client_nom=client_nom,
            remise=remise,
            mode_paiement=mode_paiement
        )
        
class ThemeMagasinSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThemeMagasin
        fields = "__all__"