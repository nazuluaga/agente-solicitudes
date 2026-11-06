# Directrices de análisis de datos con IA

> Los parámetros de cada subagente (rol, qué puede leer y qué no, qué entrega, reglas, lo que nunca hace y la prueba que lo comprueba) están en [`agentes/`](agentes/README.md).

Estas son las directrices que un analista de datos senior le exige a un análisis hecho con IA antes de firmar una cifra. Cada una dice **qué exige**, **por qué**, **dónde está aplicada** en este repositorio y **cómo se comprueba**. Sirven para validar este trabajo y para revisar cualquier otro.

El principio que las ordena todas: **la IA propone y una prueba sin IA comprueba.** La IA acorta el tiempo de cada etapa, pero no reemplaza ninguna. Por eso cada etapa tiene su prueba, y la prueba no la escribe quien escribe el código.

---

## Validar este repositorio en 15 minutos

Se necesita macOS o Linux con Python 3.13. La caja de arena usa `sandbox-exec`, que trae macOS; en Linux el código corre igual, pero sin esa capa.

```bash
python3.13 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.txt

# 1. Las baterías: seguridad (código malo bloqueado y bueno aceptado), privacidad y lecciones
.venv/bin/python herramientas/baterias.py

# 2. La corrida sellada del ejemplo sintético se vuelve a verificar desde cero (sin IA)
.venv/bin/python herramientas/verificar.py corridas/2026-11-06-ventas-semestre

# 3. Probar al probador: cada mutante comete un error típico y el criterio debe atraparlo
ls evidencia/sintetico/mutantes/*.py | sed 's#.*/\(.*\)\.py#\1=&#' | \
  xargs .venv/bin/python herramientas/verificar.py corridas/2026-11-06-ventas-semestre --impl

# 4. El oráculo del ejemplo sintético se rehace igual (semilla fija; los dos caminos deben coincidir)
.venv/bin/python evidencia/sintetico/generar_datos.py /tmp/datos-prueba /tmp/verdad-prueba.json
cmp /tmp/datos-prueba/ventas.csv ejemplo/datos/ventas.csv && echo "datos idénticos"

# 5. Gobernanza de una corrida: datos personales, salidas limpias, k-anonimato
.venv/bin/python herramientas/gobernanza.py corridas/2026-11-06-ventas-semestre

# 5b. Blindaje: se ataca cada capa a propósito (caja de arena, compuerta, perfil, salidas, integridad, dependencias)
.venv/bin/python herramientas/blindaje.py

# 5c. SGSI: la tríada C·I·D, los riesgos y la Declaración de Aplicabilidad, comprobados sin IA (y el probador, probado)
.venv/bin/python herramientas/sgsi.py --autoprueba
.venv/bin/python herramientas/sgsi.py --efectividad

# 5d. Probar al probador de la presentación: 4 presentaciones buenas aprueban y 29 mutantes (número a mano, marcadores pegados, NaN, título de tema…) fallan
.venv/bin/python herramientas/verificar_presentacion.py --autoprueba

# 6. (Opcional, con red) SECOP II: los datos no vienen en el repositorio; se descargan con su contrato y se prueban al cargar
.venv/bin/python herramientas/ingesta.py ejemplo-secop/contrato_recorte_2024-2026.json --salida ejemplo-secop/datos --repetir
.venv/bin/python herramientas/verificar.py corridas/2026-11-06-secop-medellin-2025
```

SECOP II se actualiza a diario. Si el recorte de hoy no es idéntico al del 6-nov-2026, el paso 6 puede dar otras cifras: es lo esperado, y la procedencia de la carga dice qué cambió (filas, huella).

Lo que debe salir: las cinco baterías en ✓, el blindaje con todas sus pruebas en «RESISTE» (en Linux no hay sandbox-exec: B01 sale «NO APLICA» y B11 y B12 ceden, por eso el filtro de aportes corre en macOS), la corrida en «aprobado», la referencia `m00` sin fallas y las mutantes `m01` a `m12` con al menos una falla cada una, los datos idénticos, la gobernanza aprobada y el SGSI sin fallas, con sus 21 mutantes atrapados. Si algo no sale así, el repositorio no cumple lo que dice.

