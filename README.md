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

## Performance (Raspberry Pi / 4K)
- Karte und Radar werden auf je ein Canvas gezeichnet; die Basemap nur einmal. `MAX_CANVAS` oben in `index.html`
  (Standard 1920 px) begrenzt die Canvas-Groesse, der Browser skaliert hoch. Kleiner = weniger CPU/RAM.
- `image_width`: `"auto"` (Standard) = 4 px/km Kartenbreite (min. 320, max. 1280), da das DWD-Radar nativ nur 1 km aufloest.
- `basemap_zoom`: `"auto"` waehlt die Kachelstufe fuer ca. 1920 px Kartenbreite (OSM-Kacheln sind 256 px). Zahl = fest.
- `parallel_downloads` (Standard 3): gleichzeitige Radar-Abrufe.
- Schlaegt ein Abruf fehl, wird bis zu 3x wiederholt und die Server-Antwort ins Log geschrieben (`fetch.log`).
