# Concilia Web

Frontend React del operador de conciliación. Sustituye la interfaz visual de
Streamlit sin modificar el backend FastAPI.

## Ejecutar en desarrollo

El backend debe estar disponible en `http://127.0.0.1:8123`.

```powershell
pnpm install
pnpm dev
```

Abrir `http://localhost:5173`.

Vite redirige las llamadas relativas `/api/*` al backend local, por lo que no
requiere cambios de CORS durante desarrollo. El cliente nunca muestra ni envía
el selector temporal de motor de inferencia.

## Verificar producción

```powershell
pnpm build
```

## Aplicación de escritorio (Tauri)

El mismo frontend se puede ejecutar como una aplicación nativa de Windows. La
API de Concilia sigue siendo local y debe estar disponible en
`http://127.0.0.1:8123` antes de abrir la app.

Primero instala Rust (incluye Cargo) desde <https://rustup.rs/> y reinicia la
terminal. Luego, dentro de esta carpeta:

```powershell
pnpm desktop:dev
```

Para generar el instalador ejecutable de Windows:

```powershell
pnpm desktop:build
```

El resultado se genera bajo `src-tauri/target/release/bundle/`. El contenedor
nativo está en `src-tauri/`; usa una ventana Concilia y no muestra datos del
modelo de IA.

## Principios de la interfaz

- Datos de montos, veredictos y checks llegan del backend; la UI solo los
  presenta, no reimplementa reglas de conciliación.
- El sello 3D usa el activo local de marca y tiene un fallback estático para
  móvil o reducción de movimiento.
- La escena Three.js se carga de forma diferida para no retrasar la interfaz
  operativa.