---

## A · Antes de escribir código

**D1 · La pregunta se convierte en una especificación verificable.**
Qué cifra sale, qué incluye y qué excluye, en qué unidades y período, con qué columnas y en qué forma.
*Por qué:* una petición de una frase admite varias cifras correctas, y la IA escoge una sin avisar.
*Dónde:* `spec.json` de cada corrida (`interpretacion`, `definiciones`, `salida`).
*Cómo se comprueba:* cada definición dice su fuente (`glosario`, `datos` o `supuesto`).

**D2 · El glosario del negocio manda; lo que no resuelve se pregunta.**
Toda decisión que cambie la cifra y no salga del glosario ni de los datos se escribe como pregunta, con su valor por defecto y su impacto en pesos.
*Por qué:* lo que la IA no sabe, lo inventa. Los datos no dicen si el Concejo es una entidad aparte del Distrito.
*Dónde:* `ejemplo/negocio.md` y `ejemplo-secop/negocio.md`; `preguntas` y `supuestos` en la spec.
*Cómo se comprueba:* la corrida de SECOP abrió dos preguntas (el NIT que agrupa al Concejo y la Personería, y la universidad privada), cada una con su cifra.

**D3 · Conocer los datos antes de pedir código: perfil completo, determinista y sin filas.**
*Por qué:* explorar quita que la IA invente la **estructura** (columnas, tipos, formatos), pero no el **significado** (D2). Los problemas son raros y no salen en `head()`: 6 códigos vacíos en 1.520 filas, o 5 contratos del 31 de diciembre con hora.
*Dónde:* `herramientas/perfilar.py`: formatos mezclados, fechas ambiguas con su lectura demostrada, filas repetidas, claves repetidas, variantes de escritura, códigos que no cruzan, un código con varios nombres y fechas con hora. Nunca muestra valores de columnas personales ni de texto libre.
*Cómo se comprueba:* `herramientas/baterias.py` (batería de privacidad).

**D4 · Anticipar el número antes de ejecutar.**
Un rango de magnitud, escrito antes de tener la cifra.
*Por qué:* un error de unidades o de unión salta a la vista si ya había una expectativa.
*Dónde:* `anticipo` en la spec; el informe dice si el resultado quedó dentro.

## B · Ingesta

**D5 · Contrato de datos: columnas mínimas, tipos declarados, llave, dominios y rangos.**
Los identificadores van como texto. Lo que no cumple el tipo rechaza la carga (FAILFAST).
*Dónde:* `contrato_<tabla>.json` (lo escribe la IA) y `herramientas/ingesta.py` (lo ejecuta).
*Cómo se comprueba:* una columna que no existe en la fuente o una columna personal sin justificar rechazan la carga antes de descargar.

**D6 · Las cinco pruebas de cada carga, más repetibilidad y procedencia.**
Conteo contra la fuente, llave única, llave sin nulos, rangos y dominios. Leer dos veces debe dar el mismo archivo, byte a byte. Queda una procedencia con fecha, filtro, filas, huella SHA-256, licencia y atribución.
*Dónde:* `procedencia_<tabla>.json`.

**D7 · Minimización: que un dato sea público no lo vuelve de uso libre.**
Solo se descargan las columnas que la pregunta necesita. Sin una justificación escrita en el contrato de datos no entra ninguna columna:
- personal: nombres de personas, documentos, datos bancarios o domicilios;
- cuasi-identificadora: tipo de documento, género o nacionalidad;
- de texto libre: objeto, descripción o justificación.
*Por qué:* SECOP II publica la cédula de los contratistas, sus cuentas bancarias y los nombres de supervisores y ordenadores del gasto para la transparencia de la contratación. Eso no autoriza cualquier otro uso: todo tratamiento sigue sujeto a los principios de la Ley 1581 de 2012 (finalidad, circulación restringida, seguridad). Además, el texto libre trae nombres o cédulas escritos a mano en cerca de 1 de cada 1.000 filas. Lo que no se descarga no se filtra.
*Cómo se comprueba:* `baterias/privacidad/columnas_secop.json` fija la clase esperada de 41 columnas de SECOP II (16 personales, 7 cuasi-identificadoras, 4 de texto libre y 14 sin marca); si el clasificador cambia, la batería falla. Ningún CSV de este repositorio trae columnas personales ni patrones de datos personales en su contenido.

