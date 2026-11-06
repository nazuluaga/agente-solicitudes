#!/usr/bin/env python3
"""Presentación: comprueba sin IA la presentación que propuso la IA y, si aprueba, la deja en presentacion.html.

Uso:
  python verificar_presentacion.py <corrida>
  python verificar_presentacion.py --autoprueba      prueba al probador: presentaciones buenas y sus mutantes

La IA (subagente presentador, agentes/12-presentador.md) escribe SOLO presentacion.json. **No escribe números**:
en los textos pone marcadores como {total}, y cada marcador es una cifra declarada con su cálculo. El código
calcula la cifra desde el resultado aprobado, la escribe a la colombiana y arma las láminas con una plantilla
fija; la fuente y la fecha salen de la procedencia. Así ningún número que se muestra puede ser inventado.

presentacion.json:
  {"respuesta": {"titulo", "decision"},
   "scqa": {"situacion", "complicacion", "pregunta", "respuesta"},
   "hallazgos": [{"titulo", "evidencia": {"tipo": "grafico" | "tabla" | "cifra" | "hipotesis", ...}, "nota"}],
   "metodo_y_limites": {"metodo", "incertidumbre", "limites": [...]},
   "recomendacion": {"que", "quien", "proximo_paso", "como_se_mide"},
   "cifras": [{"id", "calculo": {"op", ...}, "formato": {"escala", "decimales"}}]}

Lista de comprobación (estándares validados: pirámide de Minto y SCQA, afirmación-evidencia de Alley,
Storytelling with Data, AI Index, METR y la lección de las gráficas del lanzamiento de GPT-5):
  0. presentacion.json tiene la forma de la ficha (tipos, largos, ids)
  1. el resultado que se presenta está aprobado
  2. la respuesta va primero y dice qué se pide decidir
  3. contexto SCQA completo
  4. de 1 a 5 hallazgos, cada uno con una sola evidencia válida (gráfico aprobado, tabla sin columnas personales
     ni de texto libre, hipótesis probada)
  5. cada cifra se calcula desde los datos aprobados (valores finitos; cálculos que leen datos, no constantes)
  6. los números los escribe el código: marcadores conocidos y ningún dígito, número con palabras ni «%» fuera
     de un marcador (salvo los años del período y los ids P1, S1, H1)
  7. títulos que afirman: oración con una cifra, de 6 a 22 palabras y hasta 120 caracteres; sin repetirse
  8. método, incertidumbre y límites declarados; las preguntas abiertas se nombran
  9. recomendación con qué, quién, próximo paso y cómo se mide
 10. fuente y fecha de consulta tomadas de la procedencia
 11. sin textos con forma de instrucción, sin invisibles y sin datos personales (textos y celdas de las tablas)
"""
import html
import json
import math
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from gobernanza import clasificar_columna, escanear_texto, parece_instruccion  # noqa: E402

MAX_HALLAZGOS = 5
MAX_FILAS_TABLA = 10
MAX_COLUMNAS_TABLA = 6
MAX_LIMITES = 8
MAX_CIFRAS = 40
MAX_TEXTO = 400                      # caracteres por campo: también acota el costo de los barridos
MAX_CARACTERES_TITULO = 120          # unas dos líneas en la plantilla de 16:9
MIN_PALABRAS_TITULO, MAX_PALABRAS_TITULO = 6, 22
PROFUNDIDAD_MAX = 4
ESCALAS = {None: (1.0, ""), "mil": (1e3, "mil"), "millones": (1e6, "millones"),
           "mil millones": (1e9, "mil millones"), "billones": (1e12, "billones")}
VEREDICTOS = ("se sostiene", "no se sostiene")
ID_OK = re.compile(r"[a-z][a-z0-9_]{0,29}")
MARCADOR = re.compile(r"\{([^{}]{0,40})\}")
# Magnitudes con palabras: son afirmaciones sobre los datos y van con marcador, en cualquier texto.
MAGNITUDES = re.compile(
    r"\b(dieci\w+|veinte|veinti\w+|treinta|cuarenta|cincuenta|sesenta|setenta|ochenta|noventa|cien|ciento|cientos|"
    r"\w+cientos|\w+cientas|quinient\w+|mil|miles|millar\w*|mill[oó]n|millones|bill[oó]n|billones|mitad|doble|triple|"
    r"cu[aá]druple|qu[ií]ntuple|duplic\w*|triplic\w*|cuadruplic\w*|multiplic\w*|tercio|tercios|cuart[ao]s?\s+partes?|"
    r"quinta\s+parte|d[eé]cima\s+parte|decena|decenas|centena|centenar|centenares|docena|docenas|cero|"
    r"por\s*ciento|porciento)\b", re.I)
# Los cardinales pequeños («dos implementaciones», «se calculó dos veces») cuentan cosas del método: se permiten en el
# método, la incertidumbre, los límites y la recomendación. En títulos, notas, SCQA y decisión, cada número es un marcador.
CARDINALES = re.compile(r"\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece|catorce|quince)\b", re.I)
FRASES_PERMITIDAS = ("doble conteo", "doble eje", "primera mitad", "segunda mitad")
SIGNOS_PORCENTAJE = re.compile(r"[%‰‱٪⁒]")
ABREVIADAS = re.compile(r"\{[a-z][a-z0-9_]*\}\s*(?:MM|M|K|B|mill\.?|USD|US\$|COP|€|\$|d[oó]lar\w*|euro\w*)(?![\w])|"
                        r"(?:US\$|USD|COP|€|\$)\s*\{", re.I)
ID_DE_REFERENCIA = re.compile(r"[PSH]\d{1,2}")
MAX_CELDA = 120
RELLENOS = {"ㅤ", "ᅟ", "ᅠ", "ﾠ", "͏"}


# ---------------------------------------------------------------- utilidades ----------------------------------------------------------------
def formato_co(x, dec=0):
    return f"{x:,.{dec}f}".translate(str.maketrans({",": ".", ".": ","}))


def invisibles_en(texto):
    return [c for c in str(texto) if unicodedata.category(c) in ("Cf", "Zl", "Zp", "Co", "Cs", "Cc") and c not in "\n\t" or c in RELLENOS]


def normalizar(texto):
    """NFKC (⁶ → 6, ¾ → 3⁄4) y sin caracteres de formato: lo que el lector ve, sin disfraces."""
    t = unicodedata.normalize("NFKC", str(texto))
    return "".join(c for c in t if unicodedata.category(c) != "Cf")


def leer_json(p, defecto=None):
    def no_finitos(x):
        raise ValueError(f"valor no finito {x}")
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"), parse_constant=no_finitos)
    except (OSError, ValueError):
        return defecto


