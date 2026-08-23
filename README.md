# Agente de Reconciliación de Facturas — Local-First

Agente de back-office que lee facturas, las cruza contra el ERP y emite un dictamen
auditable. Toda la inferencia corre **en el dispositivo**: ningún dato de factura sale
de la máquina.

Construido para el hackathon QVAC de Tether — ver [CONTEXT.md](CONTEXT.md).

> **Estado: Fase 2 de 3.** Backend, base de datos y dashboard completos y verificados
> end-to-end. La capa LLM corre detrás de una interfaz con implementaciones stub; la
> integración real con QVAC llega en la Fase 3 y solo requiere escribir una clase.

---

## El problema

Reconciliar facturas es gente leyendo documentos sucios, tecleando números y
comparándolos a mano contra el ERP. Es alto volumen, alto valor, y toca datos que una
empresa no puede mandar a una API de terceros. Ese último punto es lo que lo hace el
caso natural para IA local.

## Cómo está resuelto

El principio de diseño es que **Python está al mando y el LLM es una herramienta**, no
al revés. El modelo nunca hace dos trabajos en la misma llamada — pedirle a un modelo de
1–4B que extraiga datos *y* razone sobre la base de datos simultáneamente produce
amnesia de contexto y fracasa.

```
Fase 1  Ingesta        Operador sube la foto de la factura
Fase 2  Extracción     LLM transcribe → JSON validado    [self-correction loop]
        ── el modelo se detiene ──
Fase 3  Herramienta    Python consulta MariaDB (el ERP)
Fase 4  Verificación   Python corre 6 checks deterministas — sin tocar el modelo
Fase 5  Razonamiento   LLM redacta la nota sobre hechos ya establecidos
Fase 6  Presentación   Dictamen + checks + traza completa auditable
```

**La aritmética la hace Python, nunca el modelo.** El delta entre lo facturado y lo
autorizado se calcula en código; al LLM solo se le pide prosa. Los modelos pequeños
fallan en aritmética y no hay razón para delegársela.

### Verificado por código

El dashboard muestra una fila `verificado por código` separada de la nota que
redactó el modelo. Todo lo que aparece ahí sale de
[`backend/core/checks.py`](backend/core/checks.py), que **no toca el LLM en ningún
momento**:

| Check | Qué compara |
|---|---|
| `suma de líneas` | Que las líneas sumen el total declarado (coherencia interna del documento) |
| `impuestos` | Que subtotal + IVA dé el total, y que el IVA sea el 13% |
| `cantidad vs OC` | Cantidad de cada línea contra la línea equivalente de la orden |
| `precio unit. vs OC` | Precio unitario línea a línea |
| `total vs OC` | El delta entre lo facturado y lo autorizado |
| `estado de la OC` | Falla si la orden figura cancelada |

`SKIPPED` es un estado de primera clase: si el modelo no logró leer las líneas, el
check se declara no evaluable en vez de inventar un resultado. **Un `SKIPPED` nunca
auto-aprueba** — no verificar no es lo mismo que verificar con éxito.

Las líneas se emparejan por descripción normalizada (sin acentos, espacios
colapsados) con fallback a coincidencia aproximada, para que el ruido de OCR no
cuente como discrepancia real.

### Política de auto-aprobación

Vive en código, no en el modelo: se auto-aprueba solo si el veredicto es `MATCH`
**y** ningún check quedó en `WARN`/`FAIL`. Una factura puede coincidir en el total
y aun así quedar a revisar — por ejemplo, si cobra contra una orden cancelada, o si
sus líneas no suman lo que declara.

### Los cuatro veredictos

| Veredicto | Cuándo |
|---|---|
| `MATCH` | Los montos coinciden (tolerancia de 1 centavo) y la orden está vigente |
| `MISMATCH` | Hay diferencia de monto, o se cobra contra una orden cancelada |
| `NO_PO_FOUND` | No existe orden de compra para ese NIT — **no se llama al modelo**, porque pedirle una opinión sin datos es invitarlo a confabular |
| `UNCERTAIN` | El documento no se pudo leer de forma confiable. El agente dice "no sé" en vez de inventar un número |

`UNCERTAIN` y `NO_PO_FOUND` son la parte que importa: un agente que marca incertidumbre
vale más que uno que alucina un número con confianza.

---

## Ingeniería de fiabilidad

Los modelos de 1–4B fallan de formas reconocibles. El sistema las trata como casos
esperados, no como excepciones:

**1. Capa de rescate antes de gastar un reintento.**
Los modelos pequeños envuelven el JSON en bloques de código o lo rodean de prosa aunque
se les prohíba explícitamente. Eso es ruido de formato, no un error de contenido:
[`_salvage_json`](backend/core/orchestrator.py) lo limpia en vez de castigarlo con un
reintento.

**2. Self-correction loop con feedback específico.**
Si la validación falla igual, el error concreto se reinyecta en el prompt del reintento
— el modelo recibe *qué* estuvo mal, no solo la orden de reintentar. Agotados los
intentos, el resultado es `UNCERTAIN`; nunca se completa a mano lo que faltó.

