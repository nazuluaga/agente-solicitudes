# Subagentes del pipeline

Cada ficha define un subagente: qué hace, qué puede leer y qué no, qué entrega, sus reglas, lo que nunca hace y la prueba sin IA que lo comprueba. Las fichas no dependen de una herramienta: se pueden pegar como instrucciones en cualquier asistente (Claude, ChatGPT, Copilot, Gemini) junto con los archivos que la ficha dice que puede leer. `flujo.js` las orquesta en orden y con esta misma separación.

| # | Subagente | Etapa | Lo comprueba (sin IA) |
|---|---|---|---|
| 01 | [Lector](01-lector.md) | 1 · Ingesta | `herramientas/ingesta.py` |
| 02 | [Especificador](02-especificador.md) | 2 · Procesamiento | `herramientas/verificar.py --autoprueba` |
| 03 | [Limpiador](03-limpiador.md) | 2 · Procesamiento | `herramientas/limpieza.py` |
| 04 | [Revisor de la especificación](04-revisor-de-la-especificacion.md) | 2 · Procesamiento | `herramientas/verificar.py --sellar` |
| 05 | [Generador (A y B)](05-generador.md) | 2 · Procesamiento | `herramientas/verificar.py` |
| 06 | [Reparador](06-reparador.md) | 2 · Procesamiento | `herramientas/verificar.py` |
| 07 | [Proponente de hipótesis](07-proponente-de-hipotesis.md) | 3 · Análisis | `herramientas/verificar_hipotesis.py --sellar` |
| 08 | [Probador de hipótesis](08-probador-de-hipotesis.md) | 3 · Análisis | `herramientas/verificar_hipotesis.py` |
| 09 | [Graficador](09-graficador.md) | 4 · Visualización | `herramientas/verificar_grafico.py` |
| 10 | [Custodio de datos personales](10-custodio-de-datos-personales.md) | 5 · Gobernanza | `herramientas/gobernanza.py` |
| 11 | [Revisor ciego de seguridad](11-revisor-ciego-de-seguridad.md) | 5 · Gobernanza | `herramientas/baterias.py` |
| 12 | [Presentador](12-presentador.md) | 4 · Visualización | `herramientas/verificar_presentacion.py` (calcula y escribe cada cifra) |

Las [reglas comunes](00-reglas-comunes.md) aplican a todos.

## Quién puede ver qué
La independencia es lo que evita que el que prueba comparta los puntos ciegos del que hace. Por eso cada subagente tiene cosas que **no** puede leer.

| Subagente | Puede leer | No puede leer |
|---|---|---|
| Lector | metadatos, conteos | filas |
| Especificador | perfil, CSV crudos, glosario | implementaciones |
| Limpiador | spec, perfil, formato del plan | reglas, caso conocido, implementaciones |
| Revisor de la especificación | todo el criterio y los planes | implementaciones |
| Generador A / B | spec, planes, capa limpia | reglas, caso conocido, sellos, la otra implementación |
| Reparador | su falla, su sección del informe, spec | reglas, la otra implementación |
| Proponente | spec, resultado aprobado | pruebas |
| Probador | hipótesis (enunciado, umbral, línea base), CSV | razonamiento del proponente, resultado aprobado, implementaciones |
| Graficador | resultado aprobado, procedencia | datos crudos |
| Presentador | resultado aprobado, hipótesis probadas, gráfico aprobado, supuestos y preguntas, procedencia | datos crudos, capa limpia, código y bitácoras de los demás |
| Custodio | metadatos de todas las columnas, conteos | filas y valores |
| Revisor ciego de seguridad | el código generado | bitácora y notas de los autores |

## Orden

```
Ingesta        lector ──► ingesta.py (5 pruebas de carga, procedencia)
               └─► custodio (en paralelo, solo metadatos)
Procesamiento  especificador ──► limpiador ──► limpieza.py ──► revisor (sella) ──► generador A ∥ generador B
               ──► verificar.py ──► reparador (hasta 2 rondas)
Análisis       proponente (sella) ──► probador ──► verificar_hipotesis.py
Visualización  graficador ──► verificar_grafico.py            (en paralelo con el análisis)
               presentador ──► verificar_presentacion.py      (cuando terminan el análisis y el gráfico)
Gobernanza     revisor ciego de seguridad ──► gobernanza.py ──► baterias.py ──► informe_final.py
```
