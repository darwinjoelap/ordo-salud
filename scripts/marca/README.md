# Marca Ordo Salud — fuentes del logo

- `logo-original.png`: logo entregado por Darwin (2026-10-21).
- `trazar.py`: separa las formas del logo por los espacios blancos y las vectoriza (potrace) → `paths.json`.
- `armar.py`: arma los SVG (`static/img/marca/ordo-salud-*.svg`); la cruz y las cabezas se dibujan con geometría
  limpia y el degradado circular del anillo se emula con cuñas recortadas (SVG no tiene degradado cónico).

Regenerar (en `scripts/marca/`): `pip install potracer scipy pillow` · `python trazar.py` · `python armar.py`.
Los PNG (favicon, PWA, apple-touch, imagen para compartir) se renderizan desde los SVG con Chromium.
