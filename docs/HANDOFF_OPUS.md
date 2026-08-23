# HANDOFF — CONCILIA · Aleph Hackathon · QVAC Track 1
## Informe de estado + instrucciones para continuar la sesión

> **Para el asistente que recibe esto (Opus):** este documento es la fuente de verdad
> del proyecto al momento del traspaso (sábado 22-ago-2026, ~H+7 de hackathon).
> Tienes acceso a la carpeta `C:\concilia` vía Cowork (device "aiso", carpeta conectada).
> **Antes de asumir nada, relee los archivos reales del disco** — pueden haber cambiado
> desde este handoff. Daniel es el usuario; su rol en el equipo: IA + Base de datos.

---

## 1. CONTEXTO FIJO (no renegociar)

- **Evento:** Aleph Hackathon, Chapter Santa Cruz, Bolivia. Arrancó sábado 11:30 AM.
- **Deadline duro:** domingo 11:00 (UTC-4). **Freeze 07:00. Submit 09:00.**
- **Track:** QVAC Track 1 ($1,000 USDt) + General Track ($500, se apila).
- **Proyecto:** CONCILIA — agente local de conciliación de facturas bolivianas.
  Foto de recibo sucio → OCR local → JSON estructurado → cruce contra libro de
  gastos en MariaDB → veredicto MATCH/MISMATCH/NO_MATCH/UNCERTAIN con explicación.
- **Criterios del track (textuales):** (1) funciona con inputs sucios reales,
  (2) razonamiento auditable (`source_span`), (3) honesto sobre lo que no puede
  (`UNCERTAIN` es la feature ganadora, no un fallo).
- **Prohibido por el brief:** VisionPsy (no soportado), generación de imagen/video,
  métodos del SDK inventados (auditoría anti-slop del jurado descarta el proyecto).

## 2. DECISIONES CONGELADAS