## C · Procesamiento

**D8 · El criterio se escribe antes y aparte del código, y se sella.**
Las reglas y el caso conocido los escribe un agente que no escribe el código; otro agente los revisa y los sella con huellas SHA-256. Cambiar el criterio después invalida la aprobación.
*Dónde:* `reglas.py`, `caso_conocido/`, `sellos.json`; la constancia de un sello rehecho está en `historial/NOTA-SELLOS.md`.

**D9 · Las reglas son más simples que el análisis y no comparten su lógica.**
La conservación compara el total del resultado con un total sacado directo de la fuente, sin unir tablas. Las reglas usan solo la biblioteca estándar, así una trampa de pandas no se cuela en el criterio.
*Cómo se comprueba:* la regla de conservación atrapó un error real de pandas, `dayfirst=True` (lección L01), sin que nadie leyera el código.

**D10 · Caso con respuesta conocida que contenga cada borde.**
Fechas límite (00:00 del 1 de enero, 23:59 del 31 de diciembre), repetidos, vacíos, variantes de escritura y códigos que no cruzan.
*Cómo se comprueba:* en SECOP, el error de zona horaria no cambia nada en los datos de hoy, pero el caso conocido lo atrapa. Protege contra datos que todavía no han llegado.

**D11 · Dos implementaciones independientes, con herramientas distintas, que deben dar lo mismo.**
pandas y Python puro. Un error propio de una herramienta no se repite en la otra.

**D12 · Todo conteo cierra; limpiar es marcar.**
Cada implementación concilia: filas leídas = usadas + excluidas por motivo. Nada se borra en silencio.
*Dónde:* `conciliar(datos)` en `impl_a.py` e `impl_b.py`; tabla de conciliación en el informe.
*Por qué:* quitar «duplicados» por (entidad, valor, fecha) borró 25.824 contratos legítimos en una de las mutantes (lección L08).

**D13 · Repetible.** Misma entrada, mismo resultado. El verificador corre cada implementación dos veces.

**D14 · Probar al probador.**
Un criterio vale lo que atrapa. Se mide con mutantes, que son la referencia con un solo error típico, y la referencia sin errores no debe dar falsas alarmas.
*Cómo se comprueba:* `evidencia/*/resultados_mutacion.txt`: 12 de 12 en el ejemplo sintético y 11 de 11 en SECOP, sin falsas alarmas.

## C2 · Limpieza de datos (dentro del procesamiento)

La IA propone el plan de limpieza (`plan_limpieza_<tabla>.json`) y `herramientas/limpieza.py` lo ejecuta igual cada vez. Ficha del subagente: [`agentes/03-limpiador.md`](agentes/03-limpiador.md).

**DL1 · Tres capas: cruda, limpia y respuesta.** El dato crudo no se toca y conserva su procedencia y su huella. La capa limpia (`limpio/<tabla>.csv`) se reconstruye desde el plan. La respuesta se calcula sobre la capa limpia.
*Cómo se comprueba:* la limpieza verifica que la huella del crudo no cambió.

**DL2 · Limpiar es marcar (R14).** La capa limpia tiene las mismas filas, en el mismo orden y con la misma llave. Cada problema queda en una columna `calidad_<marca>`, y `calidad_ok` dice si la fila está limpia. La spec decide qué marcas excluyen la fila del análisis y cuáles solo avisan, y la conciliación las cuenta.

**DL3 · Reglas declaradas, no código suelto.** Cada operación (texto, invisibles y Unicode NFC, reemplazar, nulos disfrazados, mapear, fecha, número, rango, atípicos, repetidos, comparar entre columnas) informa cuántas filas cambió, cuántas marcó y un ejemplo; nunca de columnas privadas. Los mapas de variantes son listas cerradas y versionadas: lo que no está en el mapa se marca, no se adivina.

