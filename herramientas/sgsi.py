#!/usr/bin/env python3
"""SGSI del pipeline, comprobado sin IA: la tríada C·I·D aplicada a ISO/IEC 27001:2022.

Uso:
  python herramientas/sgsi.py                 comprueba el SGSI (rápido, sin red y sin escribir nada)
  python herramientas/sgsi.py --escribir      además reescribe sgsi/INFORME-SGSI.md desde los datos
  python herramientas/sgsi.py --efectividad   además corre las pruebas de cada control (blindaje, baterías,
                                              corrida sintética y mutantes) y solo cuenta los controles que pasan
  python herramientas/sgsi.py --efectividad --en-linea   también las comprobaciones con red (aportes y OSV)
  python herramientas/sgsi.py --salida <archivo.json>    guarda el resultado completo
  python herramientas/sgsi.py --autoprueba    prueba al probador: 21 SGSI dañados a propósito deben fallar

Lee sgsi/activos.json, sgsi/controles.json, sgsi/riesgos.json y sgsi/soa.json, y comprueba:
  inventario    cada activo tiene propietario, custodio y valor de C, I y D (1 a 5) con su porqué, y su
                clasificación concuerda con su C (pública: C <= 2; interna: C = 3; restringida: C >= 4);
  restringidos  nada restringido está en el repositorio público: lo que debe quedar fuera está ignorado y sin versionar;
  secretos      ningún archivo versionado trae llaves o tokens;
  permisos      los flujos de GitHub piden solo lectura, no usan pull_request_target, no leen secretos propios,
                fijan cada acción a su commit y, si corren el banco de blindaje, lo hacen en macOS (sandbox-exec);
  controles     cada control apunta a evidencia que existe y a pruebas que existen;
  riesgos       impacto = valor del activo en la propiedad que se pierde; nivel = probabilidad × impacto;
                la regla de la tríada (curso NODO, clase 1):
                  C · sin reversa  una fuga no se deshace: solo un control PREVENTIVO baja el riesgo;
                  I · se corrige   lo que se detecta se corrige: hace falta un control DETECTIVO;
                  D · se restablece lo que se cae se recupera: hace falta un control CORRECTIVO;
                y todo activo con 4 o más en una propiedad tiene al menos un riesgo valorado sobre ella (6.1.2 c 1);
  soa           la Declaración de Aplicabilidad tiene los 93 controles del Anexo A, una sola vez cada uno; lo que
                aplica lo implementa al menos un control del repositorio y lo que no aplica dice por qué;
  corridas      etiqueta C·I·D de cada corrida publicada (sus salidas, sus sellos y si se puede reconstruir).
Sale con 1 si algo falla. Un riesgo por encima del criterio sin aceptación del dueño es un aviso: lo decide el dueño.
"""
import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SGSI = RAIZ / "sgsi"
INFORME = SGSI / "INFORME-SGSI.md"
PY = sys.executable

ANEXO_A = [f"A.5.{i}" for i in range(1, 38)] + [f"A.6.{i}" for i in range(1, 9)] + \
          [f"A.7.{i}" for i in range(1, 15)] + [f"A.8.{i}" for i in range(1, 35)]
TEMAS = {"A.5": "Organizacionales", "A.6": "Personas", "A.7": "Físicos", "A.8": "Tecnológicos"}
PROPIEDADES = {"C": "confidencialidad", "I": "integridad", "D": "disponibilidad"}
# La regla de la tríada: qué tipo de control hace falta y cuál puede bajar el impacto de cada propiedad
REDUCE_IMPACTO = {"C": "preventivo", "I": "detectivo", "D": "correctivo"}
TIPOS = ("preventivo", "detectivo", "correctivo")
CLASES = {"publica": (1, 2), "interna": (3, 3), "restringida": (4, 5)}
CLASE_TEXTO = {"publica": "pública", "interna": "interna", "restringida": "restringida"}
ABREV = {"preventivo": "prev.", "detectivo": "det.", "correctivo": "corr."}
TRATAMIENTOS = ("mitigar", "aceptar", "evitar", "transferir", "por decidir")

