from supermarcher.models import Vente, LigneVente, Achat, LigneAchat, Produit
from django.db import transaction
from decimal import Decimal

# ------------------------------
# Vente
# ------------------------------
def ajouter_au_panier_vente(user, produit, quantite=1):
    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(
            id=produit.id,
            magasin=user.magasin,
            actif=True
        )

        if produit.quantite_stock < quantite:
            raise ValueError("Stock insuffisant.")

        # Vente temporaire EN_COURS par utilisateur
        vente, _ = Vente.objects.get_or_create(
            magasin=user.magasin,
            cree_par=user,
            statut='EN_COURS'
        )

        ligne, created = LigneVente.objects.get_or_create(
            vente=vente,
            produit=produit,
            defaults={
                'quantite': quantite,
                'prix_unitaire': produit.prix_vente,
                'total': produit.prix_vente * quantite
            }
        )

        if not created:
            ligne.quantite += quantite
            ligne.total = ligne.quantite * ligne.prix_unitaire
            ligne.save(update_fields=['quantite', 'total'])

        return vente

# ------------------------------
# Achat
# ------------------------------
def ajouter_au_panier_achat(user, produit, quantite=1):
    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(
            id=produit.id,
            magasin=user.magasin,
            actif=True
        )

        # Achat temporaire EN_COURS par utilisateur
        achat, _ = Achat.objects.get_or_create(
            magasin=user.magasin,
            cree_par=user,
            statut='EN_COURS'
        )

        ligne, created = LigneAchat.objects.get_or_create(
            achat=achat,
            produit=produit,
            defaults={
                'quantite': quantite,
                'prix_unitaire': produit.prix_achat,
                'total': produit.prix_achat * quantite
            }
        )

        if not created:
            ligne.quantite += quantite
            ligne.total = ligne.quantite * ligne.prix_unitaire
            ligne.save(update_fields=['quantite', 'total'])

        return achat