**DL4 · Lo disfrazado y lo invisible también se limpia.** «No Definido», «N/A» o «-» son nulos disfrazados. Los caracteres de control (en SECOP apareció un U+0096 dentro de un nombre) se quitan, y el texto se normaliza a NFC antes de comparar.

**DL5 · Atípicos e imposibles se marcan con un método explícito.** El método es el rango intercuartílico sobre log10, para montos que abarcan varios órdenes de magnitud. Nada se corrige en silencio (R7). Los límites quedan en el informe, en pesos.

**DL6 · Calidad medida antes y después, con umbrales que bloquean.** Completitud, validez y unicidad por columna. Un umbral que el dato real incumple no se relaja en silencio: o el umbral era un supuesto equivocado (se anota) o el dato no sirve para la pregunta.

**DL7 · Una limpieza mal planteada también se atrapa.** Las reglas y el caso conocido calculan desde el dato **crudo**, y el caso conocido pasa por el **mismo** plan antes de la implementación. Una regla de limpieza mal escrita (por ejemplo, «IVA mayor que el subtotal», que marcó 1.150 filas en una prueba) aparece en el conteo de marcas y en la conservación.

## D · Análisis

**D15 · Hipótesis registradas antes de probarlas.**
Quien propone escribe el enunciado, la medida, el umbral y la línea base, y los sella. Otro agente, sin ver ese razonamiento, escribe la consulta desde los datos de origen. El veredicto lo da el código.
*Dónde:* `hipotesis.json`, `sellos_hipotesis.json`, `hipotesis.py` y `herramientas/verificar_hipotesis.py`.
*Por qué:* mover el umbral después de ver el resultado convierte cualquier dato en confirmación.

**D16 · Si hay modelo:** partición temporal, línea base de la misma partición, solo variables que se conocen en el momento de decidir (sin fuga), métrica según el costo del error y umbral explícito. Lo exige el módulo 3 del curso; los ejemplos de este repositorio no entrenan modelos.

## E · Visualización

**D17 · El gráfico responde la pregunta y no exagera.**
- Barras desde cero (factor de mentira 1).
- Título con qué, dónde y cuándo; unidades en el eje.
- Fuente y fecha de consulta visibles; período incompleto marcado.
- Cuenta de control: lo que suma el gráfico más lo que se dejó fuera es igual al total de la tabla.
*Dónde:* `herramientas/verificar_grafico.py`. El HTML lo escribe el verificador, no el código de la IA.

**D29 · El color tiene una función y se mide.**
- Siete colores o menos; lo ideal es gris para el contexto y un color de acento para lo que importa (Datawrapper).
- Contraste de 3:1 o más de cada marca contra el fondo (WCAG 1.4.11) y de 4,5:1 para el texto (WCAG 1.4.3). Un color por debajo de 3:1 solo pasa si la marca lleva su valor escrito.
- Colores distinguibles con daltonismo: diferencia perceptual (ΔE en OKLab ×100) de 8 o más entre cada par, con protanopía, deuteranopía y tritanopía simuladas; nunca rojo contra verde como única diferencia.
- Un solo eje de valores (con dos ejes, quien diseña escoge dónde se cruzan las líneas); sin 3D; tortas de cinco porciones o menos; si la escala es logarítmica, se dice.
*Dónde:* `herramientas/verificar_grafico.py` y `herramientas/color.py`, con la batería `baterias/grafico/` (casos buenos que deben pasar y malos que deben fallar).
*Por qué:* el ojo compara mejor posiciones y longitudes que colores (Cleveland y McGill, 1984); un color que no se distingue o no contrasta borra el dato para una parte del público.

