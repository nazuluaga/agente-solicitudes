#!/usr/bin/env python3
"""Baterías: lo que falló una vez se vuelve prueba para siempre (sin IA).

Uso:
  python baterias.py                         corre todas las baterías
  python baterias.py --agregar-malo nombre archivo.py   guarda un hallazgo confirmado como código que debe bloquearse
  python baterias.py --leccion "texto" --origen "..." --prueba "..."   agrega una lección

1. Seguridad: todo lo de baterias/seguridad/malos debe quedar bloqueado y todo lo de buenos debe pasar
   (así también se prueba al probador: un falso positivo es una falla de la compuerta).
2. Privacidad: el perfil de un CSV con datos personales no puede mostrar ninguno de los valores de
   no_deben_salir.txt, y el barrido de gobernanza tiene que encontrarlos.
3. Lecciones: cada lección apunta a una prueba; si apunta a un archivo de la batería, el archivo existe.
4. Cruces: el perfil explica por qué no cruza cada valor (baterias/cruces/esperado.json) y no explica un ausente.
5. Gráfico: las figuras de baterias/grafico/buenos pasan las comprobaciones de forma y color, y cada figura de
   malos falla justo la comprobación que ataca (ni otra, ni ninguna).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
BAT = RAIZ / "baterias"
sys.path.insert(0, str(AQUI))
import dependencias  # noqa: E402
import seguridad  # noqa: E402
from gobernanza import barrer_tabla  # noqa: E402


def bloquea(ruta):
    d = dependencias.revisar(ruta)
    s, _ = seguridad.revisar([ruta])
    return bool(d.get("no_permitidas") or d.get("intenta_instalar") or s[0]["bloquean"])


def bateria_seguridad():
    fallas = []
    malos = sorted((BAT / "seguridad" / "malos").glob("*.py"))
    buenos = sorted((BAT / "seguridad" / "buenos").glob("*.py"))
    for p in malos:
        if not bloquea(p):
            fallas.append(f"no se bloqueó {p.name}")
    for p in buenos:
        if bloquea(p):
            fallas.append(f"falso positivo: se bloqueó {p.name}")
    return {"bateria": "seguridad", "casos": len(malos) + len(buenos), "fallas": fallas}


def bateria_privacidad():
    fallas = []
    csv_ = BAT / "privacidad" / "con_datos_personales.csv"
    secretos = [s for s in (BAT / "privacidad" / "no_deben_salir.txt").read_text(encoding="utf-8").splitlines() if s]
    p = subprocess.run([sys.executable, str(AQUI / "perfilar.py"), f"t={csv_}"], capture_output=True, text=True)  # nosec B603
    for s in secretos:
        if s in p.stdout:
            fallas.append(f"el perfil muestra un dato personal: {s[:3]}…")
    from gobernanza import escanear_texto
    for t in (BAT / "privacidad" / "no_son_personales.txt").read_text(encoding="utf-8").splitlines():
        if t and escanear_texto(t):
            fallas.append(f"falso positivo: «{t}» se marcó como dato personal {escanear_texto(t)}")
    barrido = barrer_tabla(csv_)
    detectadas = {c for c, i in barrido["columnas"].items() if i.get("hallazgos") or i.get("clase_por_nombre") == "personal"}
    for c in ("proveedor_adjudicado", "documento_proveedor", "objeto_del_contrato"):
        if c not in detectadas:
            fallas.append(f"el barrido no detectó {c}")
    from gobernanza import clasificar_columna
    cols = json.loads((BAT / "privacidad" / "columnas_secop.json").read_text(encoding="utf-8"))
    n_cols = 0
    for grupo, aceptadas in (("personal", {"personal"}), ("cuasi_o_personal", {"personal", "cuasi"}),
                             ("texto_libre", {"texto_libre"}), ("sin_marca", {None})):
        for c in cols[grupo]:
            n_cols += 1
            if clasificar_columna(c) not in aceptadas:
                fallas.append(f"columna de SECOP mal clasificada: {c} → {clasificar_columna(c)} (se esperaba {grupo})")
    return {"bateria": "privacidad", "casos": len(secretos) + 3 + 6 + n_cols, "fallas": fallas}


def bateria_failfast():
    """Un CSV mal formado detiene la lectura: nunca se lee a medias en silencio (FAILFAST)."""
    from reglas_base import leer_csv
    fallas, casos = [], sorted((BAT / "failfast").glob("*.csv"))
    for p in casos:
        try:
            leer_csv(p)
            fallas.append(f"{p.name} se leyó sin error")
        except Exception:
            pass
    return {"bateria": "failfast", "casos": len(casos), "fallas": fallas}


def bateria_inyeccion():
    """Instrucciones disfrazadas: los textos maliciosos deben detectarse y los legítimos no (sin falsas alarmas)."""
    from gobernanza import parece_instruccion
    malos = [l for l in (BAT / "inyeccion" / "maliciosos.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    buenos = [l for l in (BAT / "inyeccion" / "legitimos.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    fallas = [f"no detecta: «{m[:60]}»" for m in malos if not parece_instruccion(m)]
    fallas += [f"falsa alarma: «{b[:60]}»" for b in buenos if parece_instruccion(b)]
    return {"bateria": "inyeccion", "casos": len(malos) + len(buenos), "fallas": fallas}


def bateria_cruces():
    """Por qué no cruza un valor entre tablas: espacios internos o invisibles; tildes, puntuación o ceros a la izquierda."""
    from perfilar import perfilar
    d = BAT / "cruces"
    esperado = json.loads((d / "esperado.json").read_text(encoding="utf-8"))
    p = perfilar({"origen": str(d / "origen.csv"), "destino": str(d / "destino.csv")})
    fallas, casos = [], 0
    for col, claves in esperado.items():
        if col.startswith("_"):
            continue
        x = next((c for c in p["cruces"] if c["desde"] == "origen" and c["columna"] == col), None)
        if x is None:
            fallas.append(f"{col}: el perfil no reporta el cruce")
            continue
        obtenido = {**x, **x.get("de_los_que_no_cruzan", {})}
        for k, v in claves.items():
            casos += 1
            if obtenido.get(k) != v:
                fallas.append(f"{col}.{k}: {obtenido.get(k)} (se esperaba {v})")
    return {"bateria": "cruces", "casos": casos, "fallas": fallas}


def bateria_grafico():
    """Forma y color del gráfico, sobre el JSON de la figura (sin caja de arena): los buenos pasan todo y cada malo
    falla solo la comprobación que ataca. Un falso positivo también es una falla (L32)."""
    from verificar_grafico import comprobar_forma_y_color
    fallas, nombres, atacadas = [], set(), set()
    buenos = sorted((BAT / "grafico" / "buenos").glob("*.json"))
    malos = sorted((BAT / "grafico" / "malos").glob("*.json"))
    for p in buenos:
        res = comprobar_forma_y_color(json.loads(p.read_text(encoding="utf-8"))["figura"])
        nombres |= {c["comprobacion"] for c in res}
        fallan = [c["comprobacion"] for c in res if not c["ok"]]
        if fallan:
            fallas.append(f"falso positivo en {p.name}: {fallan}")
    for p in malos:
        caso = json.loads(p.read_text(encoding="utf-8"))
        res = comprobar_forma_y_color(caso["figura"])
        nombres |= {c["comprobacion"] for c in res}
        fallan = [c["comprobacion"] for c in res if not c["ok"]]
        objetivo = caso.get("debe_fallar")
        atacadas.add(objetivo)
        if objetivo not in {c["comprobacion"] for c in res}:
            fallas.append(f"{p.name}: no existe la comprobación «{objetivo}»")
        elif fallan != [objetivo]:
            fallas.append(f"{p.name}: falla {fallan or 'ninguna'}; se esperaba solo «{objetivo}»")
    fallas += [f"sin caso malo para «{n}»" for n in sorted(nombres - atacadas)]
    return {"bateria": "grafico", "casos": len(buenos) + len(malos), "fallas": fallas}


def bateria_lecciones():
    d = json.loads((BAT / "lecciones.json").read_text(encoding="utf-8"))
    fallas = []
    for l in d["lecciones"]:
        prueba = l.get("prueba", "")
        if not prueba:
            fallas.append(f"{l['id']} no tiene prueba")
        for parte in prueba.split():
            if parte.startswith("bateria:"):
                ruta = parte.split(":", 1)[1]
                if not ((BAT / ruta).exists() or (RAIZ / ruta).exists()):
                    fallas.append(f"{l['id']}: no existe {parte}")
    return {"bateria": "lecciones", "casos": len(d["lecciones"]), "fallas": fallas}


def main(argv):
    if "--agregar-malo" in argv:
        i = argv.index("--agregar-malo")
        nombre, origen = argv[i + 1], Path(argv[i + 2])
        destino = BAT / "seguridad" / "malos" / f"{nombre}.py"
        shutil.copy(origen, destino)
        print(f"Agregado {destino.name}. {'Se bloquea hoy.' if bloquea(destino) else 'HOY NO SE BLOQUEA: hay que mejorar la compuerta.'}")
        return 0
    if "--leccion" in argv:
        d = json.loads((BAT / "lecciones.json").read_text(encoding="utf-8"))
        g = lambda k: argv[argv.index(k) + 1] if k in argv else ""
        ident = g("--id") or f"L{len(d['lecciones']) + 1:02d}"   # en un aporte: --id L-<usuario>-<tema>; el dueño renumera al aceptar
        d["lecciones"].append({"id": ident, "leccion": g("--leccion"), "origen": g("--origen"), "prueba": g("--prueba")})
        (BAT / "lecciones.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Lección {d['lecciones'][-1]['id']} agregada.")
        return 0
    res = [bateria_seguridad(), bateria_privacidad(), bateria_failfast(), bateria_inyeccion(), bateria_cruces(), bateria_grafico(),
           bateria_lecciones()]
    for r in res:
        print(f"{'✓' if not r['fallas'] else '✗'} {r['bateria']}: {r['casos']} casos" + ("" if not r["fallas"] else " · " + "; ".join(r["fallas"])))
    malos = sum(len(r["fallas"]) for r in res)
    print("RESUMEN " + json.dumps({"baterias": len(res), "fallas": malos}, ensure_ascii=False))
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
