from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from supermarcher.signals import log_action

from ..models import Vente, LigneVente
from .stock_service import retirer_stock

#supermarcher/services/vente_service.py
@transaction.atomic
def creer_vente(*, magasin, cree_par, lignes, mode_paiement, client_nom=None, remise=Decimal("0.00")):
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
        raise ValidationError("Une vente doit contenir au moins une ligne.")

    sous_total = Decimal("0.00")
    montant_tva = Decimal("0.00")
    remise = Decimal(remise or "0.00")

    vente = Vente.objects.create(
        magasin=magasin,
        numero_facture=generer_numero_facture_vente(magasin),
        client_nom=client_nom,
        sous_total=Decimal("0.00"),
        montant_tva=Decimal("0.00"),
        remise=remise,
        montant_total=Decimal("0.00"),
        mode_paiement=mode_paiement,
        cree_par=cree_par,
        statut=Vente.Statut.COMPLETEE
    )

    for item in lignes:
        produit = item["produit"]
        quantite = int(item["quantite"])
        prix_unitaire = Decimal(item["prix_unitaire"])

        if quantite <= 0:
            raise ValidationError("La quantité doit être supérieure à 0.")

        if produit.magasin_id != magasin.id:
            raise ValidationError(
                f"Le produit {produit.nom} n'appartient pas à ce magasin."
            )

        if not produit.actif:
            raise ValidationError(
                f"Le produit {produit.nom} est inactif."
            )

        total_ligne = prix_unitaire * quantite
        tva_ligne = (total_ligne * produit.taux_tva) / Decimal("100")

        LigneVente.objects.create(
            vente=vente,
            produit=produit,
            quantite=quantite,
            prix_unitaire=prix_unitaire,
            total=total_ligne
        )

        retirer_stock(
            produit=produit,
            magasin=magasin,
            quantite=quantite,
            reference=vente.numero_facture,
            cree_par=cree_par
        )

        sous_total += total_ligne
        montant_tva += tva_ligne

    montant_total = sous_total + montant_tva - remise

    if montant_total <= 0:
        raise ValidationError("Le total doit être supérieur à 0.")

    vente.sous_total = sous_total
    vente.montant_tva = montant_tva
    vente.montant_total = montant_total
    vente.save(update_fields=["sous_total", "montant_tva", "montant_total"])
    
    transaction.on_commit(lambda: log_action(
    action="CREATE",
    modele="Vente",
    objet_id=vente.id,
    description=f"Création vente #{vente.id}"
))
    return vente


def generer_numero_facture_vente(magasin):
    import uuid
    return f"VTE-{magasin.id}-{uuid.uuid4().hex[:8].upper()}"