**D30 · La presentación da la respuesta primero y cada cifra sale de los datos.**
- Primero la conclusión y lo que se pide decidir (pirámide de Minto); luego situación, complicación, pregunta y respuesta (SCQA).
- Cada título es una afirmación con su cifra, de dos líneas como máximo, y debajo va una sola evidencia (método afirmación-evidencia de Alley). Si solo se leen los títulos, se entiende el argumento.
- La IA no escribe números: pone marcadores (`{total}`) y declara el cálculo de cada uno; el código calcula la cifra desde el resultado aprobado y la escribe. Un dígito, una magnitud con palabras o un «%» fuera de un marcador hacen fallar la presentación. En el lanzamiento de GPT-5 (agosto de 2025), una barra de 52,8 % se dibujó más alta que una de 69,1 %: lo que no calcula el código, no se presenta.
- Método, incertidumbre y límites explícitos, con cada pregunta abierta nombrada (como METR); recomendación con qué, quién, próximo paso y cómo se mide.
- La IA escribe solo `presentacion.json`; las láminas, las tablas, la fuente y la fecha las pone el verificador, y solo si todo aprueba.
- Lo que el código no puede ver: que la frase use bien una cifra correcta (por ejemplo, llamar «Medellín» a las entidades con sede en Medellín). Eso lo revisa una persona o un juez ciego con la lámina «Prueba de los títulos».
*Dónde:* `agentes/12-presentador.md` y `herramientas/verificar_presentacion.py` (`--autoprueba`: 4 presentaciones buenas aprueban y 29 mutantes fallan donde deben).

## F · Gobernanza

**D18 · Nunca filas a la IA; el texto libre es un dato personal en potencia.**
La IA trabaja con nombres, tipos y conteos. Antes de publicar, un barrido determinista busca cédulas con contexto, correos, celulares y nombres con tratamiento en los datos y en todo lo que se publica. Si se publican personas, se exige k-anonimato (k ≥ 5).
*Dónde:* `herramientas/gobernanza.py`. La IA (custodio) clasifica todas las columnas de la fuente y el código compara su clasificación con la propia.
*Por qué:* además de proteger a las personas, la IA no puede seguir una instrucción escondida en un texto que nunca lee.

**D19 · Licencia y atribución de la fuente.** SECOP II se publica con CC BY-SA 4.0; la atribución va en la procedencia, en la cita y en este repositorio.

**D20 · Citar con fecha (R9).** Fuente, conjunto, filtro, fecha de consulta y filas, en cada cifra que sale.

## G · Seguridad del código que escribe la IA

**D21 · Lista cerrada de librerías y versiones fijas.**
El código de la IA solo importa la biblioteca estándar y lo de `herramientas/permitidas.json`; se instala solo desde `requirements.txt`. Nunca se instala desde el código.
*Por qué:* un nombre inventado (`pandas-secop-tools`) lo puede registrar un atacante. Comprobar que el paquete exista no basta (*slopsquatting*).

**D22 · Contrato estrecho y análisis estático antes de ejecutar.**
El código de la IA es una función pura. Antes de correrlo se revisan con reglas propias y con Bandit: ejecución de texto, comandos, deserialización, red, escritura, reflexión y secretos. Si algo bloquea, no se ejecuta.
*Dónde:* `herramientas/seguridad.py` y `herramientas/dependencias.py`.

**D23 · Caja de arena.** Sin red y sin escritura fuera de una carpeta temporal (`herramientas/caja.py`).

**D24 · Los datos son entrada no confiable.** Todo lo que viene de los datos se escapa al armar el HTML: un nombre con `<script>` se muestra, no se ejecuta.

**D25 · Revisión ciega de seguridad, con prueba por hallazgo.**
Un agente que no conoce a los autores revisa todo el código generado. Cada hallazgo trae un fragmento que lo reproduce, y un hallazgo sin prueba no cuenta. Lo confirmado entra a la batería.

## H · Aprendizaje y evidencia

**D26 · Baterías: lo que falló una vez se vuelve prueba para siempre.**
- Seguridad: código malo que debe bloquearse y código bueno que debe pasar. Así se prueba al probador: el falso positivo de `re.compile` es un caso.
- Privacidad: datos personales que no pueden salir y textos que no son personales.
- Lecciones: cada error real, con la prueba que lo atrapa.
*Dónde:* `baterias/`, `herramientas/baterias.py`.

