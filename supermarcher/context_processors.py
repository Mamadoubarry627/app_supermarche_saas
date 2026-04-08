# context_processors.py

from .utils.theme import generate_theme_colors, hex_to_rgba


def theme_processor(request):
    """
    Ajoute automatiquement le thème du magasin dans tous les templates.
    """

    if not request.user.is_authenticated:
        return {}

    magasin = getattr(request.user, "magasin", None)
    if not magasin:
        return {}

    theme = getattr(magasin, "theme", None)
    if not theme:
        return {}

    # Couleur principale
    primary = theme.couleur_principale

    # Génération palette
    colors = generate_theme_colors(primary)

    return {
        "theme": theme,
        "theme_logo": theme.logo,
        "theme_dark": theme.mode_sombre,

        # couleurs complètes
        "theme_colors": colors,

        # accès rapide
        "theme_color": primary,
        "theme_light": hex_to_rgba(primary, 0.05),
    }