**3. Validación estricta.** `ExtractedInvoice` usa `extra="forbid"`: si el modelo
alucina un campo que no pedimos, la validación falla y se dispara el reintento, en vez
de que el dato basura entre silenciosamente al pipeline.

**4. Decimal de punta a punta.** Ningún importe toca un `float`. Comparar plata con
floats produce falsos mismatches por redondeo.

**5. Fallback en el razonamiento.** Si el modelo devuelve una nota vacía, hay un texto
de respaldo generado en código y el hecho queda registrado en la traza.

**6. El modelo redacta, no deduce.** Los checks y el delta entran al prompt de triaje
como hechos ya establecidos, con instrucción explícita de no recalcularlos.

Los modos de fallo están reproducidos en
[`FlakyLLMClient`](backend/core/llm/stub.py) — JSON truncado, campo alucinado, respuesta
en prosa, monto en palabras, el esquema devuelto en lugar de los datos — y es contra eso
que se prueba el retry loop.

---

## Cómo levantar el proyecto

Requiere **Python 3.12+**, **Node** y **Docker**. Solo la base de datos está
containerizada; el backend y el dashboard corren nativos, cada uno en su propia
terminal.

### 1. Dependencias

```bash
npm install                                       # runtime Bare + @qvac/sdk

python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
```

`npm install` no es opcional: el worker de OCR arranca el runtime **Bare** desde
`node_modules`, y las rutas a ese runtime son dos de las variables del `.env`.

### 2. Configuración

```bash
cp .env.example .env                              # Windows: copy .env.example .env
```

Hay que editar tres valores a mano; el resto funciona con los defaults:

| Variable | Qué poner |
|---|---|
| `QVAC_SDK_DIR` | Ruta **absoluta** a `node_modules/@qvac/sdk` |
| `QVAC_BARE_PATH` | Ruta **absoluta** al ejecutable `bare` de `node_modules` |
| `QVAC_MODEL_OCR` | ID del modelo OCR en el registry de QVAC, o ruta a los pesos |

Mientras `QVAC_MODEL_OCR` siga en `PENDIENTE`, el motor de OCR devuelve ese
estado en `quality_flags` en vez de fallar en silencio. El resto del pipeline
funciona igual con los clientes de prueba (ver el selector de motor más abajo).

### 3. Base de datos

```bash
docker compose up -d
```

Levanta MariaDB 11 en el puerto **3307** y carga `db/schema.sql` y `db/seed.sql`
automáticamente. Comprobá que quedó sana antes de seguir:

```bash
docker compose ps                                 # STATUS debe decir (healthy)
```

### 4. Backend — terminal 1

```bash
.venv/Scripts/python -m uvicorn backend.api.main:app --port 8123 --reload
```

Verificá que responde y que alcanza la base:

```bash
curl localhost:8123/health
# {"status":"ok","db":"connected","llm_client":"stub","test_clients":["stub","flaky"]}
```

Si `db` dice `unreachable`, el backend está bien pero el contenedor no —
volvé al paso 3.

### 5. Dashboard — terminal 2

```bash
.venv/Scripts/python -m streamlit run frontend/app.py
```

Queda en **`localhost:8501`**. Ya podés subir una factura.

### 6. Tests (opcional)

```bash
.venv/Scripts/python -m pytest -q                 # 78 tests
```

Los de DB y API se saltan solos si MariaDB no está levantada, así que el resto
de la suite corre igual sin Docker.

> Los tests escriben en la misma base que la demo. Si vas a grabar, corré
> `docker compose down -v && docker compose up -d` para arrancar con la base
> recién sembrada.

### Notas de entorno

- La DB expone el **3307** para no chocar con una instalación local de
  MySQL/MariaDB en 3306.
- El backend usa el **8123** porque en Windows el 8000 suele caer en un rango
  reservado (`WinError 10013`).
- Si cambiás `db/schema.sql`, hace falta `docker compose down -v` antes de
  `up -d`: los scripts de init solo corren sobre un volumen vacío.
- Docker Compose deriva el nombre del proyecto del **nombre de la carpeta**. Si
  levantaste el contenedor desde otra ruta, `docker compose ps` acá no lo va a
  ver y `up -d` va a chocar en el 3307. Se resuelve con
  `docker rm -f concilia-db` y volver a levantar.

### Probarlo

```bash
printf 'imagen' > factura_oriente.jpg
curl -F "file=@factura_oriente.jpg" localhost:8123/reconcile
```

El stub elige su respuesta según el nombre del archivo, para que la demo sea
reproducible. Nombres reconocidos: `oriente` (24 cajas contra 20 autorizadas),
`match`, `descuadre`, `grande`, `extra`, `iva`, `cancelada`, `subcobro`,
`desconocido`, `ilegible`.

Para ver el retry loop en acción, levantar con `LLM_CLIENT=flaky` — el cliente falla las
dos primeras llamadas y el agente se recupera igual.

### Selector de motor en el dashboard (provisional)

