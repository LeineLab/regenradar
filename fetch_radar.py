#!/usr/bin/env python3
"""Holt Radarframes (DWD RV: Analyse + Vorhersage) und schreibt sie nach ./data.

Nur Standardbibliothek. Per Cron alle 5 Minuten ausfuehren, z. B.:
  */5 * * * * cd /pfad/zu/regenradar && python3 fetch_radar.py
Die Basemap-Kacheln werden nur einmal geladen (bzw. wenn config.json geaendert wurde).
"""
from concurrent.futures import ThreadPoolExecutor
import json, math, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
WMS = "https://maps.dwd.de/geoserver/dwd/wms"
LAYER = "dwd:Radar_rv_product_1x1km_ger"
UA = "KioskDisplay/1.0"
R = 6378137.0


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def merc(lat, lon):
    return (R * math.radians(lon),
            R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def bbox(cfg):
    cx, cy = merc(cfg["center_lat"], cfg["center_lon"])
    # Mercator streckt mit 1/cos(lat): Breite in Meter am Boden -> Kartenmeter
    k = 1 / math.cos(math.radians(cfg["center_lat"]))
    w = cfg["width_km"] * 1000 * k
    h = w * cfg["aspect"][1] / cfg["aspect"][0]
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def reference_time():
    """Letzte Analysezeit = Default von REFERENCE_TIME des Layers."""
    xml = get(WMS.replace("/wms", "/Radar_rv_product_1x1km_ger/ows") + "?service=WMS&version=1.3.0&request=GetCapabilities", 90).decode("utf-8", "replace")
    i = xml.find("<Name>Radar_rv_product_1x1km_ger</Name>")
    seg = xml[i:xml.find("</Layer>", i)]
    ref = re.search(r'<Dimension name="REFERENCE_TIME" default="([^"]+)"', seg).group(1)
    tdim = re.search(r'<Dimension name="time"[^>]*>[^/<]*/([^/<]+)/', seg).group(1)
    p = lambda s: datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    return p(ref), p(tdim)


def image_width(cfg):
    """Radar hat nativ 1 km Aufloesung; ca. 4 px/km reichen, der Browser skaliert hoch."""
    w = cfg.get("image_width", "auto")
    if w != "auto":
        return int(w)
    return int(max(320, min(1280, cfg["width_km"] * 4)))


def tile_zoom(cfg):
    """Kachelstufe, bei der die Karte ca. 1920 px breit ist (nicht feiner); "basemap_zoom" in der Config ueberschreibt."""
    z = cfg.get("basemap_zoom", "auto")
    if z != "auto":
        return int(z)
    m_per_px = cfg["width_km"] * 1000 / 1920.0
    z = math.ceil(math.log(2 * math.pi * R * math.cos(math.radians(cfg["center_lat"])) / 256 / m_per_px, 2) - 0.5)
    return max(3, min(17, z))


def basemap(cfg, bb):
    """Liefert die benoetigten Kachelnamen; fehlende werden einmalig geladen, vorhandene nie erneut."""
    z = tile_zoom(cfg)
    n = 2 ** z
    def tile(x, y):
        return ((x + R * math.pi) / (2 * R * math.pi) * n, (R * math.pi - y) / (2 * R * math.pi) * n)
    x0, y1 = tile(bb[0], bb[1]); x1, y0 = tile(bb[2], bb[3])
    tdir = os.path.join(DATA, "tiles")
    os.makedirs(tdir, exist_ok=True)
    names = []
    for x in range(int(x0), int(x1) + 1):
        for y in range(int(y0), int(y1) + 1):
            name = "t_%d_%d_%d.png" % (z, x, y)
            path = os.path.join(tdir, name)
            if not os.path.exists(path):
                img = get("https://tile.openstreetmap.org/%d/%d/%d.png" % (z, x, y))
                open(path + ".tmp", "wb").write(img); os.replace(path + ".tmp", path)
                time.sleep(0.3)
            names.append(name)
    return names


def main():
    cfg = json.load(open(os.path.join(BASE, "config.json")))
    os.makedirs(DATA, exist_ok=True)
    bb = bbox(cfg)
    tiles = basemap(cfg, bb)
    ref, tmax = reference_time()
    w = image_width(cfg); h = round(w * cfg["aspect"][1] / cfg["aspect"][0])
    start = ref - timedelta(minutes=cfg["past_minutes"])
    end = min(ref + timedelta(minutes=cfg["future_minutes"]), tmax)
    # Vorhersage-Frames nur neu holen, wenn es eine neue Referenzzeit (neuer Modelllauf) gibt
    ref_file = os.path.join(DATA, "reference.txt")
    old_ref = open(ref_file).read().strip() if os.path.exists(ref_file) else ""
    new_run = old_ref != iso(ref)
    steps, t = [], start
    while t <= end:
        steps.append(t)
        t += timedelta(minutes=5)

    def fetch(t):
        fn = "r_%s.png" % t.strftime("%Y%m%dT%H%MZ")
        path = os.path.join(DATA, fn)
        if os.path.exists(path) and not (new_run and t >= ref):
            return t, fn, True
        q = urllib.parse.urlencode({
            "service": "WMS", "version": "1.3.0", "request": "GetMap", "layers": LAYER,
            "styles": "", "crs": "EPSG:3857", "bbox": ",".join("%.2f" % v for v in bb),
            "width": w, "height": h, "format": "image/png", "transparent": "true",
            "time": iso(t), "reference_time": iso(ref)})
        try:
            img = get(WMS + "?" + q)
            if img[:4] != b"\x89PNG":
                raise ValueError("keine PNG-Antwort")
            open(path + ".tmp", "wb").write(img); os.replace(path + ".tmp", path)
            return t, fn, True
        except Exception as e:
            print("Frame %s fehlgeschlagen: %s" % (iso(t), e), file=sys.stderr)
            return t, fn, os.path.exists(path)

    with ThreadPoolExecutor(max_workers=cfg.get("parallel_downloads", 3)) as ex:
        results = list(ex.map(fetch, steps))
    frames = [{"t": iso(t), "file": fn, "forecast": t > ref} for t, fn, ok in results if ok]
    if all(ok for _, _, ok in results):
        open(ref_file, "w").write(iso(ref))
    # alte Frames loeschen
    keep = set(f["file"] for f in frames)
    for f in os.listdir(DATA):
        if f.startswith("r_") and f.endswith(".png") and f not in keep:
            os.remove(os.path.join(DATA, f))
    z = tile_zoom(cfg)
    meta = {
        "updated": iso(datetime.now(timezone.utc)), "reference": iso(ref), "frames": frames,
        "location": cfg["location_name"], "bbox": bb, "zoom": z,
        "circles_m": [r * 1000 / math.cos(math.radians(cfg["center_lat"])) for r in cfg.get("circle_radii_km", [])],
        "marker": merc(cfg["center_lat"], cfg["center_lon"]),
        "tiles": tiles,
    }
    json.dump(meta, open(os.path.join(DATA, "frames.json.tmp"), "w"))
    os.replace(os.path.join(DATA, "frames.json.tmp"), os.path.join(DATA, "frames.json"))
    print("OK: %d Frames, Referenz %s" % (len(frames), iso(ref)))


if __name__ == "__main__":
    main()
