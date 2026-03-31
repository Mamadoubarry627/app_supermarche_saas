from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import Achat, LigneAchat, Produit, MouvementStock


@transaction.atomic
def creer_achat(*, magasin, cree_par, lignes, fournisseur=None, numero_facture=None):
    """
    lignes = [
        {
            "produit": <Produit>,
            "quantite": 2,
            "prix_unitaire": Decimal("15000")
        }
    ]
    """
    if not lignes:
        raise ValidationError("Un achat doit contenir au moins une ligne.")

    # Vérifier que tous les produits appartiennent au magasin
    for item in lignes:
        if item["produit"].magasin_id != magasin.id:
            raise ValidationError(f"Le produit {item['produit'].nom} n'appartient pas à ce magasin.")
        if item["quantite"] <= 0:
            raise ValidationError(f"Quantité invalide pour {item['produit'].nom}")

    # Créer achat
    achat = Achat.objects.create(
        magasin=magasin,
        fournisseur=fournisseur,
        numero_facture=numero_facture or generer_numero_facture_achat(magasin),
        montant_total=0,
        statut=Achat.Statut.TERMINE,
        cree_par=cree_par
    )

    montant_total = Decimal("0.00")

    for item in lignes:
        produit = item["produit"]
        quantite = int(item["quantite"])
        prix_unitaire = Decimal(item["prix_unitaire"])

        total_ligne = quantite * prix_unitaire

        # Créer ligne
        LigneAchat.objects.create(
            achat=achat,
            produit=produit,
            quantite=quantite,
            prix_unitaire=prix_unitaire,
            total=total_ligne
        )

        # Mise à jour stock
        produit.quantite_stock += quantite
        produit.save(update_fields=["quantite_stock"])

        # Mouvement stock
        MouvementStock.objects.create(
            magasin=magasin,
            produit=produit,
            type_mouvement="ENTREE",
            quantite=quantite,
            reference=achat.numero_facture,
            cree_par=cree_par
        )

        montant_total += total_ligne

    achat.montant_total = montant_total
    achat.save(update_fields=["montant_total"])

    return achat


def generer_numero_facture_achat(magasin):
    import uuid
    return f"ACH-{magasin.id}-{uuid.uuid4().hex[:8].upper()}"