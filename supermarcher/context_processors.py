from .models import ThemeMagasin
from .utils.theme import generate_theme_colors, hex_to_rgba


def theme_processor(request):

    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {
            "theme_dark": False,
            "theme_color": "#1324db",
            "theme_light": "rgba(19,36,219,0.05)",
            "theme_colors": {
                "primary_hover": "#0f1ea8",
                "text": "#0f172a",
            }
        }

    magasin = getattr(user, "magasin", None)

    if not magasin:
        return {}

    # =========================
    # ONLY READ (SAFE)
    # =========================
    theme = ThemeMagasin.objects.filter(magasin=magasin).first()

    # fallback si absent
    primary = "#1324db"
    dark = False

    if theme:
        primary = theme.couleur_principale or primary
        dark = theme.mode_sombre

    colors = generate_theme_colors(primary)

    return {
        "theme": theme,
        "theme_logo": getattr(theme, "logo", None),
        "theme_dark": dark,

        "theme_colors": colors,
        "theme_color": primary,
        "theme_light": hex_to_rgba(primary, 0.05),
    }