SECRETOS = {
    "token de GitHub": re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    "llave de un proveedor de IA": re.compile(r"\bsk-(ant-)?[A-Za-z0-9_-]{32,}"),
    "llave de AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "llave de Google": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "token de Slack": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "llave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
RUTA_LOCAL = re.compile(r"(/Users/|/home/)(?!runner/)[A-Za-z0-9._-]+/|[A-Z]:\\\\?Users\\\\?[A-Za-z0-9._-]+")


def git(*a):
    return subprocess.run(["git", *a], cwd=RAIZ, capture_output=True, text=True).stdout  # nosec B603 B607


def leer(nombre):
    return json.loads((SGSI / nombre).read_text(encoding="utf-8"))


def coincide(ruta, patron):
    return fnmatch.fnmatch(ruta, patron + "*" if patron.endswith("/") else patron)


def muestra(patron):
    p = patron.replace("**", "x").replace("*", "x")
    return p + "muestra.csv" if p.endswith("/") else p


class Resultado:
    def __init__(self):
        self.chequeos = {}

    def falla(self, chequeo, texto):
        self.chequeos.setdefault(chequeo, {"fallas": [], "avisos": []})["fallas"].append(texto)

    def aviso(self, chequeo, texto):
        self.chequeos.setdefault(chequeo, {"fallas": [], "avisos": []})["avisos"].append(texto)

    def ok(self, chequeo):
        self.chequeos.setdefault(chequeo, {"fallas": [], "avisos": []})

    def paso(self, chequeo):
        return not self.chequeos.get(chequeo, {}).get("fallas")


# ---------------------------------------------------------------- activos

def comprobar_inventario(activos, res, versionados):
    ids = set()
    for a in activos:
        i = a.get("id", "?")
        res.ok("inventario")
        if i in ids:
            res.falla("inventario", f"{i}: id repetido")
        ids.add(i)
        for campo in ("nombre", "tipo", "propietario", "custodio", "clasificacion", "donde"):
            if not str(a.get(campo, "")).strip():
                res.falla("inventario", f"{i}: falta «{campo}»")
        for p in PROPIEDADES:
            v = a.get(p) or {}
            if not isinstance(v.get("valor"), int) or not 1 <= v["valor"] <= 5:
                res.falla("inventario", f"{i}: {PROPIEDADES[p]} sin valor de 1 a 5")
            if len(str(v.get("por", ""))) < 20:
                res.falla("inventario", f"{i}: {PROPIEDADES[p]} sin su porqué")
        clase = a.get("clasificacion")
        c = (a.get("C") or {}).get("valor")
        if clase not in CLASES:
            res.falla("inventario", f"{i}: clasificación «{clase}» no es pública, interna ni restringida")
        elif isinstance(c, int) and not CLASES[clase][0] <= c <= CLASES[clase][1]:
            res.falla("inventario", f"{i}: clasificación «{clase}» no concuerda con C = {c}")
        # dónde vive: lo restringido nunca en el repositorio público
        res.ok("restringidos")
        donde, ubic = a.get("donde"), a.get("ubicacion") or []
        if donde == "repositorio":
            if clase == "restringida":
                res.falla("restringidos", f"{i}: es restringido y está declarado dentro del repositorio público")
            for pat in ubic:
                if not any(coincide(v, pat) for v in versionados):
                    res.falla("inventario", f"{i}: «{pat}» no corresponde a ningún archivo versionado")
        elif donde == "ignorado":
            for pat in ubic:
                dentro = [v for v in versionados if coincide(v, pat)]
                if dentro:
                    res.falla("restringidos", f"{i}: «{pat}» debe quedar fuera del repositorio y hay {len(dentro)} archivo(s) versionados, p. ej. {dentro[0]}")
                if subprocess.run(["git", "check-ignore", "-q", "--no-index", muestra(pat)], cwd=RAIZ).returncode != 0:  # nosec B603 B607
                    res.falla("restringidos", f"{i}: «{pat}» no está en .gitignore: un «git add .» lo publicaría")
        elif donde == "fuera":
            if ubic:
                res.falla("inventario", f"{i}: un activo fuera del repositorio no lleva rutas del repositorio")
            if len(str(a.get("descripcion_ubicacion", ""))) < 15:
                res.falla("inventario", f"{i}: activo fuera del repositorio sin decir dónde vive")
        else:
            res.falla("inventario", f"{i}: «donde» debe ser repositorio, ignorado o fuera")
    return {a["id"]: a for a in activos if "id" in a}


def comprobar_secretos(versionados, res):
    res.ok("secretos")
    rutas_locales = []
    for v in versionados:
        if v.startswith("baterias/seguridad/malos/"):  # muestras de código malo con secretos ficticios, a propósito
            continue
        p = RAIZ / v
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for nombre, rx in SECRETOS.items():
            if rx.search(t):
                res.falla("secretos", f"posible {nombre} en {v}")
        n = len(RUTA_LOCAL.findall(t))
        if n:
            rutas_locales.append((v, n))
    return rutas_locales


def comprobar_permisos(res):
    res.ok("permisos")
    flujos = sorted((RAIZ / ".github/workflows").glob("*.y*ml"))
    for f in flujos:
        t = f.read_text(encoding="utf-8")
        nombre = f.name
        if not re.search(r"^permissions:", t, re.M):
            res.falla("permisos", f"{nombre}: no declara permissions (el token tendría los permisos por defecto)")
        if re.search(r"^\s+[\w-]+:\s*write\b|^permissions:\s*write-all", t, re.M):
            res.falla("permisos", f"{nombre}: pide permiso de escritura")
        if "pull_request_target" in t:
            res.falla("permisos", f"{nombre}: usa pull_request_target (código de un fork con permisos del repositorio)")
        otros = sorted(set(re.findall(r"secrets\.([A-Za-z0-9_]+)", t)) - {"GITHUB_TOKEN"})
        if otros:
            res.falla("permisos", f"{nombre}: lee secretos propios {otros} (el filtro de aportes no usa llaves)")
        if re.search(r"blindaje\.py|validar_aporte\.py|sgsi\.py --efectividad", t) and not re.search(r"runs-on:\s*macos", t):
            res.falla("permisos", f"{nombre}: corre el banco de blindaje fuera de macOS, donde la caja de arena no existe (L42)")
        for u in re.findall(r"uses:\s*([^\s#]+)", t):
            if not re.search(r"@[0-9a-f]{40}$", u):
                res.falla("permisos", f"{nombre}: la acción {u} no está fijada a un commit")
    return [f.name for f in flujos]


# ---------------------------------------------------------------- controles

def pruebas_existentes():
    blind = set(re.findall(r'@prueba\("(B\d+)"', (RAIZ / "herramientas/blindaje.py").read_text(encoding="utf-8")))
    bat = set(re.findall(r'"bateria":\s*"(\w+)"', (RAIZ / "herramientas/baterias.py").read_text(encoding="utf-8")))
    return blind, bat


PRUEBAS_FIJAS = {"corrida-sintetica", "mutantes", "red:abierta_a_aportes", "red:vulnerabilidades"}


def comprobar_controles(controles, res, chequeos_propios):
    blind, bat = pruebas_existentes()
    usadas = set()
    ids = set()
    for c in controles:
        i = c.get("id", "?")
        res.ok("controles")
        if i in ids:
            res.falla("controles", f"{i}: id repetido")
        ids.add(i)
        if c.get("tipo") not in TIPOS:
            res.falla("controles", f"{i}: tipo «{c.get('tipo')}» no es preventivo, detectivo ni correctivo")
        if not c.get("protege") or set(c["protege"]) - set(PROPIEDADES):
            res.falla("controles", f"{i}: «protege» debe ser una lista con C, I o D")
        for a in c.get("anexo_a", []):
            if a not in ANEXO_A:
                res.falla("controles", f"{i}: {a} no es un control del Anexo A de ISO/IEC 27001:2022")
        if not c.get("anexo_a"):
            res.falla("controles", f"{i}: no dice qué control del Anexo A implementa")
        c["_evidencia_rota"] = []
        for e in c.get("evidencia", []):
            p = RAIZ / e.get("archivo", "")
            if not e.get("archivo") or not p.exists():
                c["_evidencia_rota"].append(f"no existe {e.get('archivo')}")
                continue
            if e.get("contiene"):
                t = p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else \
                    "\n".join(str(x.relative_to(p)) for x in sorted(p.rglob("*")))
                if not re.search(e["contiene"], t, re.M):
                    c["_evidencia_rota"].append(f"{e['archivo']} ya no contiene «{e['contiene']}»")
        if not c.get("evidencia"):
            c["_evidencia_rota"].append("sin evidencia")
        for e in c["_evidencia_rota"]:
            res.falla("controles", f"{i}: {e}")
        for t in c.get("pruebas", []):
            usadas.add(t)
            existe = (t in blind) or (t.startswith("bateria:") and t[8:] in bat) or t in PRUEBAS_FIJAS or \
                     (t.startswith("sgsi:") and t[5:] in chequeos_propios)
            if not existe:
                res.falla("controles", f"{i}: la prueba «{t}» no existe")
    huerfanas = sorted(blind - usadas) + sorted(f"bateria:{b}" for b in bat if f"bateria:{b}" not in usadas)
    for h in huerfanas:
        res.aviso("controles", f"la prueba {h} no protege ningún control declarado: agréguela a sgsi/controles.json")
    return {c["id"]: c for c in controles if "id" in c}


# ---------------------------------------------------------------- riesgos

def evaluar_riesgos(datos, activos, controles, res, efect=None):
    criterio = datos["criterio_aceptacion"]["valor"]
    out = []
    usados = set()
    for r in datos["riesgos"]:
        i = r.get("id", "?")
        res.ok("riesgos")
        prop = r.get("propiedad")
        if prop not in PROPIEDADES:
            res.falla("riesgos", f"{i}: «propiedad» debe ser C, I o D")
            continue
        acts = [activos[a] for a in r.get("activos", []) if a in activos]
        for a in r.get("activos", []):
            if a not in activos:
                res.falla("riesgos", f"{i}: el activo {a} no está en el inventario")
        if not acts:
            res.falla("riesgos", f"{i}: sin activos")
            continue
        impacto = max(a[prop]["valor"] for a in acts)
        p = (r.get("probabilidad") or {}).get("valor")
        if not isinstance(p, int) or not 1 <= p <= 5 or len(str(r["probabilidad"].get("por", ""))) < 20:
            res.falla("riesgos", f"{i}: probabilidad sin valor de 1 a 5 o sin su porqué")
            continue
        for campo in ("amenaza", "vulnerabilidad", "dueño"):
            if len(str(r.get(campo, ""))) < 3:
                res.falla("riesgos", f"{i}: falta «{campo}»")
        trat = r.get("tratamiento")
        if trat not in TRATAMIENTOS:
            res.falla("riesgos", f"{i}: tratamiento «{trat}» no es mitigar, aceptar, evitar, transferir ni «por decidir»")
        validos, no_reducen, invalidos = [], [], []
        for cid in r.get("controles", []):
            usados.add(cid)
            c = controles.get(cid)
            if not c:
                res.falla("riesgos", f"{i}: el control {cid} no existe")
                continue
            if prop not in c.get("protege", []):
                res.falla("riesgos", f"{i}: {cid} no protege la {PROPIEDADES[prop]}")
                continue
            if c["_evidencia_rota"] or (efect is not None and efect.get(cid, {}).get("estado") == "falla"):
                invalidos.append(cid)
                continue
            validos.append(c)
        tipos = {c["tipo"] for c in validos}
        res_p = (r.get("residual") or {}).get("probabilidad", p)
        res_i = (r.get("residual") or {}).get("impacto", impacto)
        if trat == "mitigar" and REDUCE_IMPACTO[prop] not in tipos:
            res.falla("riesgos", f"{i}: un riesgo de {PROPIEDADES[prop]} se mitiga con al menos un control "
                                 f"{REDUCE_IMPACTO[prop]} que funcione (regla de la tríada)")
        if res_p > p or res_i > impacto:
            res.falla("riesgos", f"{i}: el residual ({res_p}×{res_i}) no puede ser mayor que el inherente ({p}×{impacto})")
        if res_p < p and "preventivo" not in tipos:
            res.falla("riesgos", f"{i}: baja la probabilidad sin un control preventivo que funcione")
            res_p = p
        if res_i < impacto and REDUCE_IMPACTO[prop] not in tipos:
            res.falla("riesgos", f"{i}: baja el impacto de la {PROPIEDADES[prop]} sin un control {REDUCE_IMPACTO[prop]} que funcione")
            res_i = impacto
        if prop == "C":
            no_reducen = [c["id"] for c in validos if c["tipo"] != "preventivo"]
        if res_p < p or res_i < impacto:
            if len(str((r.get("residual") or {}).get("por", ""))) < 20:
                res.falla("riesgos", f"{i}: el residual baja sin decir por qué")
        nivel, residual = p * impacto, res_p * res_i
        estado = "dentro del criterio" if residual <= criterio else "fuera del criterio"
        acept = r.get("aceptacion")
        if trat == "por decidir":
            res.aviso("riesgos", f"{i}: tratamiento por decidir (dueño del riesgo): {r.get('plan', 'sin plan escrito')}")
            estado = "pendiente del dueño"
        elif residual > criterio:
            if acept and acept.get("por") and acept.get("fecha") and len(str(acept.get("motivo", ""))) >= 20:
                estado = f"aceptado por {acept['por']} ({acept['fecha']})"
            else:
                res.aviso("riesgos", f"{i}: residual {residual} por encima del criterio ({criterio}) y sin aceptación del "
                                     f"dueño (6.1.3 f): {r.get('plan', 'sin plan escrito')}")
                estado = "pendiente del dueño"
        out.append({"id": i, "propiedad": prop, "activos": r["activos"], "amenaza": r.get("amenaza"),
                    "probabilidad": p, "impacto": impacto, "nivel": nivel,
                    "residual_probabilidad": res_p, "residual_impacto": res_i, "residual": residual,
                    "controles": [c["id"] for c in validos if c["id"] not in no_reducen], "no_reducen": no_reducen,
                    "sin_validez": invalidos,
                    "tratamiento": trat, "estado": estado, "plan": r.get("plan")})
    # 6.1.2 c 1: lo que vale 4 o más en una propiedad tiene al menos un riesgo valorado sobre ella
    for a in activos.values():
        for prop in PROPIEDADES:
            if a[prop]["valor"] >= 4 and not any(x["propiedad"] == prop and a["id"] in x["activos"] for x in out):
                res.falla("riesgos", f"{a['id']} vale {a[prop]['valor']} en {PROPIEDADES[prop]} y no tiene ningún riesgo valorado sobre ella")
    for cid in sorted(set(controles) - usados):
        res.falla("riesgos", f"{cid} no trata ningún riesgo: todo control sale del tratamiento de un riesgo (6.1.3 b)")
    return out, criterio


# ---------------------------------------------------------------- SoA

def comprobar_soa(soa, controles, riesgos, res):
    res.ok("soa")
    filas = soa.get("controles", [])
    ids = [f.get("id") for f in filas]
    faltan = [a for a in ANEXO_A if a not in ids]
    sobran = [a for a in ids if a not in ANEXO_A]
    repetidos = sorted({a for a in ids if ids.count(a) > 1})
    if faltan:
        res.falla("soa", f"faltan {len(faltan)} controles del Anexo A: {faltan[:6]}")
    if sobran or repetidos:
        res.falla("soa", f"ids que no son del Anexo A {sobran[:4]} o repetidos {repetidos[:4]}")
    por_anexo = {}
    for c in controles.values():
        for a in c.get("anexo_a", []):
            por_anexo.setdefault(a, []).append(c["id"])
    trata = {}
    for r in riesgos:
        for cid in r["controles"] + r["no_reducen"]:
            trata.setdefault(cid, set()).add(r["id"])
    salida = []
    for f in filas:
        a = f.get("id")
        impl = sorted(set(por_anexo.get(a, [])))
        if not str(f.get("nombre", "")).strip():
            res.falla("soa", f"{a}: sin nombre")
        if f.get("aplica") is True:
            if not impl:
                res.falla("soa", f"{a}: dice que aplica y ningún control del repositorio lo implementa")
            rotos = [c for c in impl if controles[c]["_evidencia_rota"]]
            estado = "evidencia rota" if rotos else "implementado"
            if rotos:
                res.falla("soa", f"{a}: su evidencia está rota en {rotos}")
        elif f.get("aplica") is False:
            if impl:
                res.falla("soa", f"{a}: dice que no aplica pero lo implementan {impl}")
            if len(str(f.get("justificacion", ""))) < 30:
                res.falla("soa", f"{a}: no aplica y no dice por qué (6.1.3 d)")
            estado = "excluido"
        else:
            res.falla("soa", f"{a}: «aplica» debe ser true o false")
            estado = "?"
        props = sorted({p for c in impl for p in controles[c]["protege"]}, key="CID".index)
        riesgos_ = sorted({x for c in impl for x in trata.get(c, set())})
        salida.append({"id": a, "nombre": f.get("nombre"), "aplica": f.get("aplica"), "implementan": impl,
                       "propiedades": props, "riesgos": riesgos_, "estado": estado,
                       "justificacion": f.get("justificacion")})
    return salida


# ---------------------------------------------------------------- corridas: etiqueta C·I·D

def etiquetar_corridas(res):
    res.ok("corridas")
    out = []
    for c in sorted((RAIZ / "corridas").glob("*/informe.json")):
        d = c.parent
        nombre = d.name
        gob = json.loads((d / "gobernanza.json").read_text(encoding="utf-8")) if (d / "gobernanza.json").exists() else {}
        inf = json.loads(c.read_text(encoding="utf-8"))
        # C: ¿las salidas se pueden publicar? barrido de datos personales y k-anonimato
        if gob.get("estado") == "aprobado" and not gob.get("problemas"):
            et_c = ("publicable", "barrido de datos personales limpio" + (", k-anonimato cumplido"
                    if (gob.get("k_anonimato") or {}).get("aplica") else "; solo agregados, sin columnas de personas"))
        elif gob:
            et_c = ("no publicar", f"gobernanza {gob.get('estado')}: {str(gob.get('problemas'))[:80]}")
        else:
            et_c = ("sin valorar", "la corrida no tiene gobernanza.json")
        # I: ¿el criterio sigue sellado y el resultado aprobado? se recalculan las huellas hoy
        cambios = []
        sellados = json.loads((d / "sellos.json").read_text(encoding="utf-8")) if (d / "sellos.json").exists() else {}
        if (d / "sellos_hipotesis.json").exists():  # verificar_hipotesis.py sella hipotesis.json con {"sha256": ...}
            sellados["hipotesis.json"] = json.loads((d / "sellos_hipotesis.json").read_text(encoding="utf-8"))["sha256"]
        for rel, h in sellados.items():
            p = d / rel
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
                cambios.append(rel)
        if not (d / "sellos.json").exists():
            et_i = ("sin sellos", "no hay criterio sellado")
        elif cambios:
            et_i = ("alterada", f"{len(cambios)} archivo(s) sellados cambiaron: {cambios[:3]}")
            res.falla("corridas", f"{nombre}: {len(cambios)} archivo(s) sellados ya no coinciden con su huella: {cambios[:3]}")
        elif inf.get("estado") == "aprobado":
            et_i = ("íntegra", "huellas del criterio recalculadas al generar este informe y resultado aprobado sin IA")
        else:
            et_i = ("no aprobada", f"estado {inf.get('estado')}")
        # D: ¿se puede reconstruir si se pierde? contrato de datos con procedencia, o datos sintéticos con semilla
        spec = (d / "spec.json").read_text(encoding="utf-8") if (d / "spec.json").exists() else ""
        if list(d.glob("contrato_*.json")) or "ejemplo-secop" in spec or "secop" in nombre:
            et_d = ("reconstruible", "se vuelve a descargar con el contrato de datos (ingesta.py) y se compara con la procedencia")
        elif "ejemplo/datos" in spec:
            et_d = ("reconstruible", "datos sintéticos versionados y regenerables desde la semilla (generar_datos.py)")
        else:
            et_d = ("solo copia local", "no hay contrato ni semilla para rehacer los datos")
        out.append({"corrida": nombre, "C": et_c, "I": et_i, "D": et_d})
    return out


# ---------------------------------------------------------------- efectividad (9.1): las pruebas de cada control

def correr(*a):
    p = subprocess.run([PY, *a], cwd=RAIZ, capture_output=True, text=True)  # nosec B603
    return p.returncode, p.stdout + p.stderr


def medir_efectividad(controles, en_linea, res):
    resultados = {f"sgsi:{ch}": ("pasa" if res.paso(ch) else "falla") for ch in CHEQUEOS_PREVIOS}
    rc, out = correr("herramientas/blindaje.py")
    for m in re.finditer(r"^([✓✗·!]) (B\d+) ", out, re.M):
        resultados[m.group(2)] = {"✓": "pasa", "✗": "falla", "·": "no aplica aquí", "!": "falla"}[m.group(1)]
    if "RESUMEN " not in out:  # el banco no terminó: una prueba que no corre no falla, pero tampoco cuenta
        resultados["_diagnostico_blindaje"] = f"el banco no terminó (código {rc}): " + " | ".join(out.strip().splitlines()[-6:])[:600]
    rc, out = correr("herramientas/baterias.py")
    for m in re.finditer(r"^([✓✗]) (\w+): ", out, re.M):
        resultados[f"bateria:{m.group(2)}"] = "pasa" if m.group(1) == "✓" else "falla"
    tmp = Path(tempfile.mkdtemp(prefix="sgsi-")) / "corrida"
    try:
        shutil.copytree(RAIZ / "corridas/2026-11-06-ventas-semestre", tmp)
        rc, out = correr("herramientas/verificar.py", str(tmp))
        resultados["corrida-sintetica"] = "pasa" if rc == 0 else "falla"
        mutantes = sorted((RAIZ / "evidencia/sintetico/mutantes").glob("m*.py"))
        rc, out = correr("herramientas/verificar.py", str(tmp), "--impl", *[f"{m.stem}={m}" for m in mutantes])
        sin_fallas = set(re.findall(r"^(m\d+\w*): sin fallas", out, re.M))
        ok = sin_fallas == {"m00_referencia_sin_errores"}
        resultados["mutantes"] = "pasa" if ok else "falla"
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    if en_linea:
        for prueba, script in (("red:abierta_a_aportes", "abierta_a_aportes.py"), ("red:vulnerabilidades", "vulnerabilidades.py")):
            rc, out = correr(f"herramientas/{script}")
            resultados[prueba] = {0: "pasa", 1: "falla"}.get(rc, "sin medir")
            if rc != 0:
                fallidas = [l.strip() for l in out.splitlines() if l.strip().startswith("✗")]
                resultados[f"_diagnostico_{prueba}"] = f"{prueba}: " + " | ".join(fallidas or out.strip().splitlines()[-2:])[:300]
    efect = {}
    for cid, c in controles.items():
        estados = [resultados.get(t, "sin medir") for t in c.get("pruebas", [])]
        if not c.get("pruebas"):
            e = "sin prueba automática"
        elif "falla" in estados:
            e = "falla"
        elif "sin medir" in estados:  # una prueba que no corrió no cuenta, aunque las demás pasen (L43)
            e = "sin medir aquí"
        elif "pasa" in estados:
            e = "operando"
        else:
            e = "sin medir aquí"
        efect[cid] = {"estado": e, "pruebas": dict(zip(c.get("pruebas", []), estados))}
    return efect, resultados


# ---------------------------------------------------------------- informe

def tabla(cab, filas):
    esc = lambda x: str(x).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    return "\n".join(["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)] +
                     ["| " + " | ".join(esc(x) for x in f) + " |" for f in filas])


def informe(activos, controles, riesgos, criterio, soa, corridas, rutas_locales):
    n_ap = sum(1 for f in soa if f["aplica"])
    fuera_inh = [r["id"] for r in riesgos if r["nivel"] > criterio]
    fuera_res = [r["id"] for r in riesgos if r["residual"] > criterio]
    con_prueba = sum(1 for c in controles.values() if c.get("pruebas"))
    L = ["# SGSI del pipeline · informe generado", "",
         "> Lo escribe `herramientas/sgsi.py --escribir` desde `sgsi/*.json`: no se edita a mano. "
         "Cómo se lee y con qué método, en [`README.md`](README.md).", "",
         "## Resumen", "",
         f"- **{len(activos)} activos** valorados en confidencialidad, integridad y disponibilidad.",
         f"- **{len(riesgos)} riesgos:** {len(fuera_inh)} superan el criterio de aceptación (nivel > {criterio}) antes de los "
         f"controles; después, {len(fuera_res)}" + (f" ({', '.join(fuera_res)})." if fuera_res else "."),
         f"- **{len(controles)} controles** del repositorio; {con_prueba} tienen prueba automática.",
         f"- **Declaración de Aplicabilidad:** {n_ap} de los 93 controles del Anexo A aplican; {93 - n_ap} se excluyen con su justificación.",
         "", "## La tríada por activo", "",
         tabla(["Activo", "Nombre", "Clasificación", "C", "I", "D", "Propietario"],
               [[a["id"], a["nombre"], CLASE_TEXTO.get(a["clasificacion"], a["clasificacion"]), a["C"]["valor"], a["I"]["valor"], a["D"]["valor"], a["propietario"]]
                for a in activos.values()]),
         "", "## Mapa de calor: antes y después de los controles", "",
         "Filas: probabilidad (5 arriba). Columnas: impacto, que sale del valor del activo en la propiedad que se pierde. "
         f"En negrilla, las celdas por encima del criterio de aceptación ({criterio}).", ""]
    for titulo, cp, ci in (("Antes de los controles (inherente)", "probabilidad", "impacto"),
                           ("Después de los controles (residual)", "residual_probabilidad", "residual_impacto")):
        filas = []
        for p in range(5, 0, -1):
            fila = [f"**P{p}**"]
            for i in range(1, 6):
                ids = ", ".join(r["id"] for r in riesgos if r[cp] == p and r[ci] == i) or "·"
                fila.append(f"**{ids}**" if p * i > criterio else ids)
            filas.append(fila)
        L += [f"**{titulo}**", "", tabla(["", "I1", "I2", "I3", "I4", "I5"], filas), ""]
    L += [          "## Riesgos", "",
          tabla(["Riesgo", "Pierde", "Amenaza", "Inherente", "Controles (tipo)", "Residual", "Estado"],
                [[r["id"], PROPIEDADES[r["propiedad"]], r["amenaza"],
                  f"{r['probabilidad']}×{r['impacto']} = {r['nivel']}",
                  "; ".join(x for x in [", ".join(f"{c} ({ABREV[controles[c]['tipo']]})" for c in r["controles"]),
                                        (f"no reducen, porque la C no tiene reversa: {', '.join(r['no_reducen'])}"
                                         if r["no_reducen"] else "")] if x),
                  f"{r['residual_probabilidad']}×{r['residual_impacto']} = {r['residual']}", r["estado"]]
                 for r in riesgos]),
          "", "prev. = preventivo, det. = detectivo, corr. = correctivo.", ""]
    pend = [r for r in riesgos if r["estado"] == "pendiente del dueño"]
    if pend:
        L += ["**Pendiente del dueño (6.1.3 f):** " + "; ".join(f"{r['id']}: {r['plan']}" for r in pend), ""]
    L += ["## Declaración de Aplicabilidad (ISO/IEC 27001:2022, 6.1.3 d)", ""]
    for tema, nombre in TEMAS.items():
        filas = [f for f in soa if f["id"].startswith(tema + ".")]
        L += [f"### {tema} · {nombre} ({sum(1 for f in filas if f['aplica'])} de {len(filas)} aplican)", "",
              tabla(["Control", "Nombre", "¿Aplica?", "Cómo se aplica o por qué no", "C·I·D", "Riesgos"],
                    [[f["id"], f["nombre"], "Sí" if f["aplica"] else "No",
                      "; ".join(f"{c} {controles[c]['nombre']}" for c in f["implementan"]) if f["aplica"] else f["justificacion"],
                      "·".join(f["propiedades"]) or "—", ", ".join(f["riesgos"]) or "—"] for f in filas]), ""]
    L += ["## Controles del repositorio", "",
          tabla(["Control", "Nombre", "Tipo", "Protege", "Anexo A", "Prueba automática"],
                [[c["id"], c["nombre"], c["tipo"], "·".join(c["protege"]), ", ".join(c["anexo_a"]),
                  ", ".join(c.get("pruebas", [])) or "evidencia documental"] for c in controles.values()]),
          "", "## Etiqueta C·I·D de las corridas publicadas", "",
          tabla(["Corrida", "C · sus salidas", "I · su resultado", "D · si se pierde"],
                [[x["corrida"], f"{x['C'][0]}: {x['C'][1]}", f"{x['I'][0]}: {x['I'][1]}", f"{x['D'][0]}: {x['D'][1]}"]
                 for x in corridas]), "",
          f"Rutas locales del equipo del dueño en archivos versionados: {sum(n for _, n in rutas_locales)} línea(s) en "
          f"{len(rutas_locales)} archivo(s) (riesgo aceptado R07; la cifra no debe crecer).", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- principal

CHEQUEOS_PREVIOS = ("inventario", "restringidos", "secretos", "permisos")  # los que una prueba «sgsi:» puede citar
CHEQUEOS = ("inventario", "restringidos", "secretos", "permisos", "controles", "riesgos", "soa", "corridas", "informe")


def evaluar(datos, versionados, argv=()):
    """Corre todos los chequeos sobre los datos del SGSI (los cuatro JSON). Devuelve el resultado y lo calculado."""
    res = Resultado()
    activos = comprobar_inventario(datos["activos"]["activos"], res, versionados)
    rutas_locales = comprobar_secretos(versionados, res)
    comprobar_permisos(res)
    controles = comprobar_controles(datos["controles"]["controles"], res, CHEQUEOS_PREVIOS)
    datos_r = datos["riesgos"]
    efect, medidas = (None, None)
    if "--efectividad" in argv:
        efect, medidas = medir_efectividad(controles, "--en-linea" in argv, res)
        for cid, e in efect.items():
            if e["estado"] == "falla":
                res.falla("controles", f"{cid}: su prueba falla hoy: {[t for t, s in e['pruebas'].items() if s == 'falla']}")
    riesgos, criterio = evaluar_riesgos(datos_r, activos, controles, res, efect)
    tope = datos_r.get("rutas_locales_aceptadas")
    total_rutas = sum(n for _, n in rutas_locales)
    if tope is not None and total_rutas > tope:
        res.aviso("secretos", f"{total_rutas} líneas con rutas locales del equipo (aceptadas: {tope}); las nuevas: "
                              f"{[v for v, _ in rutas_locales][:4]}")
    soa = comprobar_soa(datos["soa"], controles, riesgos, res)
    corridas = etiquetar_corridas(res)
    return res, {"activos": activos, "controles": controles, "riesgos": riesgos, "criterio": criterio, "soa": soa,
                 "corridas": corridas, "rutas_locales": rutas_locales, "efect": efect, "medidas": medidas}


def cargar():
    return {n: leer(f"{n}.json") for n in ("activos", "controles", "riesgos", "soa")}


def versionables():
    # lo versionado y lo que se versionaría con el próximo commit (nuevo y no ignorado)
    return sorted({v for v in (git("ls-files") + git("ls-files", "--others", "--exclude-standard")).splitlines() if v.strip()})


def riesgo(d, rid):
    return next(r for r in d["riesgos"]["riesgos"] if r["id"] == rid)


def control(d, cid):
    return next(c for c in d["controles"]["controles"] if c["id"] == cid)


def fila(d, aid):
    return next(f for f in d["soa"]["controles"] if f["id"] == aid)


def activo(d, aid):
    return next(a for a in d["activos"]["activos"] if a["id"] == aid)


# Mutantes del SGSI: cada uno comete un error típico de un SGSI de papel; la herramienta debe atraparlos todos
MUTANTES = {
    "C baja con un control detectivo (sin reversa)":
        lambda d: riesgo(d, "R03").update(controles=["CT06"]),
    "I mitigado sin ningún control detectivo":
        lambda d: riesgo(d, "R09").update(controles=["CT05"]),
    "D baja el impacto con un control solo preventivo":
        lambda d: riesgo(d, "R24").update(controles=["CT13"]),
    "residual mayor que el inherente":
        lambda d: riesgo(d, "R22")["residual"].update(probabilidad=4),
    "un control que no protege la propiedad del riesgo":
        lambda d: riesgo(d, "R23")["controles"].append("CT23"),
    "un control que no existe":
        lambda d: riesgo(d, "R01")["controles"].append("CT99"),
    "un riesgo sobre un activo que no está en el inventario":
        lambda d: riesgo(d, "R01")["activos"].append("A99"),
    "probabilidad sin su porqué":
        lambda d: riesgo(d, "R10")["probabilidad"].update(por=""),
    "un activo grave en una propiedad sin ningún riesgo valorado (6.1.2 c 1)":
        lambda d: activo(d, "A03")["D"].update(valor=5),
    "clasificación que no concuerda con la C":
        lambda d: activo(d, "A01").update(clasificacion="publica"),
    "lo restringido declarado dentro del repositorio":
        lambda d: activo(d, "A13").update(donde="repositorio", ubicacion=["README.md"]),
    "un control que no trata ningún riesgo (6.1.3 b)":
        lambda d: [riesgo(d, r)["controles"].remove("CT38") for r in ("R27",)],
    "evidencia que ya no existe":
        lambda d: control(d, "CT08")["evidencia"].append({"archivo": "herramientas/no_existe.py"}),
    "evidencia que ya no dice lo que decía":
        lambda d: control(d, "CT13")["evidencia"].append({"archivo": "herramientas/caja.py", "contiene": "texto que no está"}),
    "una prueba del banco que no existe":
        lambda d: control(d, "CT13")["pruebas"].append("B98"),
    "un control del Anexo A inventado":
        lambda d: control(d, "CT01")["anexo_a"].append("A.8.35"),
    "falta un control en la SoA":
        lambda d: d["soa"]["controles"].pop(),
    "control repetido en la SoA":
        lambda d: d["soa"]["controles"].append(dict(d["soa"]["controles"][0])),
    "aplica y nadie lo implementa":
        lambda d: fila(d, "A.7.1").update(aplica=True),
    "no aplica pero el repositorio lo implementa":
        lambda d: fila(d, "A.8.12").update(aplica=False, justificacion="no hace falta prevenir fugas en este repositorio"),
    "excluido sin justificación":
        lambda d: fila(d, "A.6.1").update(justificacion=""),
}


def autoprueba():
    """Probar al probador: control positivo (los datos de hoy pasan) y cada mutante debe fallar."""
    versionados = versionables()
    base, _ = evaluar(cargar(), versionados)
    fallas_base = [f for ch in base.chequeos.values() for f in ch["fallas"]]
    print(f"{'✓' if not fallas_base else '✗'} control positivo: el SGSI de hoy pasa sin fallas" +
          (f" — {fallas_base[:2]}" if fallas_base else ""))
    escapan = []
    for nombre, mutar in MUTANTES.items():
        d = cargar()
        mutar(d)
        res, _ = evaluar(d, versionados)
        fallas = [f for ch in res.chequeos.values() for f in ch["fallas"]]
        print(f"{'✓' if fallas else '✗'} atrapa: {nombre}" + (f" — {fallas[0][:110]}" if fallas else " — NO LO ATRAPA"))
        if not fallas:
            escapan.append(nombre)
    print("RESUMEN " + json.dumps({"mutantes": len(MUTANTES), "atrapados": len(MUTANTES) - len(escapan),
                                   "escapan": escapan, "control_positivo": not fallas_base}, ensure_ascii=False))
    return 1 if escapan or fallas_base else 0


def main(argv):
    if "--autoprueba" in argv:
        return autoprueba()
    res, x = evaluar(cargar(), versionables(), argv)
    activos, controles, riesgos, criterio = x["activos"], x["controles"], x["riesgos"], x["criterio"]
    soa, corridas, rutas_locales, efect, medidas = x["soa"], x["corridas"], x["rutas_locales"], x["efect"], x["medidas"]
    res.ok("informe")
    if efect is not None:
        # el informe publicado sale de la comprobación estática: lo medido hoy (un control caído) no lo reescribe
        if "--escribir" in argv:
            _, s = evaluar(cargar(), versionables())
            INFORME.write_text(informe(s["activos"], s["controles"], s["riesgos"], s["criterio"], s["soa"], s["corridas"],
                                       s["rutas_locales"]), encoding="utf-8")
    elif "--escribir" in argv:
        INFORME.write_text(informe(activos, controles, riesgos, criterio, soa, corridas, rutas_locales), encoding="utf-8")
    elif not INFORME.exists() or INFORME.read_text(encoding="utf-8") != informe(activos, controles, riesgos, criterio, soa,
                                                                                   corridas, rutas_locales):
        res.aviso("informe", "sgsi/INFORME-SGSI.md no coincide con los datos: python herramientas/sgsi.py --escribir")

    nombres = {"inventario": f"inventario: {len(activos)} activos con C·I·D, propietario y custodio",
               "restringidos": "lo restringido queda fuera del repositorio público",
               "secretos": "ningún archivo versionado trae llaves ni tokens",
               "permisos": "los flujos de GitHub piden solo lectura, sin secretos propios y con acciones fijadas",
               "controles": f"{len(controles)} controles con evidencia y pruebas que existen",
               "riesgos": f"{len(riesgos)} riesgos valorados con la regla de la tríada (criterio {criterio})",
               "soa": f"Declaración de Aplicabilidad: {sum(1 for f in soa if f['aplica'])} de 93 aplican",
               "corridas": f"etiqueta C·I·D de {len(corridas)} corridas", "informe": "informe al día con los datos" if efect is None else "informe: se compara en la comprobación sin --efectividad"}
    for ch in CHEQUEOS:
        info = res.chequeos.get(ch, {"fallas": [], "avisos": []})
        print(f"{'✓' if not info['fallas'] else '✗'} {nombres[ch]}")
        for f in info["fallas"]:
            print(f"    ✗ {f}")
        for a in info["avisos"]:
            print(f"    · aviso: {a}")
    if efect is not None:
        cuenta = {}
        for e in efect.values():
            cuenta[e["estado"]] = cuenta.get(e["estado"], 0) + 1
        print("Efectividad de los controles (9.1): " + ", ".join(f"{v} {k}" for k, v in sorted(cuenta.items())))
        for clave, texto_ in sorted((medidas or {}).items()):
            if clave.startswith("_diagnostico"):
                print(f"    {texto_}")
        for estado in ("falla", "sin medir aquí"):
            ids = [f"{k} ({', '.join(t for t, s in v['pruebas'].items() if s != 'pasa')})" for k, v in efect.items() if v["estado"] == estado]
            if ids:
                print(f"    {estado}: {'; '.join(ids)}")
    fallas = [f for ch in res.chequeos.values() for f in ch["fallas"]]
    avisos = [a for ch in res.chequeos.values() for a in ch["avisos"]]
    resumen = {"fallas": len(fallas), "avisos": len(avisos),
               "riesgos_fuera_del_criterio": [r["id"] for r in riesgos if r["residual"] > criterio],
               "soa_aplican": sum(1 for f in soa if f["aplica"])}
    if efect is not None:
        resumen["efectividad"] = {k: v["estado"] for k, v in efect.items()}
    if "--salida" in argv:
        Path(argv[argv.index("--salida") + 1]).write_text(json.dumps(
            {"resumen": resumen, "chequeos": res.chequeos, "riesgos": riesgos, "efectividad": efect,
             "pruebas_medidas": medidas, "corridas": corridas}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("RESUMEN " + json.dumps({k: v for k, v in resumen.items() if k != "efectividad"}, ensure_ascii=False))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