# ---------------------------------------------------------------- forma ----------------------------------------------------------------
def forma(pres):
    """Valida tipos y largos antes de comprobar nada. Devuelve la lista de problemas."""
    P = []

    def texto(v, donde, obligatorio=True):
        if v is None and not obligatorio:
            return
        if not isinstance(v, str) or (obligatorio and not v.strip()):
            P.append(f"{donde}: debe ser un texto")
        elif len(v) > MAX_TEXTO:
            P.append(f"{donde}: {len(v)} caracteres (máximo {MAX_TEXTO})")

    def objeto(v, donde):
        if not isinstance(v, dict):
            P.append(f"{donde}: debe ser un objeto")
            return {}
        return v

    def entero(v, donde, lo, hi):
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            P.append(f"{donde}: debe ser un entero de {lo} a {hi}")

    if not isinstance(pres, dict):
        return ["presentacion.json debe ser un objeto"]
    r = objeto(pres.get("respuesta"), "respuesta")
    texto(r.get("titulo"), "respuesta.titulo")
    texto(r.get("decision"), "respuesta.decision")
    sc = objeto(pres.get("scqa"), "scqa")
    for k in ("situacion", "complicacion", "pregunta", "respuesta"):
        texto(sc.get(k), f"scqa.{k}")
    hall = pres.get("hallazgos")
    if not isinstance(hall, list):
        P.append("hallazgos: debe ser una lista")
        hall = []
    for i, h in enumerate(hall[:20], 1):
        h = objeto(h, f"hallazgo {i}")
        texto(h.get("titulo"), f"hallazgo {i}.titulo")
        texto(h.get("nota"), f"hallazgo {i}.nota", obligatorio=False)
        ev = objeto(h.get("evidencia"), f"hallazgo {i}.evidencia")
        t = ev.get("tipo")
        if t not in ("grafico", "tabla", "cifra", "hipotesis"):
            P.append(f"hallazgo {i}.evidencia.tipo: grafico, tabla, cifra o hipotesis")
        elif t == "tabla":
            cols = ev.get("columnas")
            if not isinstance(cols, list) or not 1 <= len(cols) <= MAX_COLUMNAS_TABLA or not all(isinstance(c, str) for c in cols):
                P.append(f"hallazgo {i}.evidencia.columnas: lista de 1 a {MAX_COLUMNAS_TABLA} nombres")
            entero(ev.get("filas"), f"hallazgo {i}.evidencia.filas", 1, MAX_FILAS_TABLA)
            if ev.get("orden") is not None and not isinstance(ev.get("orden"), str):
                P.append(f"hallazgo {i}.evidencia.orden: nombre de una columna")
        elif t == "cifra" and not isinstance(ev.get("cifra"), str):
            P.append(f"hallazgo {i}.evidencia.cifra: id de una cifra")
        elif t == "hipotesis" and not isinstance(ev.get("id"), str):
            P.append(f"hallazgo {i}.evidencia.id: id de una hipótesis")
    m = objeto(pres.get("metodo_y_limites"), "metodo_y_limites")
    texto(m.get("metodo"), "metodo_y_limites.metodo")
    texto(m.get("incertidumbre"), "metodo_y_limites.incertidumbre")
    lim = m.get("limites")
    if not isinstance(lim, list) or len(lim) > MAX_LIMITES:
        P.append(f"metodo_y_limites.limites: lista de hasta {MAX_LIMITES} textos")
    else:
        for i, x in enumerate(lim, 1):
            texto(x, f"limite {i}")
    rec = objeto(pres.get("recomendacion"), "recomendacion")
    for k in ("que", "quien", "proximo_paso", "como_se_mide"):
        texto(rec.get(k), f"recomendacion.{k}")
    cif = pres.get("cifras")
    if not isinstance(cif, list) or len(cif) > MAX_CIFRAS:
        P.append(f"cifras: lista de hasta {MAX_CIFRAS}")
        cif = []
    ids = []
    for i, x in enumerate(cif, 1):
        x = objeto(x, f"cifra {i}")
        cid = x.get("id")
        if not isinstance(cid, str) or not ID_OK.fullmatch(cid):
            P.append(f"cifra {i}.id: minúsculas, dígitos y _ (empieza con letra, hasta 30)")
        ids.append(cid)
        objeto(x.get("calculo"), f"cifra {i}.calculo")
        f = x.get("formato")
        if f is not None:
            f = objeto(f, f"cifra {i}.formato")
            if f.get("escala") not in ESCALAS:
                P.append(f"cifra {i}.formato.escala: una de {[k for k in ESCALAS if k]} o null")
            if f.get("decimales") is not None:
                entero(f.get("decimales"), f"cifra {i}.formato.decimales", 0, 3)
        if "texto" in x:
            P.append(f"cifra {i}: no lleva «texto»; el número lo escribe el código desde el cálculo")
    if len([c for c in ids if isinstance(c, str)]) != len({c for c in ids if isinstance(c, str)}):
        P.append("cifras: hay ids repetidos")
    return P


# ---------------------------------------------------------------- cálculo ----------------------------------------------------------------
class ErrorCalculo(Exception):
    pass


def _num(v):
    if v is None or isinstance(v, bool):
        raise ErrorCalculo("valor vacío o booleano en una columna numérica")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ErrorCalculo(f"valor no numérico: {str(v)[:30]}")
    if not math.isfinite(x):
        raise ErrorCalculo("valor no finito (NaN o infinito) en los datos")
    return x


def _filtrar(filas, donde, columnas):
    if donde is None:
        return filas
    if not isinstance(donde, dict) or not donde:
        raise ErrorCalculo("«donde» debe ser un objeto {columna: valor}")
    for k, v in donde.items():
        if k not in columnas:
            raise ErrorCalculo(f"«donde» usa la columna «{k}», que no está en el resultado")
        if not isinstance(v, (str, int, float)) or isinstance(v, bool):
            raise ErrorCalculo("«donde» compara con un texto o un número")
    return [f for f in filas if all(str(f.get(k)) == str(v) for k, v in donde.items())]


def _entero(v, nombre):
    if not isinstance(v, int) or isinstance(v, bool):
        raise ErrorCalculo(f"«{nombre}» debe ser un entero")
    return v


def calcular(calc, ctx, prof=0):
    """Calcula una cifra desde el resultado aprobado, las hipótesis probadas o la procedencia. Sin IA."""
    if prof > PROFUNDIDAD_MAX:
        raise ErrorCalculo("cálculo demasiado anidado")
    if not isinstance(calc, dict):
        raise ErrorCalculo("el cálculo debe ser un objeto con «op»")
    op = calc.get("op")
    filas = ctx["resultado"]
    columnas = set(filas[0].keys()) if filas else set()
    if calc.get("como") is not None and op != "hipotesis":
        raise ErrorCalculo("«como» solo se usa con op hipotesis")

    def col():
        c = calc.get("columna")
        if c not in columnas:
            raise ErrorCalculo(f"la columna «{c}» no está en el resultado aprobado")
        return c

    if op == "conteo":
        sel = _filtrar(filas, calc.get("donde"), columnas)
        if "primeros" in calc:
            if prof > 0:
                raise ErrorCalculo("«primeros» es una constante: solo como cifra directa, nunca dentro de otro cálculo")
            n = _entero(calc["primeros"], "primeros")
            if not 1 <= n <= len(sel):
                raise ErrorCalculo(f"«primeros» = {n} y hay {len(sel)} filas")
            return float(n)
        return float(len(sel))
    if op == "suma":
        c = col()
        return math.fsum(_num(f.get(c)) for f in _filtrar(filas, calc.get("donde"), columnas))
    if op in ("maximo", "minimo"):
        c = col()
        vals = [_num(f.get(c)) for f in _filtrar(filas, calc.get("donde"), columnas)]
        if not vals:
            raise ErrorCalculo("no hay filas que cumplan «donde»")
        return max(vals) if op == "maximo" else min(vals)
    if op == "valor":
        c = col()
        sel = _filtrar(filas, calc.get("donde"), columnas)
        if calc.get("donde") is None or len(sel) != 1:
            raise ErrorCalculo(f"«donde» debe señalar una fila y señala {len(sel)}")
        return _num(sel[0].get(c))
    if op == "suma_primeros":
        c = col()
        n = _entero(calc.get("n"), "n")
        if not 1 <= n <= len(filas):
            raise ErrorCalculo(f"n = {n} y hay {len(filas)} filas")
        return math.fsum(sorted((_num(f.get(c)) for f in filas), reverse=True)[:n])
    if op in ("porcentaje", "cociente", "diferencia"):
        a = calcular(calc.get("parte") if op == "porcentaje" else calc.get("a"), ctx, prof + 1)
        b = calcular(calc.get("total") if op == "porcentaje" else calc.get("b"), ctx, prof + 1)
        if op == "diferencia":
            return a - b
        if b == 0:
            raise ErrorCalculo("división por cero")
        return 100 * a / b if op == "porcentaje" else a / b
    if op == "hipotesis":
        if ctx["hipotesis_estado"] != "probadas":
            raise ErrorCalculo(f"las hipótesis no están probadas (estado «{ctx['hipotesis_estado']}»)")
        h = {x.get("id"): x for x in ctx["hipotesis"] if isinstance(x, dict)}.get(calc.get("id"))
        if not h or h.get("veredicto") not in VEREDICTOS:
            raise ErrorCalculo(f"no hay una hipótesis probada con id {calc.get('id')}")
        campo = calc.get("campo") or "valor"
        if campo not in ("valor", "linea_base_valor", "umbral"):
            raise ErrorCalculo("«campo»: valor, linea_base_valor o umbral")
        v = (h.get("umbral") or {}).get("valor") if campo == "umbral" else h.get(campo)
        if calc.get("como") not in (None, "porcentaje"):
            raise ErrorCalculo("«como» solo admite porcentaje")
        return _num(v) * (100 if calc.get("como") == "porcentaje" else 1)
    if op == "filas_fuente":
        return _num(ctx["procedencia"].get("filas"))
    raise ErrorCalculo(f"operación desconocida: {str(op)[:30]!r}")


