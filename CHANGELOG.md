# Registro de cambios

Cada aporte aceptado queda aquí, con el usuario de GitHub de quien lo propuso (si aceptó aparecer).

## v1 · 6 de noviembre de 2026 · semilla

- Pipeline de cinco etapas con once subagentes, herramientas sin IA, directrices, baterías (seguridad, privacidad, FAILFAST y lecciones), dos corridas selladas y evidencia de los experimentos.
- Primeras lecciones de la revisión ciega de seguridad (L15–L20): reglas en caja de arena, lectura estricta de CSV, mensajes saneados, URLs bloqueadas, enlaces solo locales y ejecución desde la fuente.

## v1.1 · 6 de noviembre de 2026 · prueba de la guía de aportes

- `APORTAR-CON-TU-AGENTE.md`, probada con tres participantes simulados (cerca de 110.000 tokens por aporte, 11 minutos).
- Lo que encontraron se integró: la familia exec/spawn de `os` y sus alias, el CSV con separador distinto de la coma (FAILFAST) y once arreglos de la guía y del filtro (orden de los pasos, `upstream/main`, filtro sin efectos sobre el repositorio, ids de lección sin choques).
- Corrida de cinco etapas con capa limpia, aprobada en las cinco.

## v1.2 · 6 de noviembre de 2026 · blindaje del pipeline

- `herramientas/blindaje.py`: 15 ataques al pipeline, con un control positivo. Línea base: resistía 5 de 14; ahora resiste 15 de 15.
- Caja de arena: sin lectura de la carpeta personal, entorno mínimo sin secretos y tope de memoria por huella física.
- Compuerta: 8 evasiones conocidas cerradas sin romper el código legítimo.
- Inyección de instrucciones: cuarentena en el perfil y la limpieza, rechazo en el filtro de aportes, batería `baterias/inyeccion/` y regla común 7.
- Integridad: manifiesto sellado antes de cualquier agente y comprobado al final; las baterías solo crecen.
- Cadena de suministro: dependencias con huella (`--require-hashes`) y acciones de GitHub fijadas a su commit.
- Auditoría de independencia: 16 agentes en 4 corridas, 0 accesos prohibidos. Lecciones L25 a L33.

## v1.3 · 6 de noviembre de 2026 · SGSI con la tríada C·I·D

- `sgsi/`: 16 activos valorados en confidencialidad, integridad y disponibilidad; 27 riesgos; 39 controles del repositorio y la Declaración de Aplicabilidad de los 93 controles del Anexo A de ISO/IEC 27001:2022 (64 aplican, 29 se excluyen con su justificación).
- `herramientas/sgsi.py`: lo comprueba sin IA, con la regla de la tríada (C sin reversa → preventivo; I se corrige → detectivo; D se restablece → correctivo), el impacto tomado del activo, la cobertura de 6.1.2 c 1 y la etiqueta C·I·D de cada corrida. `--autoprueba`: 21 de 21 SGSI dañados atrapados. `--efectividad`: 27 controles operando y 12 documentales.
- Controles nuevos que salieron de la valoración: vigilancia diaria de `main` y de vulnerabilidades conocidas en las dependencias (OSV), escaneo de secretos y de permisos de los flujos en cada aporte, reporte privado de vulnerabilidades (`SECURITY.md`) y retención mínima de los datos crudos.
- Lección L42: el filtro corría en Linux, donde no hay `sandbox-exec`; B11 y B12 cedían y todo aporte que tocara `herramientas/` habría fallado. El filtro y la vigilancia corren ahora en macOS, y `sgsi.py` lo exige.
- Lección L43: la efectividad del SGSI mostró que en GitHub Actions el banco de blindaje se cortaba en B18 (la prueba exigía los CSV de SECOP, que no se publican) y el filtro pasaba igual. B18 ya no los necesita, un `SystemExit` en una prueba queda como ERROR y el filtro exige que el banco termine.
- Riesgo que queda a decisión del dueño: R16, referencias legales inventadas por la IA que `validar_ficha.py` deja pasar (residual 15, por encima del criterio de 10).

## Aportes del grupo

Cada aporte entra sin nombre hasta que quien lo propuso acepta aparecer (la casilla del pull request o del formulario).

### 6 de noviembre de 2026

- **Fórmulas de Excel exportadas como texto (L40).** `reglas_base.leer_csv` se detiene ante una celda que empieza por «=» (`=DAY(J2)`) en vez de leerla como texto. Con 168 fórmulas sembradas en `ejemplo/datos/ventas.csv`, las que cambiaban sin aviso las cifras de las reglas pasaron de 49 a 0; en los 11 CSV del repositorio (241.742 filas) no hubo ninguna falsa alarma. Caso nuevo en `baterias/failfast/`. Propuesto por un participante del curso; su usuario se agrega cuando acepte aparecer.
- **Por qué no cruza un valor entre tablas (L41).** El perfil separa los que no cruzan por espacios dobles o invisibles (U+00A0) dentro del valor y por tildes, puntuación (S.A.S. / SAS) o ceros a la izquierda (001 / 1), y cuenta los que no tienen ninguna de esas causas. En la prueba explicó 100 de 100 casos con esas causas y ninguno de los valores que de verdad faltaban. Batería nueva `baterias/cruces/`. La búsqueda de nombres parecidos del aporte original no entró: marcaba como parecidos productos distintos (Triple 15 / Triple 18) y tardaba 141 s con 20.000 valores distintos, frente a menos de 2 s de lo demás. Propuesto por un participante del curso; su usuario se agrega cuando acepte aparecer.