Mientras QVAC no esté integrado, la barra lateral del dashboard trae un **selector de
motor de inferencia**: permite alternar entre `stub` y `flaky` por request, sin editar el
`.env` ni reiniciar nada. Cambiar el motor y volver a subir el mismo documento lo
reprocesa, que es la forma de comparar los dos comportamientos sobre la misma factura.

Solo la respuesta del modelo está simulada. El resto del pipeline —extracción validada,
consulta al ERP, las verificaciones deterministas, los reintentos, el veredicto y la
traza— corre de verdad.

**El switch es código temporal y sale entero cuando `QvacLLMClient` esté listo.** Los
cuatro puntos a borrar están listados en el comentario de cabecera de
[`_selector_de_motor`](frontend/app.py), y los tests que lo cubren viven aislados en
`backend/tests/test_llm_switch.py` y `frontend/tests/test_app_switch.py`.

> Los tests de `test_api.py` escriben en la misma base que la demo. Para dejarla
> limpia antes de grabar: `TRUNCATE reconciliations; TRUNCATE invoices;`

### Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/health` | Estado del backend y de la DB |
| `POST` | `/reconcile` | Sube una factura → dictamen + traza |
| `GET` | `/purchase-orders` | Órdenes de compra del ERP |
| `GET` | `/stats` | Contadores del dashboard |
| `GET` | `/reconciliations` | Historial de dictámenes |
| `GET` | `/reconciliations/{id}` | Detalle: factura, OC, checks, nota, traza |
| `GET` | `/reconciliations/{id}/document` | El documento original, como evidencia |
| `POST` | `/reconciliations/{id}/decision` | Aprobar o escalar a compras |

---

## Estructura

```
backend/
  core/                    Lógica pura — no importa nada de HTTP
    orchestrator.py        Las fases, retry loop y traza
    checks.py              Verificación determinista — no toca el LLM
    schemas.py             Contratos Pydantic entre fases
    llm/
      base.py              LLMClient (ABC) — el punto de enganche de QVAC
      stub.py              Stubs deterministas + inyector de fallos
      prompts.py           Plantillas de extracción y triaje
    tools/db_tool.py       La herramienta del agente: consultar el ERP
  db/
    session.py             Engine SQLAlchemy
    repository.py          Persistencia de la traza y la decisión humana
  api/                     Capa fina FastAPI
  tests/
frontend/
  app.py                   Layout y navegación
  api_client.py            Única capa que habla HTTP con el backend
  view_model.py            Adapta las respuestas del backend a la tarjeta
  components/
    invoice_card.py        La tarjeta de comparación
    checks_row.py          "verificado por código"
    trace_view.py          La traza del agente, colapsable
db/
  schema.sql               ERP simulado + tablas de auditoría
  seed.sql                 9 órdenes que ejercitan los veredictos y los checks
storage/documents/         Documentos originales (fuera de git)
```

`core/` no importa nada de `api/`. La interfaz `LLMClient` devuelve **texto crudo** a
propósito: el parseo y la validación son responsabilidad del orquestador, que es donde
vive la fiabilidad. Si la interfaz devolviera objetos ya validados estaríamos
escondiendo el problema que la Pista 2 pide resolver.

El frontend **no reimplementa ninguna lógica de negocio**: qué valores se pintan en
rojo sale de los checks del backend, y el estado auto-aprobada/a revisar lo decide la
política en código. `view_model.py` solo traduce veredictos a banderas de color.

---

## Verificación

78 tests, todos en verde. Los del orquestador, los checks y el view model corren sin
Docker; los de DB y API se saltan solos si MariaDB no está levantada.

Verificado end-to-end con los diez casos de fixture: los cuatro veredictos se producen
correctamente, la traza registra las fases que corresponden a cada camino (5 pasos en el
flujo completo, 3 cuando no hay OC, 2 cuando el documento es ilegible), y todo queda
persistido en `reconciliations` con su JSON de checks y de traza.

El caso del mockup (`F-00842` · Distribuidora del Oriente) reproduce exactamente:
`MISMATCH`, delta `Bs 340,00`, `cantidad vs OC` en `WARN`, y la nota *"Se facturaron 4
unidades de más. Diferencia de Bs 340,00 a favor del proveedor."*

Con `LLM_CLIENT=flaky` el agente absorbe dos respuestas rotas y termina en `MATCH` con
`retries: 2` registrado en la traza.

El dashboard se verifica con `AppTest` de Streamlit además de a ojo — así se detectó,
por ejemplo, que envolver la tarjeta en un expander rompía la app por anidamiento.

---

## Lo que falta

- **Fase 3 — QVAC.** Implementar `QvacLLMClient(LLMClient)` con OCR y comprensión
  multimodal del SDK. El orquestador no cambia, y el frontend tampoco: consume la misma
  API sin importar qué cliente LLM haya detrás.
- **Entradas reales desordenadas.** Fotos con mala iluminación y arrugas — el track
  premia robustez sobre entradas que no elegiste de antemano, no un PDF limpio.
- **Medición de fiabilidad.** Correr la misma tarea N veces contra el modelo real y
  reportar la tasa de éxito, incluidos los fallos que no se pudieron arreglar.
