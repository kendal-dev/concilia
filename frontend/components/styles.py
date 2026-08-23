"""Estilos del dashboard.

El tema base va en .streamlit/config.toml; aca solo lo que Streamlit no expone:
la tarjeta, el banner de discrepancia y los colores de los checks.
"""

import streamlit as st

CSS = """
<style>
  /* --- paleta --- */
  :root {
    --fondo:      #0d0d0d;
    --tarjeta:    #131313;
    --borde:      #2a2a2a;
    --tenue:      #8a8a8a;
    --texto:      #e8e8e8;
    --ok:         #4ade80;
    --alerta:     #f0a02a;
    --error:      #f4635e;
    --error-bg:   #3d1512;
    --error-bd:   #6b2420;
  }

  .block-container { padding-top: 2.5rem; max-width: 1150px; }
  #MainMenu, footer { visibility: hidden; }

  /* --- fila de estadisticas --- */
  .stat-label {
    color: var(--tenue); font-size: 0.95rem; margin-bottom: 0.15rem;
  }
  .stat-valor { font-size: 2.6rem; line-height: 1; font-weight: 500; }
  .stat-ok    { color: var(--ok); }
  .stat-warn  { color: var(--alerta); }

  /* --- tarjeta de factura ---
     La tarjeta llega como un unico bloque HTML, asi que este div si envuelve
     su contenido. No se estilan los contenedores de Streamlit: comparten
     testid con todos los bloques verticales de la pagina. */
  .tarjeta {
    background: var(--tarjeta);
    border: 1px solid var(--borde);
    border-radius: 12px;
    padding: 1.3rem 1.6rem 1.1rem;
    margin: 0.4rem 0 0.9rem;
  }
  .tarjeta-encabezado {
    display: flex; justify-content: space-between; align-items: center;
  }
  /* Dos columnas de ancho igual, con aire en el medio. */
  .comparacion {
    display: grid; grid-template-columns: 1fr 1fr; gap: 0 3rem;
  }
  .titulo-factura {
    font-size: 1.25rem; font-weight: 600; color: var(--texto);
  }
  .badge {
    font-size: 0.85rem; padding: 0.2rem 0.7rem;
    border-radius: 6px; font-weight: 500; white-space: nowrap;
  }
  .badge-revisar  { background: #3a2a12; color: var(--alerta); }
  .badge-aprobada { background: #14301f; color: var(--ok); }

  .col-titulo {
    color: var(--tenue); font-size: 0.95rem; margin: 0.9rem 0 0.5rem;
  }
  /* Fila etiqueta/valor: etiqueta a la izquierda, valor alineado a la derecha. */
  .fila {
    display: flex; justify-content: space-between;
    padding: 0.2rem 0; font-size: 1rem;
  }
  .fila-etiqueta { color: var(--texto); }
  .fila-valor    { color: var(--texto); font-variant-numeric: tabular-nums; }
  /* Rojo solo del lado de la factura, y solo donde el backend marco diferencia. */
  .fila-valor.discrepa { color: var(--error); }

  /* --- banner de la nota del LLM --- */
  .banner {
    background: var(--error-bg); border: 1px solid var(--error-bd);
    border-radius: 8px; padding: 0.85rem 1rem; margin: 1.1rem 0 0.9rem;
    color: #ffb4b0;
  }
  .banner-ok {
    background: #0f2418; border-color: #1f4a30; color: #9ae6b4;
  }

  /* --- fila de checks --- */
  .checks { font-size: 0.95rem; color: var(--tenue); }
  .chk { margin-right: 1.1rem; white-space: nowrap; }
  .chk-pass { color: var(--ok); }
  .chk-warn { color: var(--alerta); }
  .chk-fail { color: var(--error); }
  .chk-skip { color: var(--tenue); }
</style>
"""


def inyectar() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
