#!/usr/bin/env python3
"""Visualización: comprueba el gráfico que generó la IA (sin IA) y lo deja en grafico.html.

Uso: python verificar_grafico.py <corrida>

La corrida trae:
  grafico.json  {"pregunta", "medida": columna de valores, "categoria": columna de claves, "periodo",
                 "periodo_incompleto": bool, "fuera_del_grafico": {"motivo", "valor"} (opcional)}
  grafico.py    def graficar(resultado, procedencia) -> plotly.graph_objects.Figure
                (resultado = filas aprobadas; procedencia = la de la ingesta, con fuente y fecha)

Lista de comprobación (módulo 4 del curso):
  1. cuenta de control: lo que suma el gráfico + lo que se dejó fuera (declarado) = total de la tabla
  2. barras con el eje de valores desde cero; factor de mentira 1
  3. título con qué se mide y el período (un número)
  4. eje de valores con título (unidades)
  5. fuente y fecha de consulta visibles
  6. período incompleto marcado, si aplica
  7. sin datos personales en ningún texto del gráfico
Forma y color (comprobar_forma_y_color: solo lee el JSON de la figura; la prueba es baterias/grafico/):
  8. colores con función: 7 o menos colores distintos en las marcas (Datawrapper; Muth 2018)
  9. contraste de cada color de marca con su fondo de 3:1 o más (WCAG 1.4.11); por debajo, solo si la traza
     lleva etiquetas de texto visibles
 10. colores distinguibles con daltonismo: entre cada par, ΔE (OKLab × 100) de 8 o más con protanopía,
     deuteranopía y tritanopía simuladas (Machado, Oliveira y Fernandes 2009); de 6 a 8, solo con etiquetas
 11. texto legible: letra general, título y marcas de los ejes con contraste de 4,5:1 o más con el papel (WCAG 1.4.3)
 12. un solo eje de valores: sin doble eje (mejor dos gráficas o un índice con base 100)
 13. sin 3D ni tortas de más de cinco porciones
 14. escala logarítmica declarada en el título del eje o en el principal
Los colores se toman de la figura (marker.color, line.color, marker.colors) o, si no los trae, de la paleta
(colorway) de la figura o de su plantilla, en el orden de las trazas. Ver herramientas/color.py.
El HTML lo escribe este verificador, no el código de la IA (que corre en la caja de arena y no escribe).
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import caja  # noqa: E402
import color  # noqa: E402
import dependencias  # noqa: E402
import seguridad  # noqa: E402
from gobernanza import escanear_texto, parece_instruccion  # noqa: E402

RUNNER = r'''
import importlib.util, json, sys
ruta, resultado, procedencia = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
import types
m = types.ModuleType("graf"); m.__file__ = ruta
exec(compile(open(ruta, encoding="utf-8").read(), ruta, "exec"), m.__dict__)   # desde la fuente, sin .pyc
fig = m.graficar(resultado, procedencia)
print("MARCA" + fig.to_json())
'''.replace("MARCA", caja.MARCA)


def procedencia_de(c, spec):
    from rutas import resolver
    rutas = list((spec.get("datos_crudos") or {}).values()) + list(spec["datos"].values())   # la procedencia vive junto al dato crudo
    for p in [c / "procedencia.json"] + [Path(resolver(r)).parent / "procedencia.json" for r in rutas]:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def textos(fig):
    L = []
    lay = fig.get("layout", {})
    tit = lay.get("title", {})
    L.append(tit.get("text", "") if isinstance(tit, dict) else str(tit))
    for eje in ("xaxis", "yaxis"):
        t = (lay.get(eje) or {}).get("title", {})
        L.append(t.get("text", "") if isinstance(t, dict) else str(t))
    L += [a.get("text", "") for a in lay.get("annotations", [])]
    for tr in fig.get("data", []):
        for k in ("name", "text", "hovertemplate", "x", "y", "customdata"):
            v = tr.get(k)
            if isinstance(v, list):
                L += [json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x for x in v]
            elif isinstance(v, str):
                L.append(v)
    return L


def fechas_posibles(iso):
    try:
        d = date.fromisoformat(iso[:10])
    except (TypeError, ValueError):
        return []
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return [f"{d:%d-%m-%Y}", f"{d:%d/%m/%Y}", d.isoformat(), f"{d.day} de {meses[d.month - 1]} de {d.year}",
            f"{d:%d} de {meses[d.month - 1]} de {d.year}"]


def valores_de(tr):
    h = tr.get("orientation") == "h"
    v = tr.get("x") if h else tr.get("y")
    if isinstance(v, dict) and "bdata" in v:       # plotly 6+: arreglos binarios en el JSON
        import base64
        import numpy as np
        v = np.frombuffer(base64.b64decode(v["bdata"]), dtype=np.dtype(v.get("dtype", "f8"))).tolist()
    return [float(x) for x in (v or []) if x is not None], ("xaxis" if h else "yaxis")


# --- Forma y color (comprobaciones 8 a 14): solo leen el JSON de la figura ---------------------------------------
TIPOS_3D = {"scatter3d", "surface", "mesh3d", "cone", "streamtube", "volume", "isosurface"}
TIPOS_PORCION = {"pie", "funnelarea"}            # porciones sobre el papel, con marker.colors
SIN_COLOR_DISCRETO = {"heatmap", "contour", "histogram2d", "histogram2dcontour", "choropleth", "choroplethmap",
                      "choroplethmapbox", "densitymap", "densitymapbox", "image", "table", "indicator", "parcoords",
                      "parcats", "sankey", "surface", "mesh3d", "cone", "streamtube", "volume", "isosurface"}
PALETA_PLOTLY = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22",
                 "#17becf"]                      # la de plotly.js cuando ni la figura ni la plantilla traen colorway
TEXTO_PLOTLY = "#444"
EJE = re.compile(r"^[xy]axis\d*$")
DECLARA_LOG = re.compile(r"\blog(?:ar[ií]tmic[ao]s?|arithmic|10)?\b", re.I)   # «catálogo» no cuenta (L35)
MAX_COLORES, MIN_MARCA, MIN_TEXTO, MIN_DE, MIN_DE_CON_ETIQUETAS, MAX_PORCIONES = 7, 3.0, 4.5, 8.0, 6.0, 5


def _n(x, dec=1):
    return f"{x:.{dec}f}".replace(".", ",")


def _plantilla(lay):
    t = lay.get("template")
    return (t.get("layout") or {}) if isinstance(t, dict) else {}


def _en(d, *claves):
    for k in claves:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _de(lay, *claves):
    """El valor del layout; si no está, el de la plantilla; si tampoco, None."""
    for fuente in (lay, _plantilla(lay)):
        v = _en(fuente, *claves)
        if v not in (None, "", []):
            return v
    return None


def _texto_de(t):
    return str((t.get("text") or "") if isinstance(t, dict) else (t or ""))


def _largo(v):
    """Cuántos valores trae un arreglo del JSON (lista o binario de plotly 6+)."""
    if isinstance(v, list):
        return len(v)
    if isinstance(v, dict) and "bdata" in v:
        import base64
        tam = int(re.sub(r"\D", "", str(v.get("dtype", "f8"))) or 8)
        return len(base64.b64decode(v["bdata"])) // tam
    return 0


def _porciones(tr):
    etiquetas = tr.get("labels")
    if isinstance(etiquetas, list) and etiquetas:
        return len({json.dumps(e, ensure_ascii=False) for e in etiquetas})   # Plotly junta las etiquetas repetidas
    return _largo(tr.get("values"))


def _colores_de(v):
    """Colores de un atributo: una cadena o una lista de cadenas (los números van a una escala continua: no cuentan)."""
    if isinstance(v, str):
        return [v]
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _con_etiquetas(tr):
    """La traza muestra texto sobre sus marcas (el color no es el único medio, WCAG 1.4.1)."""
    texto = tr.get("text")
    hay = bool(tr.get("texttemplate")) or (isinstance(texto, str) and texto.strip()) or \
        (isinstance(texto, list) and any(str(x).strip() for x in texto if x is not None))
    tipo = tr.get("type") or "scatter"
    if tipo.startswith("scatter"):
        return bool(hay) and "text" in str(tr.get("mode", ""))     # sin «text» en mode, el texto solo sale al pasar el puntero
    if tipo in TIPOS_PORCION and re.search(r"label|text", str(tr.get("textinfo", ""))):
        hay = True
    return bool(hay) and tr.get("textposition") != "none"


def _fondos(lay, notas):
    """Fondo del papel y del área de trazado, opacos (con transparencia, se componen sobre lo de abajo)."""
    blanco = color.leer("white")
    crudo = _de(lay, "paper_bgcolor")
    papel = color.leer(crudo) if crudo else blanco
    if papel is None:
        notas.append(f"paper_bgcolor sin reconocer ({str(crudo)[:30]}): se toma blanco")
        papel = blanco
    papel = color.componer(papel, blanco)
    crudo = _de(lay, "plot_bgcolor")
    area = color.leer(crudo) if crudo else papel
    if area is None:
        notas.append(f"plot_bgcolor sin reconocer ({str(crudo)[:30]}): se toma el del papel")
        area = papel
    return papel, color.componer(area, papel)


def _marcas(fig, papel, area):
    """Los colores con que se dibujan los datos, traza por traza: [(texto, rgba o None, traza, con etiquetas, fondo)]."""
    lay = fig.get("layout") or {}
    paleta = _colores_de(_de(lay, "colorway")) or PALETA_PLOTLY
    paleta_porciones = _colores_de(_de(lay, "piecolorway")) or paleta
    marcas, continuas = [], 0
    for i, tr in enumerate(fig.get("data") or []):
        if not isinstance(tr, dict) or tr.get("visible") in (False, "legendonly"):
            continue
        tipo = tr.get("type") or "scatter"
        if tipo in SIN_COLOR_DISCRETO:
            continue
        m = tr.get("marker") if isinstance(tr.get("marker"), dict) else {}
        linea = tr.get("line") if isinstance(tr.get("line"), dict) else {}
        if tipo in TIPOS_PORCION:
            propios = _colores_de(m.get("colors"))
            n = _porciones(tr)
            textos_ = propios + [paleta_porciones[k % len(paleta_porciones)] for k in range(len(propios), n)]
        else:
            crudos = [m.get("color")]
            if not tipo.startswith("scatter") or "lines" in str(tr.get("mode", "lines")):   # la línea se dibuja
                crudos.append(linea.get("color"))
            textos_ = [t for v in crudos for t in _colores_de(v)]
            if not textos_ and any(v is not None for v in crudos):
                continuas += 1                   # colores por escala continua: no son categorías
                continue
            textos_ = textos_ or [paleta[i % len(paleta)]]   # sin color propio: la paleta, en el orden de las trazas
        fondo = papel if tipo in TIPOS_PORCION else area
        rot = _con_etiquetas(tr)
        for t in dict.fromkeys(textos_):
            marcas.append((t, color.leer(t), i, rot, fondo))
    return marcas, continuas


def comprobar_forma_y_color(fig):
    """Comprobaciones 8 a 14 sobre el JSON de una figura de Plotly (sin correr código): devuelve la lista de checks."""
    lay = fig.get("layout") or {}
    notas = []
    papel, area = _fondos(lay, notas)
    marcas, continuas = _marcas(fig, papel, area)
    leidas = [(t, color.componer(c, f), i, rot, f) for t, c, i, rot, f in marcas if c is not None]
    raras = sorted({t for t, c, *_ in marcas if c is None})
    extra = (f" · sin reconocer: {raras[:4]}" if raras else "") \
        + (f" · trazas con escala continua, que no cuentan: {continuas}" if continuas else "") + "".join(f" · {n}" for n in notas)
    nada = not marcas
    ilegible = bool(marcas) and not leidas
    checks = []

    # 8. colores con función: 7 o menos (Datawrapper; Muth 2018)
    distintos = {}
    for t, c, i, rot, f in leidas:
        h = color.hex_(c)
        distintos.setdefault(h, {"rgb": c, "etiquetas": True})
        distintos[h]["etiquetas"] &= rot
    n = len(distintos) + len(raras)
    det = ("sin colores de marcas" if nada else "ningún color se pudo leer" if ilegible
           else f"{n} color{'es' if n != 1 else ''}: {', '.join(list(distintos)[:9])}" + (f" (máximo {MAX_COLORES})" if n > MAX_COLORES else ""))
    checks.append({"comprobacion": "colores con función: 7 o menos", "ok": not ilegible and n <= MAX_COLORES,
                   "detalle": det + extra})

    # 9. contraste de las marcas con su fondo (WCAG 1.4.11): 3:1; por debajo, solo si la traza lleva etiquetas de texto
    medidas = sorted((color.contraste(c, f), color.hex_(c), color.hex_(f), rot) for t, c, i, rot, f in leidas)
    bajas = [m for m in medidas if m[0] < MIN_MARCA]
    malas = list(dict.fromkeys(f"{h} {_n(r, 2)}:1 sobre {fo}" for r, h, fo, rot in bajas if not rot))
    aliviadas = list(dict.fromkeys(f"{h} {_n(r, 2)}:1" for r, h, fo, rot in bajas if rot))
    if nada or ilegible:
        det = "sin colores de marcas" if nada else "ningún color se pudo leer"
    elif malas:
        det = f"por debajo de 3:1 y sin etiquetas de texto: {', '.join(malas[:4])}"
    else:
        solas = [m for m in medidas if m[0] >= MIN_MARCA]
        partes = [f"por debajo de 3:1 pero con etiquetas de texto visibles en su traza: {', '.join(aliviadas[:4])}"] if aliviadas else []
        if solas:
            r, h, fo, _ = solas[0]
            partes.append(f"{'las demás, ' if aliviadas else ''}mínimo {_n(r)}:1 ({h} sobre {fo})")
        det = "; ".join(partes)
    checks.append({"comprobacion": "contraste de las marcas de 3:1 o más con el fondo (WCAG 1.4.11)",
                   "ok": not ilegible and not malas, "detalle": det + extra})

    # 10. colores distinguibles con daltonismo (Machado 2009, severidad 1,0; ΔE en OKLab × 100)
    claves = list(distintos)
    pares = color.pares_daltonismo([distintos[h]["rgb"] for h in claves])
    con_et = lambda i, j: distintos[claves[i]]["etiquetas"] and distintos[claves[j]]["etiquetas"]  # noqa: E731
    fallan = [p for p in pares if p[0] < MIN_DE_CON_ETIQUETAS or (p[0] < MIN_DE and not con_et(p[2], p[3]))]
    if nada or ilegible:
        det = "sin colores de marcas" if nada else "ningún color se pudo leer"
    elif not pares:
        det = "un solo color: no hay pares que distinguir"
    else:
        de, d, i, j = pares[0]
        det = f"peor par {claves[i]} / {claves[j]}: ΔE {_n(de)} con {d}"
        if fallan and fallan[0] is not pares[0]:
            de, d, i, j = fallan[0]
            det += f"; falla {claves[i]} / {claves[j]}: ΔE {_n(de)} con {d}"
        if fallan:
            det += f" (mínimo {_n(MIN_DE, 0)}; de {_n(MIN_DE_CON_ETIQUETAS, 0)} a {_n(MIN_DE, 0)}, solo con etiquetas de texto)"
        elif pares[0][0] < MIN_DE:
            det += f" (de {_n(MIN_DE_CON_ETIQUETAS, 0)} a {_n(MIN_DE, 0)}: pasa porque las trazas llevan etiquetas de texto)"
    checks.append({"comprobacion": "colores distinguibles con daltonismo", "ok": not ilegible and not fallan,
                   "detalle": det + extra})

    # 11. texto legible: 4,5:1 con el fondo del papel (WCAG 1.4.3)
    general = _de(lay, "font", "color") or TEXTO_PLOTLY
    textos_ = [("letra general", general), ("título", _de(lay, "title", "font", "color") or general)]
    for k in sorted(x for x in lay if EJE.match(x) and isinstance(lay[x], dict)):
        textos_.append((f"marcas de {k}", _en(lay, k, "tickfont", "color")
                        or _en(_plantilla(lay), k[:5], "tickfont", "color") or general))   # la plantilla trae xaxis y yaxis
    medidas = []
    raras_t = []
    for donde, t in textos_:
        c = color.leer(t) if isinstance(t, str) else None
        if c is None:
            raras_t.append(f"{donde} ({str(t)[:30]})")
            continue
        c = color.componer(c, papel)
        medidas.append((color.contraste(c, papel), donde, color.hex_(c)))
    medidas.sort()
    malas = [f"{d} {h} {_n(r, 2)}:1" for r, d, h in medidas if r < MIN_TEXTO]   # 2 decimales: 4,46 no se lee «4,5»
    if not medidas:
        det = "ningún color de texto se pudo leer"
    elif malas:
        det = f"por debajo de 4,5:1 sobre {color.hex_(papel)}: {', '.join(malas)}"
    else:
        r, d, h = medidas[0]
        det = f"mínimo {_n(r)}:1 ({d} {h} sobre {color.hex_(papel)})"
    det += f" · sin reconocer: {raras_t}" if raras_t else ""
    checks.append({"comprobacion": "texto legible: contraste de 4,5:1 o más (WCAG 1.4.3)", "ok": bool(medidas) and not malas,
                   "detalle": det})

    # 12. un solo eje de valores: un doble eje deja elegir la escala para que dos series «se crucen»
    dobles = [f"{k} se superpone a {lay[k]['overlaying']}" for k in sorted(lay)
              if EJE.match(k) and isinstance(lay[k], dict) and lay[k].get("overlaying")]
    checks.append({"comprobacion": "un solo eje de valores (sin doble eje)", "ok": not dobles,
                   "detalle": "un eje por dirección" if not dobles
                   else f"{'; '.join(dobles)}: en lugar del doble eje, dos gráficas o un índice con base 100"})

    # 13. sin 3D (deforma por perspectiva) ni tortas de más de cinco porciones (los ángulos se comparan mal)
    tres_d = sorted({tr.get("type") for tr in fig.get("data") or [] if isinstance(tr, dict) and tr.get("type") in TIPOS_3D})
    tortas = [_porciones(tr) for tr in fig.get("data") or [] if isinstance(tr, dict) and tr.get("type") == "pie"]
    grandes = [n for n in tortas if n > MAX_PORCIONES]
    problemas = ([f"trazas 3D: {tres_d}"] if tres_d else []) + \
        ([f"torta con {', '.join(map(str, grandes))} porciones (máximo {MAX_PORCIONES}): mejor barras ordenadas"] if grandes else [])
    checks.append({"comprobacion": "sin 3D ni tortas de más de cinco porciones", "ok": not problemas,
                   "detalle": "; ".join(problemas) if problemas
                   else (f"torta de {max(tortas)} porciones" if tortas else "sin 3D ni tortas")})

    # 14. escala logarítmica declarada en el título del eje o en el principal
    titulo = _texto_de(lay.get("title")) + " " + _texto_de(_en(lay, "title", "subtitle"))
    logs = [k for k in sorted(lay) if EJE.match(k) and isinstance(lay[k], dict) and lay[k].get("type") == "log"]
    callados = [k for k in logs if not DECLARA_LOG.search(_texto_de(lay[k].get("title")) + " " + titulo)]
    if not logs:
        det = "sin escala logarítmica"
    elif callados:
        det = f"{', '.join(callados)} en escala logarítmica sin decirlo en el título del eje ni en el principal (p. ej. «escala logarítmica»)"
    else:
        det = f"{', '.join(logs)} en escala logarítmica, declarada en el título"
    checks.append({"comprobacion": "escala logarítmica declarada", "ok": not callados, "detalle": det})
    return checks


def comprobar(c):
    from rutas import resolver_datos
    spec = resolver_datos(json.loads((c / "spec.json").read_text(encoding="utf-8")))
    inf = json.loads((c / "informe.json").read_text(encoding="utf-8"))
    meta = json.loads((c / "grafico.json").read_text(encoding="utf-8"))
    resultado = inf.get("resultado_oficial") or []
    proc = procedencia_de(c, spec)
    checks = []
    gp = c / "grafico.py"
    dep = dependencias.revisar(gp)
    seg, _ = seguridad.revisar([gp])
    bloqueos = (dep.get("no_permitidas") or []) + (dep.get("intenta_instalar") or []) + [h["regla"] for h in seg[0]["bloquean"]]
    checks.append({"comprobacion": "compuertas de seguridad y librerías", "ok": not bloqueos, "detalle": str(bloqueos or "sin hallazgos")})
    if bloqueos:
        return checks, None
    fig_json, err = caja.correr(RUNNER, str(gp), json.dumps(resultado, ensure_ascii=False), json.dumps(proc, ensure_ascii=False))
    checks.append({"comprobacion": "el código del gráfico corre", "ok": err is None, "detalle": err or "devolvió una figura"})
    if err:
        return checks, None
    fig = fig_json
    lay = fig.get("layout", {})
    barras = [t for t in fig.get("data", []) if t.get("type") == "bar"]
    medida = meta.get("medida")
    total_tabla = sum(float(f.get(medida) or 0) for f in resultado) if medida else None
    suma_graf, eje = 0.0, "yaxis"
    for t in fig.get("data", []):
        vals, eje = valores_de(t)
        suma_graf += sum(vals)
    fuera = float((meta.get("fuera_del_grafico") or {}).get("valor") or 0)
    escala = float(meta.get("escala") or 1)       # p. ej. 1e9 si el gráfico muestra miles de millones
    if total_tabla is not None:
        en_pesos = suma_graf * escala
        ok = abs(en_pesos + fuera - total_tabla) <= max(0.5, 1e-9 * abs(total_tabla), 1e-6 * escala)
        checks.append({"comprobacion": "cuenta de control", "ok": ok,
                       "detalle": f"gráfico {en_pesos:,.2f} (escala {escala:g}) + fuera del gráfico {fuera:,.2f} · tabla {total_tabla:,.2f}"})
    if barras:
        ax = lay.get(eje, {}) or {}
        rango = ax.get("range")
        desde_cero = not (rango and rango[0] not in (0, None)) and ax.get("type") != "log" and not any(t.get("base") for t in barras)
        factor = 1.0
        if not desde_cero and rango:
            vals = [v for t in barras for v in valores_de(t)[0] if v > 0]
            if vals and min(vals) > rango[0]:
                factor = round(((max(vals) - rango[0]) / (min(vals) - rango[0])) / (max(vals) / min(vals)), 2)
        checks.append({"comprobacion": "barras desde cero (factor de mentira 1)", "ok": desde_cero,
                       "detalle": "el eje de valores empieza en 0" if desde_cero else f"el eje empieza en {rango[0]}: factor de mentira {factor}"})
        tit_eje = (ax.get("title") or {}).get("text") if isinstance(ax.get("title"), dict) else ax.get("title")
        checks.append({"comprobacion": "eje de valores con título y unidades", "ok": bool(tit_eje and str(tit_eje).strip()),
                       "detalle": str(tit_eje or "sin título")})
    t = lay.get("title", {})
    titulo = t.get("text", "") if isinstance(t, dict) else str(t or "")
    checks.append({"comprobacion": "título con qué se mide y el período", "ok": len(titulo) >= 15 and bool(re.search(r"\d", titulo)),
                   "detalle": titulo or "sin título"})
    todo = " ".join(textos(fig))
    fuente = (proc.get("fuente") or {}).get("titulo", "")
    palabra = (fuente.split()[0] if fuente else "fuente").lower()
    fechas = fechas_posibles(proc.get("consultado", ""))
    tiene_fuente = palabra in todo.lower()
    tiene_fecha = any(f in todo for f in fechas) if fechas else True
    checks.append({"comprobacion": "fuente y fecha de consulta visibles", "ok": tiene_fuente and tiene_fecha,
                   "detalle": f"fuente «{palabra}»: {'sí' if tiene_fuente else 'no'} · fecha {fechas[:1]}: {'sí' if tiene_fecha else 'no'}"})
    if meta.get("periodo_incompleto"):
        marcado = bool(re.search(r"\b(incomplet\w*|parcial\w*|corte|hasta el)\b", todo, re.I))   # «Recorte» no cuenta
        checks.append({"comprobacion": "período incompleto marcado", "ok": marcado, "detalle": "marcado" if marcado else "no se marca"})
    # El riesgo: un texto de los DATOS que trae «<» (p. ej. un nombre con <a href>) y llega sin escapar, o enlaces y
    # scripts en cualquier parte. El formato que pone el graficador (<b>, <br>, <span>) es legítimo en Plotly.
    crudos = sorted({v for f in resultado for v in f.values() if isinstance(v, str) and "<" in v})
    sin_escapar = [v[:60] for v in crudos if v in todo]
    peligrosas = sorted(set(re.findall(r"<\s*(a|img|iframe|script|object|embed|link|meta)\b", todo, re.I)))
    ok_html = not sin_escapar and not peligrosas
    checks.append({"comprobacion": "sin HTML de los datos sin escapar, ni enlaces o scripts", "ok": ok_html,
                   "detalle": "ninguno" if ok_html else (f"texto de los datos sin escapar: {sin_escapar}" if sin_escapar else "")
                   + (f" · etiquetas peligrosas {peligrosas}" if peligrosas else "") + " (Plotly interpreta HTML; escape «<» como &lt;)"})
    invisibles = [t[:40] for t in textos(fig) if re.search(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]", t)]
    checks.append({"comprobacion": "sin caracteres invisibles o bidireccionales en el texto publicado", "ok": not invisibles,
                   "detalle": "ninguno" if not invisibles else f"{len(invisibles)} textos (pueden voltear o disfrazar lo que se lee): {invisibles[:2]}"})
    # procedencia: con una procedencia falsa, el gráfico debe mostrar ESA fuente y ESA fecha (nada escrito a mano)
    falsa = dict(proc or {})
    falsa.update({"fuente": {**(proc.get("fuente") or {}), "titulo": "FUENTE-DE-CONTROL"}, "consultado": "2000-01-02T00:00:00"})
    fig_f, err_f = caja.correr(RUNNER, str(gp), json.dumps(resultado, ensure_ascii=False), json.dumps(falsa, ensure_ascii=False))
    if fig_f is not None:
        tf = " ".join(textos(fig_f))
        sigue = any(f in tf for f in fechas_posibles(proc.get("consultado", "")))
        usa = any(f in tf for f in fechas_posibles("2000-01-02"))
        checks.append({"comprobacion": "la fuente y la fecha salen de la procedencia, no del código", "ok": usa and not sigue,
                       "detalle": "con una procedencia de control, el gráfico muestra su fecha" if usa and not sigue
                       else "el gráfico muestra una fecha escrita en el código, no la de la procedencia"})
    ordenes = [t[:60] for t in textos(fig) if parece_instruccion(t)]
    checks.append({"comprobacion": "sin textos con forma de instrucción para una IA", "ok": not ordenes,
                   "detalle": "ninguno" if not ordenes else f"{len(ordenes)}: {ordenes[:2]} (un dato con forma de orden no se publica como dato normal: revisarlo en la fuente)"})
    pii = escanear_texto(todo)
    checks.append({"comprobacion": "sin datos personales en el gráfico", "ok": not pii, "detalle": str(pii or "ninguno")})
    checks += comprobar_forma_y_color(fig)
    return checks, fig


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    c = Path(argv[0]).resolve()
    checks, fig = comprobar(c)
    if fig is not None:
        import plotly.io as pio
        pio.from_json(json.dumps(fig)).write_html(str(c / "grafico.html"), include_plotlyjs=True, full_html=True)
    ok = all(x["ok"] for x in checks)
    out = {"estado": "aprobado" if ok else "revisar", "comprobaciones": checks, "html": str(c / "grafico.html") if fig else None}
    (c / "grafico_verificacion.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for x in checks:
        print(f"{'✓' if x['ok'] else '✗'} {x['comprobacion']}: {x['detalle']}")
    print("RESUMEN " + json.dumps({"estado": out["estado"], "fallas": [x["comprobacion"] for x in checks if not x["ok"]]}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