**D27 · Bitácora del copiloto.** Por etapa: qué se pidió, qué devolvió, cómo se probó, qué se corrigió y qué quedó sin verificar (`bitacora/`). Va en el informe final.

**D28 · Evidencia honesta y control según el riesgo.**
Se reporta también cuando la IA sola acertó, y se mide lo que cuesta el control.
*Dónde:* `evidencia/README.md`: los generadores de un solo disparo acertaron en los seis casos (en SECOP, uno excluyó una universidad privada y lo declaró); el procesamiento verificado costó entre 3,4 y 4,5 veces los tokens de un generador solo.
*Cómo se aplica:* para explorar basta con el perfil y una revisión rápida. Cuando la cifra va a sostener una decisión con plata, una norma o un informe público, se usa el pipeline completo.

---

## I · Blindaje del pipeline: atacar cada capa a propósito

El mismo patrón del generador y el validador, aplicado al pipeline entero: un atacante (cada prueba de `herramientas/blindaje.py`) y un defensor (cada capa). El detalle y la línea base están en [`evidencia/blindaje/README.md`](evidencia/blindaje/README.md).

**DB1 · Toda batería de ataques lleva un control positivo.** Un ataque que «resiste» porque nada funciona no prueba nada. B00 corre código normal en la caja: si falla, ninguna prueba de la caja vale (lección L27).

**DB2 · La caja de arena niega la red, la escritura y la lectura de la carpeta personal, y da un entorno mínimo.** El código de la IA no ve las variables de entorno del proceso que lo lanza (secretos) y tiene topes de tiempo y de memoria. La memoria se mide como huella física, no como memoria residente (B01, B10–B14; lecciones L25, L26, L28).

**DB3 · Las herramientas no pueden cambiar durante una corrida.** Un manifiesto de integridad se sella antes de cualquier agente y se comprueba al final. Las baterías solo pueden crecer (B02, L29).

**DB4 · Los datos y los aportes son datos, nunca instrucciones.** Los valores con forma de orden para una IA quedan en cuarentena en el perfil y en la limpieza; el filtro rechaza aportes que dan órdenes a los agentes; y es una regla común de todos los subagentes (B04, B07, L30, `baterias/inyeccion/`).

**DB5 · Las salidas no ejecutan nada al abrirse.** Las fórmulas de Excel se neutralizan y se marcan en la capa limpia; el HTML de los datos se escapa (B03, L31, L19, L23).

**DB6 · La compuerta se ataca con evasiones conocidas,** y cada evasión cerrada queda en la batería sin romper el código legítimo (B15, L32).

**DB7 · Cadena de suministro fijada.** Cada dependencia lleva su huella y se instala con `--require-hashes`; cada acción de GitHub está fijada a su commit (B08, L33).

**DB8 · Los generadores generalizan.** Sobre datos nuevos que nadie vio (otra semilla del oráculo), A y B deben dar exacto el resultado correcto (B05).

**DB9 · La independencia se audita, no se supone.** Se revisan las transcripciones reales: ningún agente puede haber abierto lo que su ficha le prohíbe (`evidencia/blindaje/auditar_independencia.py`: 16 agentes, 0 accesos prohibidos).

**DB10 · Quien toca una herramienta corre el banco de blindaje.** El filtro de aportes lo corre si el aporte cambia `herramientas/`: debilitar una defensa hace fallar el aporte.

## J · SGSI: la tríada C·I·D aplicada al pipeline

La seguridad del repositorio, ordenada como un sistema de gestión (ISO/IEC 27001:2022) y comprobada sin IA, igual que el análisis. El método, el alcance y los proveedores están en [`sgsi/README.md`](sgsi/README.md); lo que hay hoy, en [`sgsi/INFORME-SGSI.md`](sgsi/INFORME-SGSI.md).

**DS1 · Cada activo dice cuánto vale en confidencialidad, en integridad y en disponibilidad, y por qué.** Su clasificación sale de la C, y lo restringido nunca entra al repositorio público (A.5.9, A.5.12).
*Cómo se comprueba:* `sgsi.py` cruza el inventario con `git ls-files` y `.gitignore`: los datos de SECOP con personas deben quedar ignorados y sin versionar.