def es_porcentaje(calc):
    return isinstance(calc, dict) and (calc.get("op") == "porcentaje" or (calc.get("op") == "hipotesis" and calc.get("como") == "porcentaje"))


def escribir_cifra(valor, cifra):
    f = cifra.get("formato") or {}
    factor, palabra = ESCALAS[f.get("escala")]
    v = valor / factor
    dec = f.get("decimales")
    if dec is None:
        dec = 0 if abs(v) >= 100 or float(v).is_integer() else 1
    redondo = round(v, dec)
    if v != 0 and redondo == 0:
        raise ErrorCalculo(f"con {dec} decimales se mostraría 0 y el valor no es 0: use más decimales u otra escala")
    if es_porcentaje(cifra.get("calculo")) and v < 100 and redondo >= 100:
        raise ErrorCalculo(f"con {dec} decimales se mostraría 100 % y el valor es menor: use más decimales")
    if redondo == 0:
        v = 0.0                                      # nunca «-0»
    s = formato_co(v, dec)
    if palabra:
        s += " " + palabra
    if es_porcentaje(cifra.get("calculo")):
        s += " %"
    return s


def poner_cifras(texto, escritas):
    return MARCADOR.sub(lambda m: escritas.get(m.group(1), m.group(0)), str(texto or ""))


def publicar_con_tramos(texto, escritas):
    """El texto ya publicado y los tramos [inicio, fin) que escribió el código (uno por marcador)."""
    t, partes, tramos, pos, largo = str(texto or ""), [], [], 0, 0
    for m in MARCADOR.finditer(t):
        antes = t[pos:m.start()]
        partes.append(antes)
        largo += len(antes)
        s = escritas.get(m.group(1), m.group(0))
        partes.append(s)
        tramos.append((largo, largo + len(s)))
        largo += len(s)
        pos = m.end()
    partes.append(t[pos:])
    return "".join(partes), tramos


def normal_sellado(texto):
    return " ".join(re.sub(r"[^\w.,%-]+", " ", normalizar(texto).lower()).split())


# ---------------------------------------------------------------- carga ----------------------------------------------------------------
def procedencia_de(c):
    for p in (c / "procedencia.json", c / "datos" / "procedencia.json"):
        if p.exists():
            return leer_json(p, {}) or {}
    spec = leer_json(c / "spec.json")
    if spec:
        try:
            import verificar_grafico
            from rutas import resolver_datos
            return verificar_grafico.procedencia_de(c, resolver_datos(spec)) or {}
        except Exception:
            return {}
    return {}


def textos_de(pres):
    """Todos los textos que escribió la IA, con su lugar: [(lugar, texto)]."""
    L = []
    r = pres.get("respuesta") or {}
    L += [("respuesta.titulo", r.get("titulo")), ("respuesta.decision", r.get("decision"))]
    for k in ("situacion", "complicacion", "pregunta", "respuesta"):
        L.append((f"scqa.{k}", (pres.get("scqa") or {}).get(k)))
    for i, h in enumerate(pres.get("hallazgos") or [], 1):
        L += [(f"hallazgo {i}.titulo", h.get("titulo")), (f"hallazgo {i}.nota", h.get("nota"))]
    m = pres.get("metodo_y_limites") or {}
    L += [("metodo", m.get("metodo")), ("incertidumbre", m.get("incertidumbre"))]
    L += [(f"limite {i}", x) for i, x in enumerate(m.get("limites") or [], 1)]
    for k in ("que", "quien", "proximo_paso", "como_se_mide"):
        L.append((f"recomendacion.{k}", (pres.get("recomendacion") or {}).get(k)))
    return [(lugar, t) for lugar, t in L if isinstance(t, str)]


def lleno(x, palabras=3):
    return isinstance(x, str) and len(x.split()) >= palabras


def celdas_de_tabla(ev, resultado):
    cols = [c for c in ev.get("columnas") or [] if resultado and c in resultado[0]]
    orden = ev.get("orden") if resultado and ev.get("orden") in resultado[0] else None
    filas = list(resultado)
    if orden:
        def clave(f):
            try:
                x = float(f.get(orden))
                return -x if math.isfinite(x) else 0.0
            except (TypeError, ValueError):
                return 0.0
        filas.sort(key=clave)
    filas = filas[: int(ev.get("filas") or 5)]
    cuerpo = []
    for f in filas:
        fila = []
        for c in cols:
            v = f.get(c)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)):
                if float(v).is_integer() and 1900 <= v <= 2100:
                    fila.append((str(int(v)), True))            # un año no lleva punto de miles
                else:
                    fila.append((formato_co(v, 0 if float(v).is_integer() or abs(v) >= 1000 else 2), True))
            else:
                s = " ".join(str(v if v is not None else "").split())
                fila.append((s if len(s) <= MAX_CELDA else s[:MAX_CELDA - 1] + "…", False))   # lo que se dibuja es lo que se barre
        cuerpo.append(fila)
    return cols, cuerpo


