from django import template

register = template.Library()

@register.filter
def underscore_to_space(value):
    if value is None:
        return ""
    return str(value).replace("_", " ")


@register.filter
def is_numeric_field(field):
    numeric_fields = [
        "prix",
        "prix_unitaire",
        "prix_achat",
        "prix_vente",
        "total",
        "montant",
        "montant_total",
        "quantite",
        "quantite_stock",
        "total_ventes",
        "total_ca",
        "marge",
        "benefice"
    ]
    return field in numeric_fields