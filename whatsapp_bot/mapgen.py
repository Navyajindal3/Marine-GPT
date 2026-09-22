"""
mapgen.py - Leaflet-style static map images for the TARANG WhatsApp bot.

Coherent with the TARANG web app (Leaflet + OpenStreetMap):
  * 🟢 green filled circles  -> recommended fishing zones (PFZ)
  * 🔵 dashed blue line      -> safe route from Kochi Harbour
  * 🔴 red filled circles    -> restricted / geofenced risk areas
  * ⚪ harbour pin           -> Kochi Harbour (departure)
  * legend bar               -> '---- Safe Route   ● High Fishing Zone'

Tiles come from the live OpenStreetMap tile server (same style as the web
app). If tiles can't be fetched (offline demo), it falls back to a plain
sea-blue canvas so the bot NEVER crashes on a map.

Public API:
  render_route_map(zone_dict, lang)  -> (png_path, caption)  route/pfz query
  render_avoid_map(lang)             -> (png_path, caption)  avoid query
  risk_score(boat_cat, day)          -> '28/100 - Low' style score string
"""
import math
import os
import threading

import requests
from PIL import Image, ImageDraw, ImageFont

import kochi

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
UA = "tarang-whatsapp-demo/1.0 (hackathon)"
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mapcache")
os.makedirs(TMP, exist_ok=True)

W, H = 900, 620          # output image size (WhatsApp-friendly, 2:3-ish)
LEGEND_H = 64
TILE_SIZE = 256

# TARANG palette (matches the web app's teal/green theme)
TEAL = (13, 128, 111)
GREEN_FILL = (46, 160, 67, 90)
GREEN_EDGE = (46, 160, 67)
RED_FILL = (214, 69, 65, 90)
RED_EDGE = (214, 69, 65)
ROUTE_BLUE = (58, 110, 214)
WHITE = (255, 255, 255)
INK = (32, 41, 51)

_lock = threading.Lock()

# ---------------------------------------------------------------------------
# web-mercator helpers
# ---------------------------------------------------------------------------
def _lng_to_x(lng, z):
    return (lng + 180.0) / 360.0 * (1 << z)