# ---------------------------------------------------------------- comprobación ----------------------------------------------------------
def comprobar(c):
    checks = []

    def chk(nombre, ok, detalle):
        checks.append({"comprobacion": nombre, "ok": bool(ok), "detalle": detalle})

    pres = leer_json(c / "presentacion.json")
    problemas = forma(pres) if pres is not None else ["falta presentacion.json o no es JSON válido"]
    chk("presentacion.json tiene la forma de la ficha", not problemas, "bien" if not problemas else "; ".join(problemas[:8]))
    if problemas:
        return checks, None

    inf = leer_json(c / "informe.json", {}) or {}
    resultado = [f for f in (inf.get("resultado_oficial") or []) if isinstance(f, dict)]
    hip = leer_json(c / "hipotesis_resultado.json", {}) or {}
    hipotesis = [x for x in (hip.get("hipotesis") or []) if isinstance(x, dict)]
    graf = leer_json(c / "grafico_verificacion.json", {}) or {}
    graf_meta = leer_json(c / "grafico.json", {}) or {}
    spec = leer_json(c / "spec.json", {}) or {}
    proc = procedencia_de(c)
    ctx = {"resultado": resultado, "hipotesis": hipotesis, "hipotesis_estado": hip.get("estado"), "procedencia": proc}
    columnas = set(resultado[0].keys()) if resultado else set()

    estado = inf.get("estado")
    chk("el resultado que se presenta está aprobado", estado == "aprobado" and bool(resultado),
        f"informe.json: estado «{estado}», {len(resultado)} filas" + ("" if estado == "aprobado" else " (no se presenta un resultado sin aprobar)"))

    r, sc = pres["respuesta"], pres["scqa"]
    chk("la respuesta va primero y dice qué se pide decidir", lleno(r["titulo"]) and lleno(r["decision"]),
        "presentes" if lleno(r["titulo"]) and lleno(r["decision"]) else "falta la conclusión o la decisión (3 palabras o más)")
    falta = [k for k in ("situacion", "complicacion", "pregunta", "respuesta") if not lleno(sc.get(k))]
    chk("contexto SCQA completo (situación, complicación, pregunta, respuesta)", not falta, "completo" if not falta else f"falta: {falta}")

    # cifras: se calculan desde los datos y las escribe el código
    cifras = {x["id"]: x for x in pres["cifras"]}
    escritas, errores = {}, []
    for cid, x in cifras.items():
        try:
            v = calcular(x["calculo"], ctx)
            if not math.isfinite(v):
                raise ErrorCalculo("el cálculo no da un número finito")
            escritas[cid] = escribir_cifra(v, x)
        except (ErrorCalculo, ValueError, TypeError, OverflowError, RecursionError) as e:
            errores.append(f"{cid}: {e}")
    chk("cada cifra se calcula desde los datos aprobados", cifras and not errores,
        (f"{len(escritas)} de {len(cifras)} cifras calculadas: " + ", ".join(f"{k} = {v}" for k, v in list(escritas.items())[:8])
         if cifras else "no hay cifras declaradas") + (f" · {errores[:5]}" if errores else ""))

    # hallazgos y evidencias
    hall = pres["hallazgos"]
    malas, tablas = [], {}
    ids_hip = {x.get("id") for x in hipotesis if x.get("veredicto") in VEREDICTOS} if hip.get("estado") == "probadas" else set()
    for i, h in enumerate(hall, 1):
        ev = h["evidencia"]
        t = ev["tipo"]
        if t == "grafico" and graf.get("estado") != "aprobado":
            malas.append(f"hallazgo {i}: el gráfico no está aprobado por verificar_grafico.py")
        elif t == "tabla":
            cols = ev["columnas"]
            fuera = [x for x in cols if x not in columnas]
            sensibles = [x for x in cols if clasificar_columna(x)]
            if fuera:
                malas.append(f"hallazgo {i}: columnas que no están en el resultado: {fuera}")
            if sensibles:
                malas.append(f"hallazgo {i}: columnas personales o de texto libre: {sensibles}")
            if ev.get("orden") is not None and ev["orden"] not in columnas:
                malas.append(f"hallazgo {i}: no existe la columna de orden «{ev['orden']}»")
            tablas[i] = celdas_de_tabla(ev, resultado)
        elif t == "cifra" and ev["cifra"] not in escritas:
            malas.append(f"hallazgo {i}: la cifra «{ev['cifra']}» no está declarada o no se pudo calcular")
        elif t == "hipotesis" and ev["id"] not in ids_hip:
            malas.append(f"hallazgo {i}: «{ev['id']}» no es una hipótesis probada (estado «{hip.get('estado')}»)")
        elif t == "hipotesis" and not isinstance(({x.get("id"): x for x in hipotesis}.get(ev["id"]) or {}).get("umbral"), dict):
            malas.append(f"hallazgo {i}: la hipótesis «{ev['id']}» no trae un umbral con operador y valor")
    ok_n = 1 <= len(hall) <= MAX_HALLAZGOS
    chk(f"de 1 a {MAX_HALLAZGOS} hallazgos, cada uno con una sola evidencia válida", ok_n and not malas,
        (f"{len(hall)} hallazgos" if ok_n else f"{len(hall)} hallazgos (deben ser de 1 a {MAX_HALLAZGOS})") + (f" · {malas}" if malas else ""))

    # los números los escribe el código
    textos = textos_de(pres)
    contexto = " ".join(str(v) for v in [spec.get("peticion"), inf.get("peticion"), (proc.get("fuente") or {}).get("filtro_legible"),
                                         proc.get("cita"), graf_meta.get("periodo"), str(proc.get("consultado") or "")[:4]] if v)
    anios = set(re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", contexto))
    ids_ok = {str(p.get("id")) for p in (spec.get("preguntas") or []) + (spec.get("supuestos") or []) if isinstance(p, dict) and p.get("id")}
    ids_ok |= {str(x.get("id")) for x in hipotesis if x.get("id")}
    ids_ok = {x for x in ids_ok if ID_DE_REFERENCIA.fullmatch(x)}
    # Lo sellado antes de la presentación (especificación, hipótesis registradas, procedencia): un número que aparece
    # ahí, con las mismas palabras, es una cita literal (un umbral, un corte, el id del conjunto), no una cifra nueva.
    hip_sellada = leer_json(c / "hipotesis.json", []) or []
    fte = proc.get("fuente") if isinstance(proc.get("fuente"), dict) else {}
    sellado = normal_sellado(" ".join(
        [json.dumps([spec.get(k) for k in ("peticion", "interpretacion", "definiciones", "supuestos", "preguntas")], ensure_ascii=False)]
        + [str(h.get(k) or "") for h in hip_sellada if isinstance(h, dict) for k in ("enunciado", "medida", "linea_base")]
        + [str(v) for v in (proc.get("cita"), fte.get("filtro_legible"), fte.get("conjunto"), graf_meta.get("periodo")) if v]))
    palabras_selladas = set(sellado.split())
    sueltos, desconocidos = [], []
    for lugar, t in textos:
        for m in MARCADOR.finditer(t):
            if m.group(1) not in cifras:
                desconocidos.append(f"{lugar}: «{m.group(0)[:30]}»")
        if MARCADOR.sub("", t).count("{") or MARCADOR.sub("", t).count("}"):
            desconocidos.append(f"{lugar}: llaves sueltas")
        resto = normalizar(MARCADOR.sub(" ", t))
        for m in re.finditer(r"[\w-]*\d(?:[\w.,-]*\w)?", resto):
            tok = m.group(0)
            if tok in anios or tok in ids_ok:
                continue
            frase = " ".join(normal_sellado(resto[m.start():m.start() + 80]).split()[:2])
            if (len(tok) >= 3 and normal_sellado(tok) in palabras_selladas) or (frase and f" {frase} " in f" {sellado} "):
                continue
            sueltos.append(f"{lugar}: «{tok[:20]}»")
        raros = sorted({ch for ch in resto if not ch.isascii() and unicodedata.numeric(ch, None) is not None})
        if raros:
            sueltos.append(f"{lugar}: caracteres numéricos {raros[:5]}")
        for m in MAGNITUDES.finditer(resto):
            frase = " ".join(resto[m.start():m.start() + 80].lower().split()[:2])
            if frase in FRASES_PERMITIDAS or f" {normal_sellado(frase)} " in f" {sellado} ":
                continue
            sueltos.append(f"{lugar}: «{m.group(0)}» (magnitud con palabras)")
        if not lugar.startswith(("metodo", "incertidumbre", "limite", "recomendacion")):
            for m in CARDINALES.finditer(resto):
                sueltos.append(f"{lugar}: «{m.group(0)}» (fuera del método y los límites, cada número es un marcador)")
        if SIGNOS_PORCENTAJE.search(resto):
            sueltos.append(f"{lugar}: «%» fuera de un marcador")
        for m in ABREVIADAS.finditer(t):
            sueltos.append(f"{lugar}: «{m.group(0)[:20]}» (escala abreviada o moneda junto a un marcador)")
        publicado, tramos = publicar_con_tramos(t, escritas)
        for m in re.finditer(r"\d(?:[\d.,]*\d)?", publicado):
            a, b = m.span()
            toca = [tr for tr in tramos if tr[0] < b and a < tr[1]]
            if toca and not (len(toca) == 1 and toca[0][0] <= a and b <= toca[0][1]):
                sueltos.append(f"{lugar}: «{publicado[max(0, a - 3):b + 3]}» (marcadores pegados forman otro número)")
    ok_num = not sueltos and not desconocidos
    chk("los números los escribe el código (marcadores {id}, ningún número a mano)", ok_num,
        "todos los números salen de cifras declaradas" if ok_num else
        "; ".join((["marcadores desconocidos: " + ", ".join(desconocidos[:10])] if desconocidos else [])
                  + ([f"{len(sueltos)} números escritos a mano (use un marcador con su cifra): " + ", ".join(sueltos[:30])] if sueltos else [])))

    # títulos que afirman (se miden ya con las cifras puestas)
    titulos = [("respuesta", r["titulo"])] + [(f"hallazgo {i}", h["titulo"]) for i, h in enumerate(hall, 1)]
    problemas = []
    for lugar, t in titulos:
        vista = poner_cifras(t, escritas)
        n_pal = len(vista.split())
        if not MIN_PALABRAS_TITULO <= n_pal <= MAX_PALABRAS_TITULO:
            problemas.append(f"{lugar}: {n_pal} palabras (de {MIN_PALABRAS_TITULO} a {MAX_PALABRAS_TITULO}: una afirmación, no un tema)")
        if len(vista) > MAX_CARACTERES_TITULO:
            problemas.append(f"{lugar}: {len(vista)} caracteres (máximo {MAX_CARACTERES_TITULO}, unas dos líneas)")
        if vista.rstrip().endswith((":", "?")):
            problemas.append(f"{lugar}: termina en «{vista.rstrip()[-1]}»; un título afirma")
        if not any(m.group(1) in escritas for m in MARCADOR.finditer(t)):
            problemas.append(f"{lugar}: sin una cifra; el título dice el hallazgo con su número")
    vistos = [poner_cifras(t, escritas).strip().lower() for _, t in titulos]
    if len(set(vistos)) != len(vistos):
        problemas.append("hay títulos repetidos")
    chk("títulos que afirman: oración con una cifra, de 6 a 22 palabras y hasta 120 caracteres", not problemas,
        "todos afirman con cifra" if not problemas else "; ".join(problemas[:6]))

    # método y límites
    m = pres["metodo_y_limites"]
    limites = [x for x in m["limites"] if x.strip()]
    ids_abiertas = [str(p.get("id")) for p in (spec.get("preguntas") or []) if isinstance(p, dict) and p.get("id")]
    abiertas = inf.get("preguntas_abiertas")
    n_abiertas = abiertas if isinstance(abiertas, int) and not isinstance(abiertas, bool) else len(abiertas) if isinstance(abiertas, list) else 0
    texto_lim = " ".join(limites + [m["incertidumbre"], m["metodo"]])
    sin_nombrar = [p for p in ids_abiertas if n_abiertas and not re.search(rf"(?<!\w){re.escape(p)}(?!\w)", texto_lim)]
    ok_m = lleno(m["metodo"]) and lleno(m["incertidumbre"], 2) and bool(limites) and not sin_nombrar
    chk("método, incertidumbre y límites declarados; preguntas abiertas nombradas", ok_m,
        f"{len(limites)} límites" + ("" if lleno(m["metodo"]) else " · falta el método")
        + ("" if lleno(m["incertidumbre"], 2) else " · falta la incertidumbre (o «no aplica» con el motivo)")
        + ("" if limites else " · sin límites")
        + (f" · preguntas abiertas sin nombrar: {sin_nombrar}" if sin_nombrar else ""))

    rec = pres["recomendacion"]
    falta = [k for k in ("que", "quien", "proximo_paso", "como_se_mide") if not lleno(rec.get(k), 2)]
    chk("recomendación con qué, quién, próximo paso y cómo se mide", not falta, "completa" if not falta else f"falta: {falta}")

    fuente = (proc.get("fuente") or {}).get("titulo") if isinstance(proc.get("fuente"), dict) else None
    fuente = fuente or proc.get("cita")
    consultado = str(proc.get("consultado") or "")[:10]
    try:
        date.fromisoformat(consultado)
        ok_f = isinstance(fuente, str) and bool(fuente.strip())
    except ValueError:
        ok_f = False
    chk("fuente y fecha de consulta tomadas de la procedencia", ok_f,
        f"«{fuente}», consultado {consultado}" if ok_f else "la procedencia no trae fuente o fecha: la lámina no se puede citar")

    # barridos sobre lo que se publica: textos con las cifras puestas y celdas de las tablas
    publicados = [poner_cifras(t, escritas) for _, t in textos]
    publicados += [txt for cols, cuerpo in tablas.values() for txt in cols + [v for fila in cuerpo for v, _ in fila]]
    publicados = [" ".join(x.split()) for x in publicados]      # sin rachas de espacios: los barridos no se atascan
    ordenes = [t[:60] for t in publicados if parece_instruccion(t)]
    chk("sin textos con forma de instrucción para una IA", not ordenes, "ninguno" if not ordenes else f"{ordenes[:2]}")
    invis = [t[:40] for t in publicados + [t for _, t in textos] if invisibles_en(t)]
    chk("sin caracteres invisibles o bidireccionales", not invis, "ninguno" if not invis else f"{len(invis)} textos")
    pii = escanear_texto(" ".join(x[:MAX_TEXTO] for x in publicados))
    chk("sin datos personales en los textos ni en las tablas", not pii, str(pii or "ninguno"))

    return checks, {"pres": pres, "ctx": ctx, "cifras": cifras, "escritas": escritas, "tablas": tablas, "proc": proc,
                    "graf_ok": graf.get("estado") == "aprobado", "informe_final": (c / "informe_final.html").exists()}


# ---------------------------------------------------------------- plantilla ----------------------------------------------------------------
CSS = """
:root{color-scheme:light;--bg:#f1f0ec;--slide:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#6b6964;--line:#e1e0d9;--accent:#2a78d6;--wash:rgba(42,120,214,.10)}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#0d0d0d;--slide:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#a3a19b;--line:#2c2c2a;--accent:#3987e5;--wash:rgba(57,135,229,.14)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}
.slide{width:min(1100px,100vw - 32px);aspect-ratio:16/9;margin:24px auto;background:var(--slide);border:1px solid var(--line);border-radius:12px;
  padding:40px 48px 28px;display:flex;flex-direction:column;overflow:hidden}
.kicker{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
h1,h2{margin:0 0 10px;line-height:1.18;letter-spacing:-.01em;max-width:30em}h1{font-size:34px}h2{font-size:27px}
.sub{color:var(--ink2);margin:0 0 14px}.body{flex:1;min-height:0;display:flex;flex-direction:column;gap:12px}
.foot{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:8px;margin-top:10px}
.scqa{display:grid;grid-template-columns:1fr 1fr;gap:12px}.scqa div{border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.scqa b{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--accent)}
ol.res{margin:0;padding-left:22px;font-size:20px}ol.res li{margin:0 0 10px}
.hero{font-size:72px;font-weight:700;letter-spacing:-.02em;margin:10px 0 0}.nota{color:var(--ink2);border-left:3px solid var(--accent);padding:4px 12px;margin:0}
.marco{flex:1;min-height:0;overflow:hidden;border-radius:8px;background:#fff}
.marco iframe{display:block;border:0;width:100%;height:640px;zoom:.72}
.centro{justify-content:center}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line)}
th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.h{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.h div{border:1px solid var(--line);border-radius:10px;padding:12px}
.h b{display:block;font-size:12px;color:var(--muted);text-transform:uppercase}.h span{font-size:28px;font-weight:700}
.dec{background:var(--wash);border-radius:10px;padding:14px 16px;font-size:19px}ul.lim{margin:0;padding-left:20px}
@media print{body{background:#fff}.slide{width:100%;margin:0;border:0;border-radius:0;page-break-after:always}@page{size:landscape;margin:0}}
@media (max-width:700px){.slide{aspect-ratio:auto;padding:24px 18px}.scqa,.h{grid-template-columns:1fr}.hero{font-size:48px}h1{font-size:26px}h2{font-size:21px}}
"""


def _e(x):
    return html.escape(str(x if x is not None else ""))


def _hipotesis(hid, ctx, cifras):
    h = {x.get("id"): x for x in ctx["hipotesis"]}.get(hid) or {}
    u = h.get("umbral") or {}
    # Si el presentador la escribió como porcentaje, la lámina la muestra igual que el título (0,824 → 82,4 %).
    pct = any(isinstance(x.get("calculo"), dict) and x["calculo"].get("op") == "hipotesis" and x["calculo"].get("id") == hid
              and x["calculo"].get("como") == "porcentaje" for x in cifras.values())
    signo = {">=": "≥", "<=": "≤", ">": ">", "<": "<", "entre": "entre"}.get(str(u.get("operador")), "")

    def f(v):
        if isinstance(v, list):
            return " y ".join(f(x) for x in v[:2])
        try:
            v = float(v)
            if not math.isfinite(v):
                raise ValueError
        except (TypeError, ValueError):
            return "—"
        return formato_co(100 * v, 1) + " %" if pct else formato_co(v, 3 if abs(v) < 10 else 0)
    return (f'<p class="sub">{_e(h.get("id"))} · veredicto del código: <b>{_e(h.get("veredicto"))}</b></p>'
            f'<div class="h"><div><b>Valor medido</b><span>{f(h.get("valor"))}</span></div>'
            f'<div><b>Umbral sellado</b><span>{_e(signo)} {f(u.get("valor"))}</span></div>'
            f'<div><b>Línea base</b><span>{f(h.get("linea_base_valor"))}</span></div></div>')


def renderizar(datos):
    pres, ctx, cifras, escritas, proc = datos["pres"], datos["ctx"], datos["cifras"], datos["escritas"], datos["proc"]

    def tx(t):
        return _e(poner_cifras(t, escritas))
    fuente = (proc.get("fuente") or {}).get("titulo") if isinstance(proc.get("fuente"), dict) else None
    try:
        fecha = f"{date.fromisoformat(str(proc.get('consultado'))[:10]):%d-%m-%Y}"
    except ValueError:
        fecha = "sin fecha de consulta"
    cita = str(proc.get("cita") or fuente or "fuente sin declarar")
    pie = f'<div class="foot">Fuente: {_e(cita)}' + ("" if fecha in cita else f" · consultado el {_e(fecha)}") + "</div>"
    r, sc, hall = pres["respuesta"], pres["scqa"], pres["hallazgos"]
    L = []
    L.append(f'<section class="slide"><p class="kicker">Respuesta</p><h1>{tx(r["titulo"])}</h1>'
             f'<div class="body centro"><p class="dec"><b>Lo que se pide decidir:</b> {tx(r["decision"])}</p></div>{pie}</section>')
    L.append('<section class="slide"><p class="kicker">Contexto</p><h2>' + tx(sc["pregunta"]) + '</h2><div class="body scqa">'
             + "".join(f"<div><b>{n}</b>{tx(sc[k])}</div>" for k, n in
                       (("situacion", "Situación"), ("complicacion", "Complicación"), ("pregunta", "Pregunta"), ("respuesta", "Respuesta")))
             + f"</div>{pie}</section>")
    L.append('<section class="slide"><p class="kicker">Resumen ejecutivo</p><h2>' + tx(r["titulo"]) + '</h2><div class="body"><ol class="res">'
             + "".join(f"<li>{tx(h['titulo'])}</li>" for h in hall) + f"</ol></div>{pie}</section>")
    for i, h in enumerate(hall, 1):
        ev = h["evidencia"]
        t = ev["tipo"]
        if t == "grafico":
            cuerpo = '<div class="marco"><iframe src="grafico.html" title="Gráfico aprobado" sandbox="allow-scripts"></iframe></div>'
        elif t == "tabla":
            cols, filas = datos["tablas"][i]
            head = "".join(f"<th>{_e(c)}</th>" for c in cols)
            cuerpo = (f"<table><thead><tr>{head}</tr></thead><tbody>"
                      + "".join("<tr>" + "".join(f'<td class="n">{_e(v)}</td>' if n else f"<td>{_e(v)}</td>" for v, n in fila) + "</tr>" for fila in filas)
                      + "</tbody></table>")
        elif t == "cifra":
            cuerpo = f'<p class="hero">{_e(escritas.get(ev["cifra"]))}</p>'
        else:
            cuerpo = _hipotesis(ev["id"], ctx, cifras)
        nota = f'<p class="nota">{tx(h.get("nota"))}</p>' if h.get("nota") else ""
        L.append(f'<section class="slide"><p class="kicker">Hallazgo {i} de {len(hall)}</p><h2>{tx(h["titulo"])}</h2>'
                 f'<div class="body">{cuerpo}{nota}</div>{pie}</section>')
    m = pres["metodo_y_limites"]
    n_fuente = proc.get("filas")
    L.append('<section class="slide"><p class="kicker">Método y límites</p><h2>Qué se hizo y qué no se puede concluir</h2><div class="body">'
             f'<p><b>Método:</b> {tx(m["metodo"])}</p><p><b>Incertidumbre:</b> {tx(m["incertidumbre"])}</p>'
             + (f"<p><b>Filas de la fuente:</b> {_e(formato_co(float(n_fuente)))}</p>"
                if isinstance(n_fuente, (int, float)) and not isinstance(n_fuente, bool) and math.isfinite(float(n_fuente)) else "")
             + '<ul class="lim">' + "".join(f"<li>{tx(x)}</li>" for x in m["limites"]) + f"</ul></div>{pie}</section>")
    rec = pres["recomendacion"]
    L.append('<section class="slide"><p class="kicker">Recomendación</p><h2>' + tx(rec["que"]) + '</h2><div class="body"><div class="h">'
             f'<div><b>Quién</b>{tx(rec["quien"])}</div><div><b>Próximo paso</b>{tx(rec["proximo_paso"])}</div>'
             f'<div><b>Cómo se mide</b>{tx(rec["como_se_mide"])}</div></div></div>{pie}</section>')
    titulos = [r["titulo"]] + [h["titulo"] for h in hall]
    anexo = [x for x, ok in (('<a href="informe_final.html">informe final</a>', datos["informe_final"]),
                             ('<a href="grafico.html">gráfico</a>', datos["graf_ok"])) if ok]
    L.append('<section class="slide"><p class="kicker">Prueba de los títulos</p><h2>Si solo se leen los títulos, ¿se entiende el argumento?</h2>'
             '<div class="body"><ol class="res">' + "".join(f"<li>{tx(t)}</li>" for t in titulos) + "</ol>"
             + (f'<p class="sub">Anexo: {" · ".join(anexo)}</p>' if anexo else "") + "</div>" + pie + "</section>")
    titulo_doc = _e(poner_cifras(r["titulo"], escritas)[:80])
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{titulo_doc}</title><style>{CSS}</style></head><body>{''.join(L)}</body></html>")


# ---------------------------------------------------------------- autoprueba ----------------------------------------------------------------
def _base():
    """Ventas sintéticas en pesos (no son datos reales) y una presentación que cumple todo."""
    resultado = [{"region": r, "ventas": v * 1e6, "pedidos": p} for r, v, p in
                 [("Norte", 420, 60), ("Centro", 300, 50), ("Sur", 150, 30), ("Oriente", 80, 12), ("Occidente", 50, 8)]]
    pct = lambda parte: {"op": "porcentaje", "parte": parte, "total": {"op": "suma", "columna": "ventas"}}  # noqa: E731
    pres = {
        "respuesta": {"titulo": "La región Norte vende el {pct_norte} del total del semestre y lidera las ventas por región",
                      "decision": "Si se refuerza el inventario del Norte antes que el de las demás regiones."},
        "scqa": {"situacion": "La empresa vende en {n_regiones} regiones con el mismo inventario.",
                 "complicacion": "Las ventas no se reparten igual entre las regiones.",
                 "pregunta": "¿Dónde conviene poner el inventario del próximo semestre?",
                 "respuesta": "En el Norte primero, porque vende el {pct_norte} del total."},
        "hallazgos": [
            {"titulo": "El Norte vendió {norte}, más que las regiones menores juntas, que suman {menores}",
             "evidencia": {"tipo": "tabla", "columnas": ["region", "ventas"], "orden": "ventas", "filas": 5},
             "nota": "Las regiones menores son el Sur, el Oriente y el Occidente."},
            {"titulo": "Las regiones Norte y Centro concentran el {top2} de las ventas del semestre",
             "evidencia": {"tipo": "cifra", "cifra": "top2"}, "nota": "El resto se reparte entre las otras regiones."},
        ],
        "metodo_y_limites": {"metodo": "Suma de ventas aprobadas por región, calculada por dos implementaciones independientes.",
                             "incertidumbre": "No aplica: son todas las ventas del semestre, no una muestra.",
                             "limites": ["P1: no se sabe si las devoluciones se restan; por defecto no se restan."]},
        "recomendacion": {"que": "Reforzar primero el inventario del Norte", "quien": "Gerencia comercial",
                          "proximo_paso": "Plan de inventario por región", "como_se_mide": "Ventas por región del próximo semestre frente a este"},
        "cifras": [
            {"id": "pct_norte", "calculo": pct({"op": "valor", "columna": "ventas", "donde": {"region": "Norte"}}), "formato": {"decimales": 0}},
            {"id": "n_regiones", "calculo": {"op": "conteo"}},
            {"id": "norte", "calculo": {"op": "valor", "columna": "ventas", "donde": {"region": "Norte"}}, "formato": {"escala": "millones", "decimales": 0}},
            {"id": "menores", "calculo": {"op": "diferencia", "a": {"op": "suma", "columna": "ventas"},
                                          "b": {"op": "suma_primeros", "columna": "ventas", "n": 2}}, "formato": {"escala": "millones", "decimales": 0}},
            {"id": "top2", "calculo": pct({"op": "suma_primeros", "columna": "ventas", "n": 2}), "formato": {"decimales": 0}},
        ],
    }
    hip = {"estado": "probadas", "problemas": [],
           "hipotesis": [{"id": "H1", "valor": 0.42, "umbral": {"operador": ">=", "valor": 0.3}, "linea_base_valor": 0.2, "veredicto": "se sostiene"},
                         {"id": "H2", "valor": 0.996, "umbral": {"operador": ">=", "valor": 0.9}, "linea_base_valor": 0.5, "veredicto": "se sostiene"}]}
    return resultado, pres, hip


def _corrida(d, resultado, pres, hip, estado="aprobado"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "informe.json").write_text(json.dumps({"estado": estado, "resultado_oficial": resultado, "preguntas_abiertas": 1}, ensure_ascii=False), encoding="utf-8")
    (d / "spec.json").write_text(json.dumps({"peticion": "Ventas por región del primer semestre de 2026", "preguntas": [{"id": "P1"}],
                                             "definiciones": {"venta_grande": "venta de más de 100.000 pesos"}}, ensure_ascii=False), encoding="utf-8")
    (d / "hipotesis_resultado.json").write_text(json.dumps(hip, ensure_ascii=False), encoding="utf-8")
    (d / "procedencia.json").write_text(json.dumps({"fuente": {"titulo": "Ventas sintéticas", "conjunto": "abcd-12ef"}, "consultado": "2026-11-06T08:00:00",
                                                    "filas": 160, "cita": "Ventas sintéticas del ejemplo (conjunto abcd-12ef), consultado el 06-11-2026"},
                                                   ensure_ascii=False), encoding="utf-8")
    (d / "presentacion.json").write_text(json.dumps(pres, ensure_ascii=False), encoding="utf-8")


def _muestras():
    """Un texto con datos personales y otro con una orden para una IA, tomados de las baterías del repositorio."""
    import csv
    raiz = AQUI.parent
    pii = orden = None
    try:
        with open(raiz / "baterias" / "privacidad" / "con_datos_personales.csv", newline="", encoding="utf-8") as fh:
            pii = next((v for fila in csv.DictReader(fh) for v in fila.values() if v and escanear_texto(v)), None)
        orden = next((x for x in (raiz / "baterias" / "inyeccion" / "maliciosos.txt").read_text(encoding="utf-8").splitlines()
                      if parece_instruccion(x) and len(x) < MAX_TEXTO), None)
    except OSError:
        pass
    if not pii or not orden:
        raise SystemExit("faltan las muestras de baterias/privacidad o baterias/inyeccion")
    return pii[:MAX_CELDA], orden


def autoprueba():
    import copy
    resultado, base, hip = _base()

    def mut(f, sobre=None):
        p = copy.deepcopy(sobre or base)
        f(p)
        return p

    def con_hipotesis(p):
        p["hallazgos"][1] = {"titulo": "Los pedidos del Norte pesan el {h1} de su región según la hipótesis sellada",
                             "evidencia": {"tipo": "hipotesis", "id": "H1"}, "nota": "El código la probó contra su umbral sellado."}
        p["cifras"].append({"id": "h1", "calculo": {"op": "hipotesis", "id": "H1", "campo": "valor", "como": "porcentaje"}})
    hip_base = hip
    hip_mala = dict(hip, estado="revisar")
    datos_nan = copy.deepcopy(resultado)
    datos_nan[2]["ventas"] = float("nan")
    datos_pii = copy.deepcopy(resultado)
    # Las muestras maliciosas se leen de las baterías (ahí viven los casos de prueba): el código no las trae escritas.
    muestra_pii, muestra_orden = _muestras()
    datos_pii[4]["region"] = muestra_pii
    # (nombre, presentación, resultado, hipótesis, estado, comprobación que debe fallar o None si debe aprobar)
    casos = [
        ("base", base, resultado, hip_base, "aprobado", None),
        ("base con hipótesis probada como porcentaje", mut(con_hipotesis), resultado, hip_base, "aprobado", None),
        ("base con un año de la petición y una cifra negativa",
         mut(lambda p: (p["hallazgos"][1].update(nota="En 2026 el Sur queda a {dif} del Norte."),
                        p["cifras"].append({"id": "dif", "calculo": {"op": "diferencia", "a": {"op": "valor", "columna": "ventas", "donde": {"region": "Sur"}},
                                                                     "b": {"op": "valor", "columna": "ventas", "donde": {"region": "Norte"}}},
                                            "formato": {"escala": "millones", "decimales": 0}}))), resultado, hip_base, "aprobado", None),
        ("base con citas selladas y cardinales en el método",
         mut(lambda p: (p["metodo_y_limites"].update(metodo="Se calculó dos veces, con dos implementaciones, sobre el conjunto abcd-12ef.",
                                                      limites=p["metodo_y_limites"]["limites"] + ["Hay riesgo de doble conteo en las ventas de más de 100.000 pesos."]))),
         resultado, hip_base, "aprobado", None),
        ("dígito escrito a mano", mut(lambda p: p["hallazgos"][1].update(nota="Es 3 veces lo del año pasado.")), resultado, hip_base, "aprobado", "los números los escribe"),
        ("marcadores pegados", mut(lambda p: p["hallazgos"][1].update(nota="Entre todas suman {n_regiones}{norte}.")), resultado, hip_base, "aprobado", "los números los escribe"),
        ("moneda junto a un marcador", mut(lambda p: p["hallazgos"][1].update(nota="El Norte vendió {n_regiones} USD por pedido.")),
         resultado, hip_base, "aprobado", "los números los escribe"),
        ("carácter numérico que no es dígito", mut(lambda p: p["hallazgos"][1].update(nota="Creció ❹ puntos frente al año pasado.")),
         resultado, hip_base, "aprobado", "los números los escribe"),
        ("cardinal en un título", mut(lambda p: p["hallazgos"][1].update(titulo="Catorce de las quince tiendas concentran el {top2} de las ventas del semestre")),
         resultado, hip_base, "aprobado", "los números los escribe"),
        ("id de hipótesis con forma de número", mut(lambda p: p["hallazgos"][1].update(nota="Según 90, el resto se reparte entre las otras regiones.")),
         resultado, dict(hip, hipotesis=hip["hipotesis"] + [{"id": "90", "valor": 1, "umbral": {"operador": ">", "valor": 0}, "veredicto": "se sostiene"}]),
         "aprobado", "los números los escribe"),
        ("redondeo que muestra 100 %", mut(lambda p: (p["cifras"].append({"id": "casi", "calculo": {"op": "hipotesis", "id": "H2", "campo": "valor", "como": "porcentaje"},
                                                                          "formato": {"decimales": 0}}),
                                                       p["hallazgos"][1].update(nota="La hipótesis H2 da {casi}.")))
         , resultado, hip_base, "aprobado", "cada cifra se calcula"),
        ("redondeo que muestra 0", mut(lambda p: (p["cifras"].append({"id": "occ", "calculo": {"op": "valor", "columna": "ventas", "donde": {"region": "Occidente"}},
                                                                     "formato": {"escala": "billones", "decimales": 0}}),
                                                  p["hallazgos"][1].update(nota="El Occidente vende {occ}.")))
         , resultado, hip_base, "aprobado", "cada cifra se calcula"),
        ("número con palabras", mut(lambda p: p["hallazgos"][1].update(nota="Es la mitad de lo del año pasado.")), resultado, hip_base, "aprobado", "los números los escribe"),
        ("porcentaje fuera de un marcador", mut(lambda p: p["hallazgos"][1].update(titulo="Las regiones Norte y Centro concentran el {norte} % de las ventas del semestre")),
         resultado, hip_base, "aprobado", "los números los escribe"),
        ("dígito disfrazado (superíndice)", mut(lambda p: p["hallazgos"][1].update(nota="Creció 10⁶ veces.")), resultado, hip_base, "aprobado", "los números los escribe"),
        ("marcador desconocido", mut(lambda p: p["hallazgos"][1].update(nota="Sube {inventada} frente al año pasado.")), resultado, hip_base, "aprobado", "los números los escribe"),
        ("cifra con texto escrito a mano", mut(lambda p: p["cifras"][0].update(texto="48 %")), resultado, hip_base, "aprobado", "forma de la ficha"),
        ("constante anidada (conteo primeros)", mut(lambda p: p["cifras"][4].update(calculo={"op": "porcentaje", "parte": {"op": "conteo", "primeros": 4},
                                                                                               "total": {"op": "conteo", "primeros": 5}})),
         resultado, hip_base, "aprobado", "cada cifra se calcula"),
        ("«como» fuera de una hipótesis", mut(lambda p: p["cifras"][2]["calculo"].update(como="porcentaje")), resultado, hip_base, "aprobado", "cada cifra se calcula"),
        ("NaN en los datos", base, datos_nan, hip_base, "aprobado", "cada cifra se calcula"),
        ("nota que no es texto", mut(lambda p: p["hallazgos"][0].update(nota=["9.999 millones"])), resultado, hip_base, "aprobado", "forma de la ficha"),
        ("JSON con la respuesta como texto", mut(lambda p: p.update(respuesta="El Norte gana")), resultado, hip_base, "aprobado", "forma de la ficha"),
        ("título de tema", mut(lambda p: p["hallazgos"][0].update(titulo="Ventas por región")), resultado, hip_base, "aprobado", "títulos que afirman"),
        ("título sin cifra", mut(lambda p: p["hallazgos"][0].update(titulo="El Norte es la región que más vende entre todas las del país")),
         resultado, hip_base, "aprobado", "títulos que afirman"),
        ("sin límites", mut(lambda p: p["metodo_y_limites"].update(limites=[])), resultado, hip_base, "aprobado", "método, incertidumbre"),
        ("pregunta abierta sin nombrar", mut(lambda p: p["metodo_y_limites"].update(limites=["Las devoluciones no se restan."])),
         resultado, hip_base, "aprobado", "método, incertidumbre"),
        ("resultado sin aprobar", base, resultado, hip_base, "revisar", "el resultado que se presenta"),
        ("tabla con columna inexistente", mut(lambda p: p["hallazgos"][0]["evidencia"].update(columnas=["region", "utilidad"])),
         resultado, hip_base, "aprobado", "hallazgos, cada uno"),
        ("hipótesis sin probar", mut(con_hipotesis), resultado, hip_mala, "aprobado", "hallazgos, cada uno"),
        ("seis hallazgos", mut(lambda p: p.update(hallazgos=[dict(h, titulo=h["titulo"] + f" (parte {k})") for k in "abc" for h in p["hallazgos"]])),
         resultado, hip_base, "aprobado", "hallazgos, cada uno"),
        ("texto con orden para una IA", mut(lambda p: p["scqa"].update(situacion=muestra_orden)),
         resultado, hip_base, "aprobado", "forma de instrucción"),
        ("carácter bidireccional", mut(lambda p: p["hallazgos"][0].update(nota="Las regiones ‮menores‬ son tres.")),
         resultado, hip_base, "aprobado", "invisibles"),
        ("dato personal en una celda de la tabla", base, datos_pii, hip_base, "aprobado", "datos personales"),
    ]
    raiz = Path(tempfile.mkdtemp(prefix="autoprueba-presentacion-"))
    fallas = []
    try:
        for i, (nombre, pres, res, h, estado, debe_fallar) in enumerate(casos):
            d = raiz / f"c{i}"
            _corrida(d, res, pres, h, estado)
            try:
                checks, _ = comprobar(d)
            except Exception as e:      # el verificador nunca debe caerse
                checks = [{"comprobacion": f"el verificador se cayó ({type(e).__name__})", "ok": False}]
            rotas = [x["comprobacion"] for x in checks if not x["ok"]]
            if debe_fallar is None:
                ok = not rotas
                print(f"{'✓' if ok else '✗'} bueno «{nombre}»: {'aprueba' if ok else rotas}")
            else:
                ok = any(debe_fallar in x for x in rotas) and not any("se cayó" in x for x in rotas)
                print(f"{'✓' if ok else '✗'} mutante «{nombre}»: {'atrapado' if ok else 'NO atrapado'} · falla {rotas}")
            if not ok:
                fallas.append(nombre)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    buenos = sum(1 for x in casos if x[5] is None)
    print("RESUMEN " + json.dumps({"autoprueba": "aprobada" if not fallas else "revisar", "buenos": buenos, "mutantes": len(casos) - buenos,
                                   "fallas": fallas}, ensure_ascii=False))
    return 0 if not fallas else 1


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    if argv[0] == "--autoprueba":
        return autoprueba()
    c = Path(argv[0]).resolve()
    try:
        checks, datos = comprobar(c)
    except Exception as e:                         # nunca se cae: un error es una comprobación fallida
        checks, datos = [{"comprobacion": "el verificador terminó sin errores", "ok": False, "detalle": f"{type(e).__name__}: {str(e)[:200]}"}], None
    ok = all(x["ok"] for x in checks)
    html_ruta = c / "presentacion.html"
    pagina = None
    if ok and datos is not None:
        try:
            pagina = renderizar(datos)
        except Exception as e:
            checks.append({"comprobacion": "las láminas se arman sin errores", "ok": False, "detalle": f"{type(e).__name__}: {str(e)[:200]}"})
            ok = False
    if ok and pagina is not None:
        html_ruta.write_text(pagina, encoding="utf-8")
    elif html_ruta.exists():
        html_ruta.unlink()                         # no queda una presentación vieja que parezca aprobada
    titulos = []
    if datos is not None:
        pres, esc = datos["pres"], datos["escritas"]
        titulos = [poner_cifras(pres["respuesta"]["titulo"], esc)] + [poner_cifras(h["titulo"], esc) for h in pres["hallazgos"]]
    out = {"estado": "aprobado" if ok else "revisar", "comprobaciones": checks, "titulos_en_orden": titulos,
           "html": html_ruta.name if ok and datos is not None else None}
    (c / "presentacion_verificacion.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for x in checks:
        print(f"{'✓' if x['ok'] else '✗'} {x['comprobacion']}: {x['detalle']}")
    print("RESUMEN " + json.dumps({"estado": out["estado"], "fallas": [x["comprobacion"] for x in checks if not x["ok"]]}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