1. **Stack:** Python 3.14 + MariaDB 11 (Docker, puerto **3307**) + PyMySQL + rich.
   **Sin frontend** — terminal `rich` es la UI. (Se evaluó y descartó C#/ASP.NET/SQL Server.)
2. **Pipeline de DOS etapas:** Etapa 1 = OCR nativo del SDK (imagen→texto crudo).
   Etapa 2 = modelo de texto (texto→JSON con vendor/date/total/source_span/confidence).
   El texto OCR intermedio ES el razonamiento auditable. No colapsar en una llamada.
3. **Ruta de inferencia:** SDK **nativo** de Python (`tetherto.qvac_sdk`), NO el
   servidor REST (`qvac serve openai` rechazó modelos: la ruta REST quedó descartada
   para OCR; puede servir para Etapa 2 solo si el nativo la soporta más fácil).
4. **El modelo jamás genera SQL.** Consultas parametrizadas en `reconcile/repository.py`.
5. **Dataset = 30 recibos:** 14 MATCH + 8 MISMATCH + 5 NO_MATCH + 3 manuscritos
   (UNCERTAIN esperado). Mapeo en `eval/dataset_map.md` (aún no existe). Seed ≈ 40
   registros (14 pares exactos + 8 alterados + 2 pares de manuscritos + 2 duplicados
   + ~14 ruido).

## 3. EQUIPO Y REPARTO

| Quién | Rol | Estado |
|---|---|---|
| Daniel (Zephyrus G16, RTX 4070 8GB, 16GB RAM, Win11) | IA + DB | activo, esta sesión |
| Backend (C#-ista, hace Python aquí) | MariaDB + motor de cruce | debía clonar repo y levantar Docker en SU máquina — VERIFICAR |
| Junior adaptable | Confianza + evaluación | sin noticias |
| Super Junior | **30 recibos + ground truth** | ⚠️ SIN RECIBOS a H+7 — riesgo #1 del proyecto |

## 4. ESTADO VERIFICADO DEL ENTORNO (hechos, no suposiciones)

- Vulkan 1.4.321 OK; RTX 4070 = GPU0 discreta. Node v24.19.0. Python 3.14.5.
- `qvac doctor`: pass. CLI `@qvac/cli` instalado. **El CLI NO tiene `qvac models`** —
  comandos reales: `bundle, doctor, verify, openai, serve`.
- `qvac serve openai` (puerto 11434) levanta pero **sin modelos** ("No models
  configured for preload"); rechazó VisionPsy con `model_not_found`. No usar esta ruta.
- SDK Python: `tetherto-qvac-sdk==0.17.1`, se importa como `import tetherto.qvac_sdk`.
- **Worker resuelto:** `npm install @qvac/sdk@0.17.1` en la raíz del proyecto +
  variables en `.env`: `QVAC_SDK_DIR=C:\concilia\node_modules\@qvac\sdk` y
  `QVAC_BARE_PATH=C:\concilia\node_modules\bare-runtime-win32-x64\bin\bare.exe`.
- **Patrón de conexión que funciona:** `client = q.Client(sdk_dir=..., bare_path=...)`,
  luego `async with client:` y pasar `client.transport` a las funciones globales.
- **Firma REAL verificada por `help()`:** `OcrStreamRequest(*, modelId: str,
  image: OcrStreamRequestImageBase64 | OcrStreamRequestImageFilePath,
  options: ... | None, type: Literal['ocrStream'])`. — nótese **camelCase `modelId`**.
- El SDK expone (dir() verificado): `Client, load_model, ocr_stream, completion,
  completion_stream, model_registry_list, model_registry_search, download_asset,
  get_model_info, ModelType, LoadModelRequest, OcrStreamRequest/Response`, etc.
- Repo GitHub: `https://github.com/kendal-dev/concilia` — PÚBLICO, rama main,
  limpio de node_modules (purgado con --amend).
- Docker Desktop en la Zephyrus: descarga eterna, NO instalado aún. El plan es que
  Backend levante la DB en su máquina con el compose del repo.
- Descargándose al momento del handoff: `Qwen3.5-4B-Q4_K_M.gguf` (2.6 GB, iba ~226 MB).

## 5. CORRECCIONES YA APLICADAS AL DISCO (esta sesión, vía Cowork)

1. `docker-compose.yml` → v2: monta `00-schema.sql` + `01-seed.sql`, `container_name:
   concilia-db`, healthcheck. (La versión anterior NO montaba el schema → DB sin tablas.)
2. `requirements.txt` → reescrito en UTF-8 (estaba corrupto en UTF-16 por PowerShell:
   `pip install -r` fallaba en clone limpio). 27 paquetes pineados.
3. `.gitignore` → agrega `*.gguf`, `dummy.jpg`, `logs/` (evita subir 2.6GB a GitHub).
4. `.env.example` → creado (no existía; el setup del juez lo requiere).
5. `docs/environment/probe.py` → script de introspección definitivo del SDK.

**Daniel debía ejecutar tras esto (VERIFICAR con `git log` si lo hizo):**
`git rm --cached dummy.jpg` · `git rm qvac.config.json` (config inventado por Gemini,
formato ignorado por el servidor, referencia VisionPsy prohibido) · commit · push ·
avisar a Backend que haga `git pull` y `docker compose down -v && up -d`.

## 6. BUGS CONOCIDOS PENDIENTES (en orden de prioridad)

### 6.1 ⛔ `ocr/engine.py` tiene campos ADIVINADOS — fallará al correr
El código actual (dictado por Gemini) usa: `model_id=` (la firma real es `modelId=`),
`image={"path": ...}` (claves no verificadas — las clases reales son
`OcrStreamRequestImageBase64` / `OcrStreamRequestImageFilePath` con campos aún
desconocidos), `q.load_model(transport, model_name=..., model_type="ggml_ocr")`
(kwargs no verificados; "ggml_ocr" fue RECHAZADO por pydantic según el propio reporte),
y parsea chunks con `chunk.blocks[].text` (estructura inventada).
**Regla: NO depurar a ciegas. Ejecutar `python docs\environment\probe.py` y usar SU
output para reescribir engine.py con las firmas reales.** El probe imprime: valores
de ModelType, model_fields de LoadModelRequest/OcrStreamRequest/OcrStreamResponse y
variantes de image, firmas de las funciones, y la lista del registry de modelos.

### 6.2 ⛔ El modelo descargado NO sirve para OCR
`Qwen3.5-4B-Q4_K_M.gguf` es TEXTO puro (un GGUF multimodal requiere mmproj aparte).
No puede ver imágenes. **Destino correcto: Etapa 2** (extracción texto→JSON vía
`completion`/`completion_stream` del SDK). Para la Etapa 1, el modelo OCR real sale
del **registry del SDK** (`model_registry_list/search` + `download_asset`) — el output
del probe dice cuál es y cómo descargarlo. Ese ID va en `.env` → `QVAC_MODEL_OCR`.

### 6.3 ⛔ Dataset en CERO
`data/receipts/` vacío, `db/seed.sql` 0 bytes, sin `eval/ground_truth.json` ni
`eval/dataset_map.md`. Sin esto no hay evaluación ni premio. Plan B si el Super Junior
no aparece: los 4 vacían billeteras/mochilas + 2 almacenes cercanos → 15-20 recibos
propios bastan para arrancar (el roadmap contempla recortar a 15 manteniendo
proporciones 7/4/2/2).

### 6.4 Módulos sin escribir (esqueleto vacío)
`extract/` (prompts, parser, structurer), `reconcile/` (matcher, rules, repository),
`confidence/` (scorer, detectors — detector de source_span con matching NORMALIZADO,
no substring literal), `report/terminal.py`, `eval/runner.py`, `db/connection.py`
(UNA conexión PyMySQL con retry/backoff — SIN pool), `main.py`, `README.md`, `LICENSE`.
El roadmap v2 completo (54 pasos) está en la conversación previa de Claude; los
diseños clave se resumen en §8.

## 7. REGLAS DE TRABAJO PARA EL ASISTENTE

1. **Anti-slop es sagrado:** ninguna llamada al SDK sin firma verificada por
   introspección o output real de la terminal de Daniel. El jurado descarta proyectos
   con métodos inventados.
2. **Los reportes de Gemini/"Aiso" contienen alucinaciones** — esta sesión encontró
   4 graves (compose roto dictado, engine.py con imagen-como-texto, qvac.config
   inventado, VisionPsy pese al brief). Auditar todo lo que venga de esa fuente
   contra el disco y contra outputs reales.
3. Daniel copia/pega comandos en PowerShell y edita con notepad — dar comandos
   exactos y archivos completos, no diffs. Mejor aún: escribir archivos directo a
   `C:\concilia` vía device_commit_files (staging primero para respetar mtime).
4. PowerShell: `>` escribe UTF-16 — usar `| Out-File -Encoding ascii/utf8` o
   escribir los archivos desde Cowork.
5. Código Python NUNCA pegado en la terminal (ya pasó): va en archivos.
6. Prioridad permanente: recibos > OCR funcionando > seed alineado > etapa 2 >
   conciliación > confianza > terminal > evidencia. Video y README tienen hora
   reservada (madrugada). Dos horas de colchón antes del deadline: intocables.

## 8. DISEÑOS CLAVE YA DEFINIDOS (resumen del roadmap v2)

- **Contrato JSON por recibo:** `{receipt_id, source_image, ocr:{raw_text, engine,
  route, duration_s, quality_flags}, extracted:{vendor/date/total/currency/items —
  cada uno con value+confidence+source_span, parser_repairs}, reconciliation:
  {matched_record_id, match_strategy, verdict, delta, explanation,
  human_review_required}, confidence_overall, latency_s}`.
- **Cascada de matching:** exacto(1.0) → fuzzy proveedor difflib≥0.75(0.85) →
  fecha±3d+monto(0.70) → monto solo(0.50) → NO_MATCH. Normalización compartida
  (lower, sin tildes via unicodedata, espacios colapsados) para seed Y OCR.
- **Explicaciones por REGLA** (no por modelo): transposición de dígitos (multiset),
  ~13% IVA, decimal corrido (~10x), duplicado, sin par, genérica de respaldo.
- **Detector source_span:** contención sobre texto normalizado + ventana deslizante
  SequenceMatcher ≥0.90 (NUNCA substring literal — falsos negativos por whitespace).
- **Detector aritmético:** Σ(qty×unit_price) vs total, tolerancia 1 Bs; no aplica
  si el recibo no tiene ítems (no penalizar).
- **Scorer con vetos:** span inventado en `total` → techo 0.4. Ruta multimodal →
  techo 0.7. `confidence_overall < 0.6` (de .env) → UNCERTAIN forzado.
- **Prompt Etapa 2:** rol + schema exacto con ejemplo + instrucción de incertidumbre
  ("nunca adivines, null y confidence 0.0") + trazabilidad ("source_span = cita
  LITERAL del OCR, sin corregir errores") + contexto BOB/Bs/DD-MM-YYYY/NIT.
- **README final:** permalinks con hash de commit a engine.py/structurer.py/prompts.py
  + detectors.py; setup desde clone limpio INCLUYENDO npm install del worker y la
  descarga del modelo OCR con su ID exacto; tabla de hardware/latencias.

## 9. SECUENCIA INMEDIATA AL RETOMAR (en orden)

1. **Releer el disco:** listar `C:\concilia`, ver `git log --oneline`, confirmar si
   los fixes de §5 fueron commiteados/pusheados y si `qvac.config.json`/`dummy.jpg`
   salieron del repo.
2. **Correr `python docs\environment\probe.py`** (venv activo) y capturar output.
3. Con ese output: **reescribir `ocr/engine.py`** con firmas reales; identificar el
   modelo OCR del registry; descargarlo (`download_asset` o el mecanismo que muestre
   el probe); poner su ID en `.env` → `QVAC_MODEL_OCR`.
4. **Primera inferencia real**: `python ocr\engine.py dummy.jpg` y luego sobre una
   foto de recibo real. Anotar latencia en `docs/environment/baseline.md`.
5. **Estado del equipo:** ¿Backend levantó MariaDB con el compose v2? (`SHOW TABLES;`
   → 3 tablas). ¿Recibos? Si no hay a esta altura → activar plan B (§6.3) SIN esperar.
6. **Etapa 2:** `extract/prompts.py` + `parser.py` + `structurer.py` usando
   `completion` del SDK con el Qwen GGUF ya descargado (verificar por introspección
   cómo cargar un GGUF local: LoadModelRequest model_fields lo dirá).
7. Seguir el orden de fases del roadmap v2: seed alineado al ground truth →
   matcher/rules con fixtures → confianza → terminal rich → corrida de 30 →
   RESULTS.md + limitations.md → clone limpio → freeze 07:00 → README/permalinks/
   video → submit 09:00.

## 10. INVENTARIO DE ARCHIVOS AL MOMENTO DEL HANDOFF

```
C:\concilia\
  .env                  (local, NO en git; worker paths OK; QVAC_MODEL_OCR=PENDIENTE)
  .env.example          ✅ nuevo (esta sesión)
  .gitignore            ✅ actualizado (esta sesión)
  docker-compose.yml    ✅ v2 corregido (esta sesión)
  requirements.txt      ✅ UTF-8 corregido (esta sesión)
  qvac.config.json      ⛔ borrar del repo (git rm) si no se hizo
  dummy.jpg             ⛔ sacar del repo (git rm --cached) si no se hizo
  buscar_modelo.py      (borrador de registry; superado por docs/environment/probe.py)
  package.json / lock   ✅ mantener (documentan el worker @qvac/sdk para el juez)
  db/schema.sql         ✅ correcto (3 tablas, utf8mb4, DECIMAL, JSON)
  db/seed.sql           ⛔ 0 bytes — llenar con mapeo 14/8/5(+2 dup+ruido)
  ocr/engine.py         ⛔ campos adivinados — reescribir tras probe (§6.1)
  docs/environment/introspect.py  (versión vieja; usar probe.py)
  docs/environment/probe.py       ✅ ejecutar PRIMERO
  extract/ reconcile/ confidence/ report/ eval/ data/receipts/  → VACÍOS
```

---

*Handoff generado por la sesión Claude (Cowork) del sábado ~18:00. Suerte — el
proyecto es ganable: la arquitectura es sólida, el entorno está blindado, y las dos
incógnitas restantes (modelo OCR real + recibos físicos) tienen ruta clara.*
