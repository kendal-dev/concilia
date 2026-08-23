<#
    Levanta CONCILIA completo desde una sola terminal.

        .\scripts\run_demo.ps1                 # arranque normal, con precalentamiento
        .\scripts\run_demo.ps1 -SinCalentar    # no carga los modelos de entrada
        .\scripts\run_demo.ps1 -Bajar          # apaga backend y frontend

    Por que existe: la primera peticion al backend carga detector, reconocedor y
    modelo de texto (~78 s medidos en este equipo). Si eso ocurre cuando el usuario
    sube su primer documento, la demo parece rota. Aca se paga durante el arranque:
    apenas /health responde, el script manda un recibo de calentamiento por su
    cuenta, y para cuando abris la UI los modelos ya estan en memoria.

    Cuidado con el lock: el registry de QVAC toma un lock de archivo, asi que solo
    puede haber UN proceso QVAC vivo. uvicorn se levanta SIN --reload a proposito
    (con reload son dos procesos y el segundo choca). Mientras esto corre, no
    lances eval/runner.py ni ocr/engine.py.
#>
param(
    [switch]$SinCalentar,
    [switch]$Bajar,
    [string]$Recibo = "data\receipts\R002.jpg"
)

$ErrorActionPreference = "Stop"
$RAIZ = Split-Path $PSScriptRoot -Parent
$BASE = "http://127.0.0.1:8123"
$PUERTO_UI = 8501

function Nota($m)  { Write-Host "  $m" -ForegroundColor DarkCyan }
function Bien($m)  { Write-Host "  $m" -ForegroundColor Green }
function Aviso($m) { Write-Host "  $m" -ForegroundColor Yellow }

function Matar-Puerto($puerto) {
    $cons = Get-NetTCPConnection -LocalPort $puerto -State Listen -ErrorAction SilentlyContinue
    if (-not $cons) { Nota "puerto $puerto ya estaba libre"; return }
    foreach ($c in $cons) {
        try {
            Stop-Process -Id $c.OwningProcess -Force -ErrorAction Stop
            Bien "puerto $puerto liberado (pid $($c.OwningProcess))"
        } catch { Aviso "no pude matar el pid $($c.OwningProcess) en :$puerto" }
    }
}

if ($Bajar) {
    Write-Host "`nBajando CONCILIA" -ForegroundColor White
    Matar-Puerto 8123
    Matar-Puerto $PUERTO_UI
    Nota "la base queda arriba (docker compose down para apagarla tambien)"
    exit 0
}

Set-Location $RAIZ
$env:PYTHONPATH = $RAIZ

$py = Join-Path $RAIZ ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "No encuentro el venv en $py" }

Write-Host "`nCONCILIA - arranque completo" -ForegroundColor White
Write-Host "raiz: $RAIZ`n"

# ---------------------------------------------------------- 1. base de datos
Write-Host "[1/5] base de datos" -ForegroundColor White
docker compose up -d | Out-Null
$sano = $false
foreach ($i in 1..30) {
    if ((docker compose ps 2>&1 | Out-String) -match "healthy") { $sano = $true; break }
    Start-Sleep -Seconds 2
}
if ($sano) { Bien "MariaDB healthy en :3307" }
else { Aviso "MariaDB no reporto healthy en 60 s; revisa 'docker compose ps'" }

# --------------------------------------------------------------- 2. backend
Write-Host "`n[2/5] backend" -ForegroundColor White
if (Get-NetTCPConnection -LocalPort 8123 -State Listen -ErrorAction SilentlyContinue) {
    Aviso "ya hay algo escuchando en :8123; no levanto otro (usa -Bajar si quedo colgado)"
} else {
    $cmd = "`$env:PYTHONPATH='$RAIZ'; Set-Location '$RAIZ'; " +
           "& '$py' -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8123"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd | Out-Null
    Nota "uvicorn en su propia ventana: dejala visible, es la prueba de inferencia local"
}

# -------------------------------------------------------- 3. esperar /health
Write-Host "`n[3/5] esperando al backend" -ForegroundColor White
$salud = $null
foreach ($i in 1..40) {
    try { $salud = Invoke-RestMethod "$BASE/health" -TimeoutSec 3; break }
    catch { Start-Sleep -Seconds 2 }
}
if (-not $salud) { throw "El backend no respondio /health en 80 s. Mira la ventana de uvicorn." }
Bien "health: db=$($salud.db)  motor=$($salud.llm_client)"
if ($salud.llm_client -ne "qvac") {
    Aviso "OJO: el motor es '$($salud.llm_client)', no 'qvac'. Revisa LLM_CLIENT en .env"
}

