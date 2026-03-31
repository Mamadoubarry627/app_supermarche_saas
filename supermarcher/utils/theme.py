# utils/theme.py

def hex_to_rgb(hex_color):
    """Convertit un hex en tuple RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def darken_color(hex_color, factor=0.85):
    """Assombrit une couleur HEX"""
    r, g, b = hex_to_rgb(hex_color)
    r = max(0, int(r * factor))
    g = max(0, int(g * factor))
    b = max(0, int(b * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten_color(hex_color, factor=1.2):
    """Éclaircit une couleur HEX"""
    r, g, b = hex_to_rgb(hex_color)
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def get_text_color(hex_color):
    """Retourne noir ou blanc selon la luminosité"""
    r, g, b = hex_to_rgb(hex_color)
    brightness = (r*299 + g*587 + b*114) / 1000
    return "#000000" if brightness > 128 else "#ffffff"


def generate_theme_colors(hex_color):
    """Renvoie un dictionnaire complet de couleurs pour le thème"""
    return {
        "primary": hex_color,
        "primary_hover": darken_color(hex_color, 0.85),
        "primary_light": lighten_color(hex_color, 1.2),
        "text": get_text_color(hex_color),
        "border": lighten_color(hex_color, 1.5)
    }
    
def hex_to_rgba(hex_color, alpha=0.05):

    hex_color = hex_color.lstrip('#')

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    return f"rgba({r},{g},{b},{alpha})"