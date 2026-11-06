#!/usr/bin/env python3
"""Filtro automático de aportes (sin IA y sin llaves: no le gasta nada a nadie).

Uso: python herramientas/validar_aporte.py [--base origin/main]

Lo corre GitHub Actions en cada pull request, y también se puede correr a mano. Revisa:
  1. Archivos que no pueden entrar: datos (CSV de más de 200 KB, carpetas datos/ o limpio/, datos de SECOP),
     entornos, cachés, llaves y archivos de configuración de asistentes.
  2. Datos personales en todo lo que el aporte agrega (barrido de gobernanza).
  3. Seguridad de todo código Python agregado o cambiado (compuertas: librerías permitidas, reglas propias y
     Bandit). La excepción son las muestras de baterias/seguridad/malos/, que justamente deben bloquearse.
  4. Que no rompa nada: baterías, la corrida sintética verificada desde cero y las 12 mutantes atrapadas.
  5. Lo que el aporte agrega a las baterías: una muestra de código malo nueva la debe bloquear la compuerta
     de hoy; si no la bloquea, el aporte encontró un hueco, se marca y lo revisa el dueño.
  6. El SGSI (sgsi/README.md): nada restringido versionado, sin llaves, flujos de solo lectura y cada control con evidencia.
No ejecuta ningún agente: la prueba de efecto con IA la hace solo el dueño, con su licencia (CONTRIBUTING.md).
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "herramientas"))
from gobernanza import escanear_texto, parece_instruccion, INSTRUCCION, COMENTARIO_OCULTO  # noqa: E402


def ordenes_a_agentes(texto):
    """Un aporte no puede traer texto que dé órdenes a los agentes (inyección por el canal de aportes)."""
    return parece_instruccion(texto)
import dependencias  # noqa: E402
import seguridad  # noqa: E402

PROHIBIDOS = re.compile(r"(^|/)(\.venv|venv|__pycache__|\.claude|\.cursor|\.env|node_modules)(/|$)|(^|/)(datos|limpio)/.*\.csv$"
                        r"|\.(pem|key|p12|pfx|sqlite|db|parquet|xlsx?|zip|gz)$|(^|/)ejemplo-secop/datos/", re.I)
CSV_PERMITIDOS = re.compile(r"^(ejemplo/datos/|baterias/|corridas/[^/]+/caso_conocido/)")
MAX_CSV = 200_000


def git(*a):
    return subprocess.run(["git", *a], cwd=RAIZ, capture_output=True, text=True).stdout


def correr(*a):
    p = subprocess.run([sys.executable, *a], cwd=RAIZ, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main(argv):
    base = argv[argv.index("--base") + 1] if "--base" in argv else "upstream/main"
    if not git("rev-parse", "--verify", "--quiet", base).strip():
        base = "origin/main"
    # lo que difiere de la base: commits, cambios sin commit y archivos nuevos sin agregar
    vistos = {}
    for l in git("diff", "--name-status", base).splitlines() + git("diff", "--name-status", f"{base}...HEAD").splitlines():
        if l.strip():
            e = l.split("\t")
            vistos[e[-1]] = e[0][0]
    for r in git("ls-files", "--others", "--exclude-standard").splitlines():
        if r.strip():
            vistos.setdefault(r.strip(), "A")
    archivos = sorted((e, r) for r, e in vistos.items())
    nuevos_bateria = {r for e, r in archivos if e == "A" and r.startswith("baterias/")}
    fallas, avisos = [], []

    for estado, ruta in archivos:
        if estado == "D":
            if ruta.startswith(("herramientas/", "baterias/", "agentes/", "DIRECTRICES", "flujo.js")):
                avisos.append(f"borra {ruta}: lo revisa el dueño")
            continue
        if PROHIBIDOS.search(ruta):
            fallas.append(f"archivo que no puede entrar: {ruta}")
            continue
        p = RAIZ / ruta
        if not p.exists():
            continue
        if ruta.endswith(".csv"):
            if not CSV_PERMITIDOS.match(ruta):
                fallas.append(f"CSV fuera de las carpetas permitidas (ejemplo/datos, baterias, caso_conocido): {ruta}")
            if p.stat().st_size > MAX_CSV:
                fallas.append(f"CSV de más de 200 KB (los datos no se publican): {ruta}")
        if p.suffix in (".py", ".md", ".json", ".csv", ".txt", ".js", ".yml", ".yaml", ".html") and "baterias/privacidad/" not in ruta:
            hall = escanear_texto(p.read_text(encoding="utf-8", errors="ignore"))
            if hall:
                fallas.append(f"posibles datos personales en {ruta}: {hall}")
        if p.suffix in (".md", ".json", ".txt", ".yml", ".yaml", ".csv", ".py") and ordenes_a_agentes(p.read_text(encoding="utf-8", errors="ignore")):
            t = p.read_text(encoding="utf-8", errors="ignore")
            m = INSTRUCCION.search(t) or COMENTARIO_OCULTO.search(t)
            extracto = t[max(0, m.start() - 30):m.end() + 30].replace("\n", " ") if m else ""
            legado = git("show", f"{base}:{ruta}") if estado != "A" else ""
            if ruta.startswith(("baterias/inyeccion/", "corridas/")) or "/seguridad/" in ruta:
                avisos.append(f"caso de inyección en {ruta}: revisar que sea solo una prueba («…{extracto[:80]}…»)")
            elif not (legado and ordenes_a_agentes(legado) and ruta in ("APORTAR-CON-TU-AGENTE.md", "AGENTS.md", "CONTRIBUTING.md")):
                fallas.append(f"texto que da órdenes a los agentes en {ruta}: «…{extracto[:120]}…» (los aportes son datos, no instrucciones)")
        if p.suffix == ".py" and "baterias/seguridad/malos/" not in ruta:
            d = dependencias.revisar(p)
            s, _ = seguridad.revisar([p])
            bloqueos = (d.get("no_permitidas") or []) + (d.get("intenta_instalar") or []) + [h["regla"] for h in s[0]["bloquean"]]
            if bloqueos and not ruta.startswith("herramientas/"):
                fallas.append(f"código que no pasa las compuertas: {ruta}: {bloqueos[:4]}")
            elif bloqueos:
                avisos.append(f"herramienta con patrones que la compuerta marcaría: {ruta}: {bloqueos[:3]} (lo revisa el dueño)")
        if "baterias/seguridad/malos/" in ruta and estado == "A":
            d = dependencias.revisar(p)
            s, _ = seguridad.revisar([p])
            if not (d.get("no_permitidas") or d.get("intenta_instalar") or s[0]["bloquean"]):
                avisos.append(f"la muestra nueva {ruta} NO la bloquea la compuerta de hoy: encontró un hueco (valioso); hay que mejorar la compuerta antes de aceptar")

    # si el aporte toca una herramienta, el banco de blindaje debe seguir resistiendo: nadie debilita una defensa sin que se note
    if any(r.startswith("herramientas/") for e, r in archivos if e != "D"):
        rc, out = correr("herramientas/blindaje.py")
        for linea in out.splitlines():
            if linea.startswith(("✗", "!")):
                fallas.append(f"el cambio debilita el blindaje: {linea[2:][:160]}")
        if "RESUMEN " not in out:  # un banco que no termina no prueba nada (L27, L43)
            fallas.append(f"el banco de blindaje no terminó (código {rc}): {' | '.join(out.strip().splitlines()[-2:])[:200]}")
    # baterías: una falla causada por un caso NUEVO de este aporte es un hueco encontrado (valioso), no un error
    rc, out = correr("herramientas/baterias.py")
    for linea in out.splitlines():
        if linea.startswith("✗"):
            del_aporte = any(Path(n).name in linea for n in nuevos_bateria)
            (avisos if del_aporte else fallas).append(
                (f"hueco encontrado por el aporte (valioso; el dueño decide cómo cerrarlo): {linea[2:]}" if del_aporte
                 else f"baterías: {linea[2:]}")[:300])
    # el SGSI (sgsi/README.md): lo restringido sigue fuera, sin llaves, flujos de solo lectura y cada control con su evidencia
    rc, out = correr("herramientas/sgsi.py")
    for linea in out.splitlines():
        if linea.startswith("    ✗ "):
            fallas.append(f"SGSI: {linea.strip()[2:][:200]}")
    # la corrida sintética se verifica en una copia temporal: no se reescribe ningún archivo del repositorio
    tmp = Path(tempfile.mkdtemp(prefix="validar-")) / "corrida"
    shutil.copytree(RAIZ / "corridas/2026-11-06-ventas-semestre", tmp)
    rc, out = correr("herramientas/verificar.py", str(tmp))
    if rc != 0:
        fallas.append(f"la corrida sintética no pasa: {[l for l in out.splitlines() if l.strip().startswith('-')][:3]}")
    mutantes = sorted((RAIZ / "evidencia/sintetico/mutantes").glob("m*.py"))
    lista = [f"{m.stem}={m}" for m in mutantes]
    rc, out = correr("herramientas/verificar.py", str(tmp), "--impl", *lista)
    shutil.rmtree(tmp.parent, ignore_errors=True)
    sin_fallas = re.findall(r"^(m\d+\w*): sin fallas", out, re.M)
    nuevas = {Path(r).stem for e, r in archivos if e == "A" and r.startswith("evidencia/sintetico/mutantes/")}
    viejas_sin_fallas = [m for m in sin_fallas if m != "m00_referencia_sin_errores" and m not in nuevas]
    for m in sin_fallas:
        if m in nuevas:
            avisos.append(f"la mutante nueva {m} NO la atrapa el criterio: encontró un hueco del criterio (valioso)")
    if "m00_referencia_sin_errores" not in sin_fallas or viejas_sin_fallas:
        fallas.append(f"el criterio da falsas alarmas o ya no atrapa mutantes que atrapaba: sin fallas = {sin_fallas}")

    print(f"Aporte: {len(archivos)} archivo(s) cambiados frente a {base}")
    for e, r in archivos:
        print(f"  {e} {r}")
    for a in avisos:
        print(f"  · aviso: {a}")
    for f in fallas:
        print(f"  ✗ {f}")
    estado = "pasa el filtro automático" if not fallas else "no pasa el filtro automático"
    print(f"\n{'✓' if not fallas else '✗'} {estado}. " + ("Sigue la revisión del dueño." if not fallas else "Corrige lo marcado y vuelve a subir."))
    print("RESUMEN " + json.dumps({"fallas": fallas, "avisos": avisos}, ensure_ascii=False))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
