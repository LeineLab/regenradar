# Regenradar für Kiosk-Display

Statische Seite, die Radarframes (DWD RV: letzte 60 min Messung + 120 min Vorhersage) als Schleife zeigt.
Kein Kartenrendering im Browser nötig: nur `<img>`-Elemente und ES5-JavaScript.

- `fetch_radar.py` lädt Frames nach `data/` (nur Python-Standardbibliothek). Alle 5 min per Cron:
  `*/5 * * * * cd /pfad/regenradar && python3 fetch_radar.py >> fetch.log 2>&1`
- `index.html` + `data/` per beliebigem Webserver ausliefern (nginx, `python3 -m http.server`).
- `config.json`: Mittelpunkt, Kartenbreite in km, Frame-Aufloesung, Zeitfenster.
  Kacheln werden dauerhaft in `data/tiles` gecacht und nur geladen, wenn sie fehlen.
  Bei Aenderung von Mittelpunkt/Breite/Zoom werden nur die zusaetzlich benoetigten Kacheln nachgeladen.
- Quellen: Radar © Deutscher Wetterdienst (GeoNutzV), Karte © OpenStreetMap-Mitwirkende.
