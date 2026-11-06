# Pipeline de datos con IA: la IA propone, una prueba sin IA comprueba

Un análisis de datos hecho con IA, de la pregunta al informe, en las cinco etapas del ciclo del dato. En cada etapa la IA hace el trabajo y una prueba que no es IA lo comprueba. Quien pide el análisis no lee código: lee un informe de una página con la cifra, lo que se entendió, los supuestos, las preguntas abiertas y qué pasó cada prueba.

Material aplicado del curso **«Big Data con IA»** (NODO · Universidad EAFIT, noviembre de 2026), con datos abiertos de Colombia (SECOP II).

## Conectar la IA

Para aportar con la IA que ya usas (ChatGPT, Gemini, Claude, Copilot u otra), cópiale este texto:

```text
Lee https://raw.githubusercontent.com/CristianBTA/agente-solicitudes/main/APORTAR-CON-TU-AGENTE.md, sigue sus «Instrucciones para el agente» y empieza mi aporte al repositorio CristianBTA/agente-solicitudes.
```

- **La IA te pregunta tu idea y arma el aporte.** Si trabaja con archivos y terminal (Claude Code, Codex, Copilot en VS Code, Cursor), deja listo el *pull request*. Si es un chat, te entrega el texto para el formulario [«Proponer un aporte»](https://github.com/CristianBTA/agente-solicitudes/issues/new?template=aporte.yml).
- **No gasta tu cuota más allá de esa conversación:** el filtro del repositorio no usa IA, y la prueba con IA la paga el dueño.
- Si tu IA no puede abrir enlaces, pégale el archivo [`APORTAR-CON-TU-AGENTE.md`](APORTAR-CON-TU-AGENTE.md) completo.

| Etapa | La IA… | La prueba sin IA |
|---|---|---|
| **Ingesta** | escribe el lector: un contrato de datos con fuente, columnas, tipos, llave, dominios y rangos | conteo contra la fuente, llave única y sin nulos, tipos, rangos, dominios, minimización, correr dos veces da el mismo archivo, procedencia con fecha y huella |
| **Procesamiento** | limpia y transforma: especificación, plan de limpieza, reglas, caso con respuesta conocida y dos implementaciones independientes | capa limpia con las mismas filas y marcas de calidad, calidad antes y después con umbrales, criterio sellado antes del código, reglas sobre el dato crudo, caso conocido, A = B, conciliación, repetibilidad, compuertas y caja de arena |
| **Análisis** | propone hipótesis | registro y sello previos, consulta independiente de otro agente, umbral y línea base |
| **Visualización** | genera el gráfico y propone la presentación (solo textos y cifras declaradas) | cuenta de control, eje desde cero, título con período, unidades, fuente y fecha, color con contraste y apto para daltonismo, un solo eje, sin datos personales; en la presentación: respuesta primero, títulos que afirman y cada cifra calculada y escrita por el código |
| **Gobernanza** | halla datos personales con nombres, tipos y conteos, nunca filas | barrido determinista de datos y salidas, k-anonimato, comparación con la IA, revisión ciega de seguridad y baterías |

- **Los subagentes y sus parámetros:** [`agentes/`](agentes/README.md). Doce fichas independientes de la herramienta (rol, qué puede leer y qué no, qué entrega, reglas, lo que nunca hace y la prueba sin IA que lo comprueba), las reglas comunes y la matriz de quién puede ver qué.
- **Cómo validar el trabajo y qué exige cada práctica:** [`DIRECTRICES.md`](DIRECTRICES.md), con la guía «Validar este repositorio en 15 minutos».
- **La seguridad como sistema (SGSI):** [`sgsi/`](sgsi/README.md). Inventario con su valor en confidencialidad, integridad y disponibilidad, 27 riesgos, la Declaración de Aplicabilidad de los 93 controles de ISO/IEC 27001:2022 y la regla de la tríada (la confidencialidad no tiene reversa, la integridad se corrige, la disponibilidad se restablece), comprobados sin IA por `herramientas/sgsi.py`. Las vulnerabilidades se reportan en privado: [`SECURITY.md`](SECURITY.md).
- **Qué se midió:** [`evidencia/README.md`](evidencia/README.md). Generadores de un solo disparo frente al sistema verificado, en datos sintéticos y en SECOP II, con la prueba del criterio por mutantes (12 de 12 y 11 de 11) y los costos.

## Aportar

Cualquiera con cuenta de GitHub puede hacer [fork](https://github.com/CristianBTA/agente-solicitudes/fork) y proponer una lección, un caso de prueba o una regla, sin invitación y **sin gastar su cuota de IA**. El flujo `abierta-a-aportes` comprueba cada día que el repositorio siga abierto: público, con fork y pull requests para cualquiera, y con el formulario y el instructivo publicados. Todo pasa por un embudo antes de entrar:

1. un filtro automático sin IA (`validar-aporte`): datos personales, seguridad del código y que no rompa nada;
2. la revisión del dueño;
3. solo para las reglas de los subagentes, una prueba con IA que paga la licencia del dueño.

`main` está protegida. **La forma más fácil:** el texto de [«Conectar la IA»](#conectar-la-ia), en la IA que ya usas. Ella lee [`APORTAR-CON-TU-AGENTE.md`](APORTAR-CON-TU-AGENTE.md), te pregunta tu idea, arma el aporte y deja listo el pull request o el texto del formulario. Detalles en [`CONTRIBUTING.md`](CONTRIBUTING.md) y aportes aceptados en [`CHANGELOG.md`](CHANGELOG.md).

## Instalar

```bash
python3.13 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt
.venv/bin/python herramientas/baterias.py      # debe dar las cinco baterías en ✓
.venv/bin/python herramientas/blindaje.py      # cada ataque al pipeline debe salir en RESISTE
```

Las herramientas de `herramientas/` son Python sin IA y se pueden correr solas. La orquestación de agentes (`flujo.js`) se ejecuta como flujo de trabajo de Claude Code (herramienta *Workflow*) con estos argumentos:

```json
{
  "peticion": "Valor contratado en 2025 por cada entidad pública con sede en Medellín, según SECOP II. Para cada entidad: nit_entidad, entidad (nombre), valor_contratado y numero_contratos.",
  "corrida": "<ruta del clon>/corridas/AAAA-MM-DD-nombre",
  "glosario": "<ruta del clon>/ejemplo-secop/negocio.md",
  "fuente": {"tipo": "socrata", "dominio": "www.datos.gov.co", "conjunto": "jbjy-vk9h", "titulo": "SECOP II - Contratos Electrónicos",
             "licencia": "CC BY-SA 4.0", "atribucion": "Agencia Nacional de Contratación Pública – Colombia Compra Eficiente", "unidad": "contratos"},
  "raiz": "<ruta del clon>"
}
```

Con archivos locales, `datos` reemplaza a `fuente`: `{"ventas": "<ruta>/ventas.csv", "clientes": "<ruta>/clientes.csv"}`.

## Herramientas (sin IA)

| Archivo | Qué hace |
|---|---|
| `herramientas/ingesta.py` | Ejecuta el contrato de datos contra datos.gov.co (Socrata) o un CSV local, con las pruebas de carga y la procedencia |
| `herramientas/limpieza.py` | Ejecuta el plan de limpieza: capa limpia con marcas `calidad_*`, sin borrar filas, con calidad antes y después y umbrales |
| `herramientas/perfilar.py` | Perfil determinista: formatos, fechas ambiguas y con hora, repetidos, variantes, códigos que no cruzan y códigos con varios nombres; nunca muestra valores personales |
| `herramientas/verificar.py` | Compuertas, caja de arena, reglas, caso conocido, A = B, conciliación, repetibilidad, tiempos y anticipo; `--autoprueba` y `--sellar` |
| `herramientas/verificar_hipotesis.py` | Sella las hipótesis y las prueba contra su umbral y su línea base |
| `herramientas/verificar_grafico.py` | Lista de comprobación del gráfico, con color y forma (`color.py`: contraste WCAG y simulación de daltonismo); escribe el HTML |
| `herramientas/verificar_presentacion.py` | Calcula y escribe cada cifra de la presentación desde los datos aprobados (la IA solo pone marcadores), comprueba su estructura y escribe las láminas si todo aprueba; `--autoprueba` con mutantes |
| `herramientas/gobernanza.py` | Datos personales en los datos y en las salidas, k-anonimato y comparación con la clasificación de la IA |
| `herramientas/seguridad.py`, `dependencias.py`, `caja.py` | Análisis estático (reglas propias y Bandit), librerías permitidas y caja de arena |
| `herramientas/baterias.py` | Baterías de seguridad, privacidad y lecciones; `--agregar-malo` y `--leccion` para que lo que falló no se repita |
| `herramientas/validar_aporte.py` | Filtro automático de aportes, sin IA: archivos prohibidos, datos personales, seguridad y que no rompa nada |
| `herramientas/blindaje.py` | Banco de ataques al pipeline: caja de arena, compuerta, perfil, salidas, integridad, dependencias y generalización (15 pruebas, con control positivo) |
| `herramientas/integridad.py` | Manifiesto de integridad: sella herramientas, fichas y baterías al inicio y lo comprueba al final |
| `herramientas/informe_final.py` | Informe de las cinco etapas en Markdown y HTML, con todo el texto escapado |
| `herramientas/sgsi.py` | SGSI sin IA: inventario C·I·D, riesgos con la regla de la tríada, Declaración de Aplicabilidad, etiqueta C·I·D de cada corrida; `--efectividad` y `--autoprueba` |
| `herramientas/vulnerabilidades.py` | Vulnerabilidades conocidas (OSV) en las dependencias fijadas de `requirements.txt`, sin llaves |

## Estructura

```
flujo.js                 orquestación de las cinco etapas (historial/ guarda la versión 1)
herramientas/            pruebas y utilidades sin IA
baterias/                seguridad, privacidad, FAILFAST, cruces y lecciones: lo que falló una vez, probado siempre
ejemplo/                 ventas sintéticas con trampas conocidas y su glosario
agentes/                 parámetros de los once subagentes, reglas comunes y quién puede ver qué
ejemplo-secop/           glosario de SECOP II (los datos no se publican: se descargan con ingesta.py)
corridas/<fecha-nombre>/ spec, reglas, caso conocido, implementaciones, bitácora e informes de cada corrida
evidencia/               experimentos: oráculos, mutantes, código y advertencias de los generadores de un solo disparo
DIRECTRICES.md           directrices de nivel senior y cómo validar este repositorio
sgsi/                    SGSI: activos, riesgos, controles, Declaración de Aplicabilidad e informe generado
SECURITY.md              cómo reportar una vulnerabilidad en privado y cómo se responde según C, I o D
CONTRIBUTING.md          cómo aportar sin gastar cuota, y el embudo de validación
CHANGELOG.md             versiones y aportes aceptados, con crédito
.github/                 filtro automático y vigilancia diaria (GitHub Actions), formulario de aporte, plantilla y dueño de las revisiones
```

## Licencias

- El código está bajo licencia MIT (`LICENSE`).
- Este repositorio **no publica los datos de SECOP II**: se descargan con `herramientas/ingesta.py` y el contrato de datos de cada corrida (`contrato_contratos.json`). Las cifras agregadas que aparecen en los informes vienen de SECOP II - Contratos Electrónicos, de la Agencia Nacional de Contratación Pública – Colombia Compra Eficiente, publicado en datos.gov.co con licencia CC BY-SA 4.0.
- Los datos de `ejemplo/` son sintéticos.