# ----------------------------------------------------- 4. precalentar modelos
Write-Host "`n[4/5] precalentamiento" -ForegroundColor White
if ($SinCalentar) {
    Nota "omitido por -SinCalentar: la primera subida va a tardar ~78 s"
} elseif (-not (Test-Path $Recibo)) {
    Aviso "no encuentro $Recibo; omito el precalentamiento"
} else {
    # La ruta conocida es /reconcile. Se confirma contra el contrato OpenAPI en vez
    # de confiar en ella a ciegas, y si el backend la renombro se busca la que
    # reciba un archivo. Descubrir primero y usar /reconcile de respaldo era al
    # reves: cualquier tropiezo del parseo imprimia un aviso en amarillo sobre un
    # arranque que en realidad iba bien.
    $ruta = "/reconcile"; $campo = "file"
    try {
        $spec = Invoke-RestMethod "$BASE/openapi.json" -TimeoutSec 10
        $candidatas = @()
        foreach ($p in $spec.paths.PSObject.Properties) {
            $post = $p.Value.post
            if (-not $post -or -not $post.requestBody) { continue }
            $tipos = $post.requestBody.content.PSObject.Properties.Name
            if ($tipos -notcontains "multipart/form-data") { continue }
            $esquema = $post.requestBody.content."multipart/form-data".schema
            if ($esquema.'$ref') {
                $nombre = ($esquema.'$ref' -split "/")[-1]
                $esquema = $spec.components.schemas.$nombre
            }
            $bin = $esquema.properties.PSObject.Properties |
                   Where-Object { $_.Value.format -eq "binary" } | Select-Object -First 1
            if ($bin) { $candidatas += [pscustomobject]@{ Ruta = $p.Name; Campo = $bin.Name } }
        }
        $elegida = $candidatas | Where-Object { $_.Ruta -eq $ruta } | Select-Object -First 1
        if (-not $elegida) { $elegida = $candidatas | Select-Object -First 1 }
        if ($elegida) {
            if ($elegida.Ruta -ne $ruta) { Aviso "el endpoint se llama $($elegida.Ruta), no $ruta" }
            $ruta = $elegida.Ruta; $campo = $elegida.Campo
        } else {
            Nota "el contrato no declaro ninguna subida; uso $ruta / '$campo'"
        }
    } catch { Nota "no pude leer /openapi.json; uso $ruta / '$campo'" }

    Nota "POST $ruta (campo '$campo') con $Recibo"
    Nota "la primera vez tarda ~78 s: es la carga de los tres modelos"
    $t0 = Get-Date
    $codigo = & curl.exe -s -o NUL -w "%{http_code}" -X POST "$BASE$ruta" -F "$campo=@$Recibo" --max-time 300
    $seg = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    if ($codigo -eq "200") { Bien "modelos cargados ($seg s). La proxima subida va a ~15 s." }
    else { Aviso "el calentamiento devolvio HTTP $codigo tras $seg s; mira la ventana de uvicorn" }
}

# -------------------------------------------------------------- 5. frontend
Write-Host "`n[5/5] frontend" -ForegroundColor White
if (Get-NetTCPConnection -LocalPort $PUERTO_UI -State Listen -ErrorAction SilentlyContinue) {
    Aviso "ya hay algo en :$PUERTO_UI; no levanto otro"
} else {
    $cmd = "`$env:PYTHONPATH='$RAIZ'; Set-Location '$RAIZ'; " +
           "& '$py' -m streamlit run frontend/app.py --server.port $PUERTO_UI"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd | Out-Null
    Start-Sleep -Seconds 6
    Bien "Streamlit en http://localhost:$PUERTO_UI"
}

Start-Process "http://localhost:$PUERTO_UI"

Write-Host "`nListo." -ForegroundColor White
Write-Host "  backend   $BASE/docs"
Write-Host "  frontend  http://localhost:$PUERTO_UI"
Write-Host "  apagar    .\scripts\run_demo.ps1 -Bajar`n"
