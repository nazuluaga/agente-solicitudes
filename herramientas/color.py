"""Color sin IA: leer colores CSS, contraste WCAG, OKLab y daltonismo simulado (solo biblioteca estándar).

Lo usa verificar_grafico.py para comprobar los colores del gráfico que escribe la IA.
  leer("#2a78d6")            -> (r, g, b, a), con r, g, b entre 0 y 255 y a entre 0 y 1; None si no se entiende
  componer(color, fondo)     -> el color con transparencia ya puesto sobre un fondo opaco
  contraste(c1, c2)          -> razón de contraste WCAG 2.x (de 1 a 21)
  pares_daltonismo(colores)  -> cada par con su ΔE (OKLab × 100) en el peor de tres tipos de daltonismo
Fuentes: WCAG 2.2 (luminancia relativa y contraste); Ottosson 2020 (OKLab); Machado, Oliveira y Fernandes
2009 (matrices de simulación con severidad 1,0, aplicadas en RGB lineal).
"""
import math
import re

# Nombres CSS que se usan a menudo en Plotly (minúsculas, sin espacios).
NOMBRES = {
    "white": "#ffffff", "black": "#000000", "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
    "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3", "darkgray": "#a9a9a9", "darkgrey": "#a9a9a9",
    "dimgray": "#696969", "dimgrey": "#696969", "gainsboro": "#dcdcdc", "whitesmoke": "#f5f5f5",
    "slategray": "#708090", "slategrey": "#708090", "lightslategray": "#778899", "lightslategrey": "#778899",
    "red": "#ff0000", "darkred": "#8b0000", "crimson": "#dc143c", "firebrick": "#b22222", "tomato": "#ff6347",
    "salmon": "#fa8072", "pink": "#ffc0cb", "maroon": "#800000", "brown": "#a52a2a",
    "orange": "#ffa500", "darkorange": "#ff8c00", "gold": "#ffd700", "yellow": "#ffff00", "olive": "#808000",
    "green": "#008000", "darkgreen": "#006400", "lime": "#00ff00", "lightgreen": "#90ee90", "seagreen": "#2e8b57",
    "teal": "#008080", "cyan": "#00ffff", "aqua": "#00ffff", "turquoise": "#40e0d0",
    "blue": "#0000ff", "navy": "#000080", "darkblue": "#00008b", "royalblue": "#4169e1", "steelblue": "#4682b4",
    "lightblue": "#add8e6", "skyblue": "#87ceeb", "dodgerblue": "#1e90ff",
    "purple": "#800080", "indigo": "#4b0082", "violet": "#ee82ee", "magenta": "#ff00ff", "fuchsia": "#ff00ff",
    "orchid": "#da70d6",
}

# Machado, Oliveira y Fernandes (2009), severidad 1,0; se aplican a RGB lineal.
MACHADO = {
    "protanopía": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopía": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopía": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}

_NUM = r"\s*([-+]?\d*\.?\d+)(%?)\s*"


def _canal(texto, pct, tope):
    v = float(texto)
    return max(0.0, min(tope, v * tope / 100 if pct else v))


def leer(texto):
    """'#rgb', '#rgba', '#rrggbb', '#rrggbbaa', 'rgb(...)', 'rgba(...)' o un nombre CSS -> (r, g, b, a); si no, None."""
    if not isinstance(texto, str):
        return None
    t = texto.strip().lower()
    if t == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    t = NOMBRES.get(t.replace(" ", ""), t)
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-f]+", h):
            return None
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (float(r), float(g), float(b), a)
    m = re.fullmatch(r"rgba?\((.*)\)", t)
    if not m:
        return None
    partes = [p for p in re.split(r"[,\s/]+", m.group(1).strip()) if p]
    if len(partes) not in (3, 4):
        return None
    try:
        rgb = []
        for p in partes[:3]:
            n = re.fullmatch(_NUM, p)
            if not n:
                return None
            rgb.append(_canal(n.group(1), n.group(2), 255.0))
        a = 1.0
        if len(partes) == 4:
            n = re.fullmatch(_NUM, partes[3])
            if not n:
                return None
            a = _canal(n.group(1), n.group(2), 1.0)
    except ValueError:
        return None
    return (rgb[0], rgb[1], rgb[2], a)


def componer(color, fondo):
    """Pone un color con transparencia sobre un fondo opaco: (r, g, b, a) sobre (r, g, b, ...) -> (r, g, b, 1)."""
    a = color[3]
    return tuple(a * color[i] + (1 - a) * fondo[i] for i in range(3)) + (1.0,)


def hex_(color):
    return "#" + "".join(f"{round(max(0, min(255, c))):02x}" for c in color[:3])


def _lineal(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _no_lineal(c):
    c = max(0.0, min(1.0, c))
    return 255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)


def luminancia(color):
    """Luminancia relativa WCAG de un color opaco."""
    r, g, b = (_lineal(c) for c in color[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(c1, c2):
    """Razón de contraste WCAG entre dos colores opacos (1 a 21)."""
    l1, l2 = sorted((luminancia(c1), luminancia(c2)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def _raiz3(x):
    return math.copysign(abs(x) ** (1 / 3), x)


def oklab(color):
    """OKLab (Ottosson 2020) de un color opaco: (L, a, b)."""
    r, g, b = (_lineal(c) for c in color[:3])
    l_ = _raiz3(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = _raiz3(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = _raiz3(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def simular(color, deficiencia):
    """Cómo ve el color una persona con la deficiencia dada (matriz de Machado en RGB lineal)."""
    lin = [_lineal(c) for c in color[:3]]
    fuera = [sum(fila[j] * lin[j] for j in range(3)) for fila in MACHADO[deficiencia]]
    return tuple(_no_lineal(c) for c in fuera) + (1.0,)


def delta_e(c1, c2):
    """Diferencia perceptual: distancia en OKLab × 100 (alrededor de 2 apenas se nota)."""
    return 100 * math.dist(oklab(c1), oklab(c2))


def pares_daltonismo(colores):
    """Cada par de colores opacos con su peor caso: [(ΔE mínimo entre las tres deficiencias, deficiencia, i, j)],
    de menor a mayor ΔE. Con menos de dos colores, lista vacía."""
    labs = {d: [oklab(simular(c, d)) for c in colores] for d in MACHADO}
    pares = []
    for i in range(len(colores)):
        for j in range(i + 1, len(colores)):
            de, d = min((100 * math.dist(labs[d][i], labs[d][j]), d) for d in MACHADO)
            pares.append((de, d, i, j))
    return sorted(pares)
