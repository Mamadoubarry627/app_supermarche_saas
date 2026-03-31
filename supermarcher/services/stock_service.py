from django.core.exceptions import ValidationError
from django.db.models import F

from ..models import Produit, MouvementStock


def ajouter_stock(*, produit, magasin, quantite, reference=None, cree_par=None, type_mouvement="ENTREE"):
    if quantite <= 0:
        raise ValidationError("La quantité doit être supérieure à 0.")

    if produit.magasin_id != magasin.id:
        raise ValidationError("Le produit n'appartient pas à ce magasin.")

    Produit.objects.filter(
        pk=produit.pk,
        magasin=magasin
    ).update(
        quantite_stock=F("quantite_stock") + quantite
    )

    produit.refresh_from_db(fields=["quantite_stock"])

    MouvementStock.objects.create(
        magasin=magasin,
        produit=produit,
        type_mouvement=type_mouvement,
        quantite=quantite,
        reference=reference,
        cree_par=cree_par
    )

    return produit


def retirer_stock(*, produit, magasin, quantite, reference=None, cree_par=None, autoriser_stock_negatif=False):
    if quantite <= 0:
        raise ValidationError("La quantité doit être supérieure à 0.")

    if produit.magasin_id != magasin.id:
        raise ValidationError("Le produit n'appartient pas à ce magasin.")

    qs = Produit.objects.filter(
        pk=produit.pk,
        magasin=magasin,
    )

    if not autoriser_stock_negatif:
        qs = qs.filter(quantite_stock__gte=quantite)

    updated = qs.update(
        quantite_stock=F("quantite_stock") - quantite
    )

    if updated == 0:
        produit.refresh_from_db(fields=["quantite_stock"])
        raise ValidationError(
            f"Stock insuffisant pour le produit {produit.nom}."
        )

    produit.refresh_from_db(fields=["quantite_stock"])

    MouvementStock.objects.create(
        magasin=magasin,
        produit=produit,
        type_mouvement="SORTIE",
        quantite=quantite,
        reference=reference,
        cree_par=cree_par
    )

    return produit