"""Preflight CONCILIA - verifica que el entorno esta listo ANTES de tocar el SDK.

Uso:  python docs\\environment\\preflight.py
No carga modelos ni hace inferencia: solo comprueba. Codigo de salida 1 si hay [FAIL].
"""
import os
import sys
import glob
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = {"OK": 0, "WARN": 0, "FAIL": 0}


def mark(status, name, detail=""):
    RES[status] += 1
    print(f"[{status:4}] {name}" + (f"  ->  {detail}" if detail else ""))


def head(t):
    print("\n" + t)
    print("-" * len(t))


def run(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=25)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


head("1. PYTHON")
v = sys.version_info
mark("OK" if v >= (3, 12) else "FAIL", f"Python {platform.python_version()}", sys.executable)
in_venv = sys.prefix != sys.base_prefix
mark("OK" if in_venv else "FAIL", "venv activo" if in_venv else "venv NO activo",
     "" if in_venv else "corre .venv\\Scripts\\Activate.ps1")

head("2. PAQUETES PYTHON")
try:
    from importlib.metadata import version as _pkgver
except Exception:
    def _pkgver(n):
        return "?"
for mod, pkg in [("tetherto.qvac_sdk", "tetherto-qvac-sdk"), ("pymysql", "pymysql"),
                 ("dotenv", "python-dotenv"), ("rich", "rich"),
                 ("PIL", "pillow"), ("numpy", "numpy")]:
    try:
        __import__(mod)
        try:
            ver = _pkgver(pkg)
        except Exception:
            ver = "?"
        mark("OK", pkg, ver)
    except Exception as e:
        mark("FAIL", pkg, f"import fallido: {type(e).__name__}: {e}")

head("3. .env")
env_path = ROOT / ".env"
if not env_path.exists():
    mark("FAIL", ".env", "no existe; copia .env.example")
else:
    mark("OK", ".env", str(env_path))
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except Exception:
        pass
    for k in ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
              "CONFIDENCE_THRESHOLD", "QVAC_SDK_DIR", "QVAC_BARE_PATH"]:
        val = os.environ.get(k)
        mark("OK" if val else "FAIL", k, val or "ausente")
    ocr_model = os.environ.get("QVAC_MODEL_OCR", "")
    mark("WARN" if ocr_model in ("", "PENDIENTE") else "OK", "QVAC_MODEL_OCR",
         ocr_model or "vacio -> lo resuelve probe.py (registry)")
    txt_model = os.environ.get("QVAC_MODEL_TEXT", "")
    mark("WARN" if not txt_model else "OK", "QVAC_MODEL_TEXT",
         txt_model or "ausente -> etapa 2 (GGUF local o registry)")

head("4. WORKER QVAC (bare + sdk js)")
for k in ["QVAC_SDK_DIR", "QVAC_BARE_PATH"]:
    p = os.environ.get(k)
    if not p:
        mark("FAIL", k, "no definido en .env")
    elif Path(p).exists():
        mark("OK", k, p)
    else:
        mark("FAIL", k, f"ruta inexistente: {p}")

head("5. SUPERFICIE DEL SDK (sin llamar a nada)")
try:
    import tetherto.qvac_sdk as q
    names = dir(q)
    for n in ["Client", "load_model", "ocr_stream", "completion", "completion_stream",
              "model_registry_list", "model_registry_search", "download_asset",
              "get_model_info", "ModelType", "LoadModelRequest", "OcrStreamRequest"]:
        mark("OK" if n in names else "FAIL", f"q.{n}")
except Exception as e:
    mark("FAIL", "import tetherto.qvac_sdk", str(e))

head("6. NODE / CLI")
for cmd, label, need in [("node --version", "node", True),
                         ("npm --version", "npm", True),
                         ("qvac --version", "@qvac/cli", False)]:
    rc, out = run(cmd)
    first = out.splitlines()[0] if out else ""
    if rc == 0:
        mark("OK", label, first)
    else:
        mark("FAIL" if need else "WARN", label, first or "no disponible")

head("7. DOCKER / MARIADB")
rc, out = run("docker --version")
if rc != 0:
    mark("WARN", "docker", "no instalado aqui (la DB la levanta Backend en su maquina)")
else:
    mark("OK", "docker", out.splitlines()[0])
    rc2, out2 = run('docker ps --filter name=concilia-db --format "{{.Names}} {{.Status}}"')
    vivo = rc2 == 0 and "concilia-db" in out2
    mark("OK" if vivo else "WARN", "contenedor concilia-db",
         out2.strip()[:120] if out2.strip() else "no corriendo (docker compose up -d)")

try:
    import pymysql
    conn = pymysql.connect(host=os.environ.get("DB_HOST", "127.0.0.1"),
                           port=int(os.environ.get("DB_PORT", "3307")),
                           user=os.environ.get("DB_USER", "concilia"),
                           password=os.environ.get("DB_PASSWORD", "concilia"),
                           database=os.environ.get("DB_NAME", "concilia"),
                           charset="utf8mb4", connect_timeout=4)
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        tablas = [r[0] for r in cur.fetchall()]
        n = 0
        if "gastos_esperados" in tablas:
            cur.execute("SELECT COUNT(*) FROM gastos_esperados")
            n = cur.fetchone()[0]
    conn.close()
    mark("OK" if len(tablas) >= 3 else "WARN", "MariaDB",
         f"tablas={tablas} gastos_esperados={n}")
except Exception as e:
    mark("WARN", "MariaDB", f"sin conexion: {type(e).__name__} (esperado si corre en otra maquina)")

head("8. MODELOS EN DISCO")
SKIP = {"node_modules", ".venv", "venv", ".git", "__pycache__"}


def buscar_gguf(base, max_depth=4):
    base = Path(base)
    found = []
    if not base.exists():
        return found
    base_depth = len(base.parts)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP and len(Path(dirpath).parts) - base_depth < max_depth]
        for f in filenames:
            if f.endswith(".gguf"):
                found.append(str(Path(dirpath) / f))
    return found


ggufs = buscar_gguf(ROOT) + buscar_gguf(Path.home() / ".qvac")
if ggufs:
    for g in ggufs:
        mark("OK", Path(g).name, f"{Path(g).stat().st_size / 1e9:.2f} GB")
else:
    mark("WARN", "modelos .gguf", "ninguno encontrado en el proyecto ni en ~/.qvac")

head("9. ESTRUCTURA DEL PROYECTO")
for rel, critico in [("db/schema.sql", True), ("db/seed.sql", True),
                     ("docker-compose.yml", True), ("requirements.txt", True),
                     (".env.example", True), ("data/receipts", True),
                     ("eval", False), ("logs/runs", False)]:
    p = ROOT / rel
    if not p.exists():
        mark("FAIL" if critico else "WARN", rel, "no existe")
    elif p.is_dir():
        n = len(list(p.iterdir()))
        mark("OK" if n else "WARN", rel + "/", f"{n} archivos")
    else:
        sz = p.stat().st_size
        mark("OK" if sz else "WARN", rel, f"{sz} bytes" + (" <- VACIO" if not sz else ""))

head("RESUMEN")
print(f"OK={RES['OK']}  WARN={RES['WARN']}  FAIL={RES['FAIL']}")
if RES["FAIL"]:
    print("\nHay [FAIL]: arreglalos antes de correr probe.py.")
    sys.exit(1)
print("\nEntorno apto. Siguiente:  python docs\\environment\\probe.py > docs\\environment\\probe_out.txt 2>&1")