**DS2 · Cada riesgo pierde una sola propiedad, y su impacto no se escribe: sale del valor del activo.** Así nadie baja un riesgo bajando el impacto a mano. Nivel = probabilidad × impacto; criterio de aceptación: 10 o menos (6.1.2).

**DS3 · La regla de la tríada.** La confidencialidad no tiene reversa: solo un control preventivo baja su riesgo. La integridad se corrige si se detecta: hace falta un control detectivo. La disponibilidad se restablece: hace falta un control correctivo. Si un residual baja sin el control que corresponde, la herramienta lo rechaza.

**DS4 · La Declaración de Aplicabilidad tiene los 93 controles del Anexo A, y cada «sí» apunta a un control que existe en el repositorio** (6.1.3 d). Un control cuya evidencia desaparece invalida su fila.

**DS5 · Un control vale lo que su prueba.** `--efectividad` corre el banco de blindaje, las baterías, la corrida sintética y los mutantes, y solo cuenta los controles que pasan (9.1). La vigilancia diaria (`vigilancia-diaria`) lo repite sobre `main` y consulta OSV por vulnerabilidades conocidas en las dependencias fijadas (A.8.8).

**DS6 · Probar al probador también aquí.** `sgsi.py --autoprueba` daña el SGSI 21 veces a propósito (un riesgo de C rebajado con un control detectivo, una fila de la SoA que dice «sí» sin control, evidencia que ya no existe…) y debe atraparlas todas, con los datos de hoy como control positivo.

**DS7 · Lo que queda por encima del criterio se ve y lo decide el dueño del riesgo, por escrito** (6.1.3 f). Hoy: R16, una referencia legal inventada por la IA que `validar_ficha.py` deja pasar.

**DS8 · Cada corrida sale con su etiqueta C·I·D:** si sus salidas se pueden publicar (barrido y k-anonimato), si su criterio sigue sellado (huellas recalculadas) y si se puede reconstruir (contrato de datos o semilla). Las vulnerabilidades se reportan en privado y se responden según la propiedad que se perdió ([`SECURITY.md`](SECURITY.md)).

## Correspondencia con el curso «Big Data con IA» (NODO · EAFIT)

| Módulo | Reglas del agente del curso | Directrices |
|---|---|---|
| 1 · Pedir, probar, citar | R1 solo nombres reales · R2 nunca filas · R3 todo conteo cierra · R4 prueba independiente · R5 no borrar en silencio · R6 fechas · R7 valores imposibles se cuentan · R8 primero igual, después rápido · R9 citar con fecha | D1–D4, D9, D12, D13, D18, D20 |
| 2 · Ingesta y procesamiento | R10 leer completo · R11 esquema declarado · R12 correr dos veces da lo mismo · R13 particionar sin perder nulos · R14 limpiar es marcar · R15 las cinco pruebas · R16 sin traer todo a memoria | D5–D7, D12, D13, DL1–DL7 |
| 3 · Analítica | hipótesis, línea base, partición temporal, fuga, umbral, desmentir con una consulta, bitácora | D15, D16, D27 |
| 4 · Visualización y gobernanza | etiqueta exacta, eje desde cero, factor de mentira, período incompleto, cuenta de control, color con contraste y apto para daltonismo, presentación con la respuesta primero y cifras que escribe el código, unicidad (k), qué no se pega al asistente, cita | D17–D20, D24, D29, D30 |

R13 y R16 son de PySpark: aquí no aplican, porque los datos caben en memoria (91.072 filas).

## Lo que este repositorio no garantiza

- «Aprobado» quiere decir que pasa las comprobaciones escritas, no que sea correcto en todo sentido.
- Si el especificador y el revisor entienden mal lo mismo, el error pasa. Por eso el informe muestra la interpretación, los supuestos y las preguntas: es lo único que una persona tiene que leer.
- El barrido de datos personales usa expresiones regulares: puede dejar pasar formas que no conoce. La minimización (D7) es la primera defensa.
- La caja de arena depende de `sandbox-exec` de macOS.