def _lat_to_y(lat, z):
    r = math.radians(lat)
    return (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * (1 << z)


def _x_to_lng(x, z):
    return x / (1 << z) * 360.0 - 180.0


def _y_to_lat(y, z):
    n = math.pi - 2.0 * math.pi * y / (1 << z)
    return math.degrees(math.atan(math.sinh(n)))


def _fit_zoom(lats, lngs, w=W, h=H - LEGEND_H, zmin=8, zmax=13):
    """Choose the max zoom where every point fits inside (w, h) tiles-space."""
    for z in range(zmax, zmin - 1, -1):
        xs = [_lng_to_x(l, z) for l in lngs]
        ys = [_lat_to_y(a, z) for a in lats]
        if max(xs) - min(xs) < w / TILE_SIZE - 0.4 and \
           max(ys) - min(ys) < h / TILE_SIZE - 0.4:
            return z
    return zmin


def _font(size, bold=False):
    names = (["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"] if bold else
             ["/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc"])
    for n in names:
        if os.path.exists(n):
            try:
                return ImageFont.truetype(n, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _fetch_tiles(z, x0, y0, x1, y1):
    """Stitch the OSM tiles covering (x0,y0)-(x1,y1). None when offline."""
    try:
        w_tiles, h_tiles = x1 - x0 + 1, y1 - y0 + 1
        canvas = Image.new("RGB", (w_tiles * TILE_SIZE, h_tiles * TILE_SIZE),
                           (173, 205, 214))  # sea fallback colour
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                if ty < 0 or ty >= (1 << z):
                    continue
                txx, tyy = tx % (1 << z), ty
                r = requests.get(TILE_URL.format(z=z, x=txx, y=tyy),
                                 headers={"User-Agent": UA}, timeout=8)
                if r.status_code == 200:
                    import io
                    canvas.paste(Image.open(io.BytesIO(r.content)).convert("RGB"),
                                 ((tx - x0) * TILE_SIZE, (ty - y0) * TILE_SIZE))
        return canvas
    except Exception:
        return None


def _dashed_line(draw, p0, p1, dash=14, gap=10, **kw):
    """Dashed line (the recording's 'Safe Route' style)."""
    import math as m
    x0, y0 = p0
    x1, y1 = p1
    dist = m.hypot(x1 - x0, y1 - y0)
    if dist == 0:
        return
    ux, uy = (x1 - x0) / dist, (y1 - y0) / dist
    d = 0.0
    while d < dist:
        e = min(d + dash, dist)
        draw.line([(x0 + ux * d, y0 + uy * d), (x0 + ux * e, y0 + uy * e)], **kw)
        d += dash + gap


def _zone_circle(draw, xy, r, fill, edge, width=4):
    """Translucent filled circle with a solid edge (single RGBA composite)."""
    x, y = xy
    bbox = [x - r, y - r, x + r, y + r]
    ov = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
    d2 = ImageDraw.Draw(ov)
    d2.ellipse(bbox, fill=fill, outline=edge + (255,), width=width)
    rgb = Image.alpha_composite(draw._image.convert("RGBA"), ov).convert("RGB")
    draw._image.paste(rgb, (0, 0))


def _legend(img, route=True, zone=True, restricted=False):
    """Bottom legend bar - matches the mock-up/web-app legend."""
    d = ImageDraw.Draw(img)
    y0 = H - LEGEND_H
    d.rectangle([0, y0, W, H], fill=WHITE)
    d.line([(0, y0), (W, y0)], fill=(226, 232, 240), width=2)
    f = _font(22)
    x = 26
    cy = y0 + LEGEND_H // 2
    if route:
        _dashed_line(d, (x, cy), (x + 52, cy), dash=11, gap=7,
                     fill=ROUTE_BLUE, width=5)
        d.text((x + 62, cy - 13), "Safe Route", font=f, fill=INK)
        x += 62 + 128
    if zone:
        d.ellipse([x, cy - 11, x + 22, cy + 11], fill=GREEN_EDGE)
        d.text((x + 32, cy - 13), "High Fishing Zone", font=f, fill=INK)
        x += 32 + 232
    if restricted:
        d.ellipse([x, cy - 11, x + 22, cy + 11], fill=RED_EDGE)
        d.text((x + 32, cy - 13), "Restricted", font=f, fill=INK)


def _label_chip(d, xy, text, f, pad=8):
    """White chip with teal border (zone label on the map)."""
    x, y = xy
    w = f.getbbox(text)[2] + pad * 2
    h = f.getbbox(text)[3] + pad * 2 + 2
    d.rounded_rectangle([x - w // 2, y - h // 2, x + w // 2, y + h // 2],
                        radius=10, fill=WHITE, outline=TEAL, width=3)
    d.text((x - w // 2 + pad, y - h // 2 + pad - 1), text, font=f, fill=INK)


def _render(points, circles, polylines, out_path, restricted_legend=False):
    """Generic renderer. circles: (lat,lng,r_px,kind). polylines: [(lat,lng)]."""
    lats = [p[0] for p in points] + [c[0] for c in circles]
    lngs = [p[1] for p in points] + [c[1] for c in circles]
    for pl in polylines:
        lats += [p[0] for p in pl]
        lngs += [p[1] for p in pl]
    z = _fit_zoom(lats, lngs)
    cx = sum(min(_lng_to_x(l, z) for l in lngs) +
             max(_lng_to_x(l, z) for l in lngs) for _ in [0]) / 2  # placeholder
    xs = [_lng_to_x(l, z) for l in lngs]
    ys = [_lat_to_y(a, z) for a in lats]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    x0, y0 = int(cx - W / 2 / TILE_SIZE), int(cy - (H - LEGEND_H) / 2 / TILE_SIZE)
    base = _fetch_tiles(z, x0, y0, x0 + W // TILE_SIZE + 1, y0 + (H - LEGEND_H) // TILE_SIZE + 1)
    if base is None:
        base = Image.new("RGB", (W + TILE_SIZE * 2, H), (173, 205, 214))
    img = base.crop(((cx - x0) * TILE_SIZE - W // 2,
                     (cy - y0) * TILE_SIZE - (H - LEGEND_H) // 2,
                     (cx - x0) * TILE_SIZE + W // 2,
                     (cy - y0) * TILE_SIZE + (H - LEGEND_H) // 2 + LEGEND_H))
    img = img.resize((W, H)) if img.size != (W, H) else img
    d = ImageDraw.Draw(img)

    def px(lat, lng):
        return ((_lng_to_x(lng, z) - cx) * TILE_SIZE + W // 2,
                (_lat_to_y(lat, z) - cy) * TILE_SIZE + (H - LEGEND_H) // 2)

    # circles first (zones/restricted), then routes on top, then labels
    zf = _font(24, bold=True)
    for lat, lng, r, kind in circles:
        xy = px(lat, lng)
        fill, edge = (GREEN_FILL, GREEN_EDGE) if kind == "zone" else (RED_FILL, RED_EDGE)
        _zone_circle(d, xy, r, fill, edge)
    for pl in polylines:
        pts = [px(a, l) for a, l in pl]
        for a, b in zip(pts, pts[1:]):
            _dashed_line(d, a, b, dash=13, gap=9, fill=ROUTE_BLUE, width=6)
    # labels handled by caller via annotations
    anns = points
    circle_pts = {(c[0], c[1]): c[2] for c in circles}
    for lat, lng, text in anns:
        xy = px(lat, lng)
        if text == "harbour":
            d.ellipse([xy[0] - 10, xy[1] - 10, xy[0] + 10, xy[1] + 10],
                      fill=WHITE, outline=INK, width=4)
            d.ellipse([xy[0] - 4, xy[1] - 4, xy[0] + 4, xy[1] + 4], fill=INK)
        else:
            # chip sits just below its circle, never on top of it
            r = circle_pts.get((lat, lng), 0)
            _label_chip(d, (xy[0], xy[1] + r + 26), text, zf)
    _legend(img, route=bool(polylines), zone=any(c[3] == "zone" for c in circles),
            restricted=restricted_legend)
    img.save(out_path, "JPEG", quality=82)
    return out_path

# ---------------------------------------------------------------------------
# public builders (per query type)
# ---------------------------------------------------------------------------
def render_zone_map(zone, day=1, lang="en"):
    """PFZ zone map: green highlight circle + harbour pin (no route line)."""
    name = zone["name"]
    label = f"{name} (PFZ {zone['id']})"
    circles = [(zone["lat"], zone["lng"], 56, "zone")]
    pts = [(kochi.KOCHI_PORT["lat"], kochi.KOCHI_PORT["lng"], "harbour"),
           (zone["lat"], zone["lng"], label)]
    out = os.path.join(TMP, f"zone_{zone['id']}.jpg")
    with _lock:
        _render(pts, circles, [], out)
    caption = (f"🗺 Fishing zone around Kochi for {kochi.friendly_day(day or 1)}: "
               f"green circle = high fishing zone "
               f"{name} (PFZ {zone['id']}), ~{zone['dist_km']} km out.")
    return out, caption


def render_route_map(zone, lang="en"):
    """Safe-route map: harbour -> dashed blue line -> green zone circle."""
    name = zone["name"] if lang != "hi" else zone["name"]
    label = f"{name} (PFZ {zone['id']})"
    circles = [(zone["lat"], zone["lng"], 56, "zone")]
    pl = [(kochi.KOCHI_PORT["lat"], kochi.KOCHI_PORT["lng"]),
          (zone["lat"], zone["lng"])]
    pts = [(kochi.KOCHI_PORT["lat"], kochi.KOCHI_PORT["lng"], "harbour"),
           (zone["lat"], zone["lng"], label)]
    out = os.path.join(TMP, f"route_{zone['id']}.jpg")
    with _lock:
        _render(pts, circles, [pl], out)
    caption = (f"🗺 Safe route - Kochi Harbour ➜ {name} (PFZ {zone['id']}), "
               f"~{zone['dist_km']} km. Blue dashes = safe route; "
               f"green circle = high fishing zone.")
    return out, caption


# Restricted / risk areas as a clean table (lat, lng, label) — the demo
# geofences for Kochi, spread so the red circles never overlap on the map.
RESTRICTED_AREAS = [
    (9.958, 76.250, "R1"),   # Kochi Vessel Traffic Lane (fairway)
    (9.848, 76.198, "R2"),   # Cochin MPA (marine park subzone)
    (9.971, 76.262, "R3"),   # Gundu Light dredging zone
]


def render_avoid_map(lang="en"):
    """Restricted / geofenced risk areas as red circles."""
    circles = [(lat, lng, 46, "restricted") for lat, lng, _ in RESTRICTED_AREAS]
    pts = [(kochi.KOCHI_PORT["lat"], kochi.KOCHI_PORT["lng"], "harbour")]
    pts += [(lat, lng, lbl) for lat, lng, lbl in RESTRICTED_AREAS]
    out = os.path.join(TMP, "avoid.jpg")
    with _lock:
        _render(pts, circles, [], out, restricted_legend=True)
    caption = ("🔴 Restricted / geofenced areas around Kochi (R1-R3): keep a "
               "500 m buffer. Red circles = no-fishing / risk areas.")
    return out, caption


def risk_score(boat_cat, day=1, lang="en"):
    """Delegates to kochi.risk_score (kept for back-compat)."""
    return kochi.risk_score(boat_cat, day, lang)


def safe_route_map_available():
    """True when the OSM tile server is reachable (for the config banner)."""
    try:
        return requests.get(TILE_URL.format(z=1, x=1, y=1),
                            headers={"User-Agent": UA}, timeout=4).status_code == 200
    except Exception:
        return False
