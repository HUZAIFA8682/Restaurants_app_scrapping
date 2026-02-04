import csv
import re
import time
import math
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# -------------------------
# CONFIG
# -------------------------

# south, west, north, east (Rawalpindi rough bbox)
RAWALPINDI_BBOX = (33.55, 73.00, 33.70, 73.15)

# Multiple Overpass endpoints (mirrors)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

HTTP_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; RestaurantAppAudit/1.1)"

# Keep queries small to avoid timeouts
TILE_ROWS = 3
TILE_COLS = 3

# Polite scraping settings for websites
DELAY_BETWEEN_SITES_SEC = 0.6

PLAYSTORE_RE = re.compile(r"https?://play\.google\.com/store/apps/details\?id=[A-Za-z0-9\._]+", re.I)
APPLE_APPS_RE = re.compile(r"https?://apps\.apple\.com/", re.I)
APP_TEXT_HINT_RE = re.compile(r"\b(download\s+our\s+app|get\s+the\s+app|our\s+app)\b", re.I)


# -------------------------
# HELPERS
# -------------------------

def normalize_url(url: str):
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        if not parsed.netloc:
            return None
        return url
    except Exception:
        return None


def tile_bbox(bbox, rows, cols):
    s, w, n, e = bbox
    lat_step = (n - s) / rows
    lon_step = (e - w) / cols
    tiles = []
    for r in range(rows):
        for c in range(cols):
            ts = s + r * lat_step
            tn = s + (r + 1) * lat_step
            tw = w + c * lon_step
            te = w + (c + 1) * lon_step
            tiles.append((ts, tw, tn, te))
    return tiles


def overpass_query_for_bbox(bbox):
    s, w, n, e = bbox
    return f"""
    [out:json][timeout:60];
    (
      node["amenity"="restaurant"]({s},{w},{n},{e});
      way["amenity"="restaurant"]({s},{w},{n},{e});
      relation["amenity"="restaurant"]({s},{w},{n},{e});
    );
    out center tags;
    """


def overpass_post_with_retries(query, max_attempts=4):
    last_err = None

    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(1, max_attempts + 1):
            try:
                r = requests.post(
                    endpoint,
                    data=query.encode("utf-8"),
                    headers={"User-Agent": USER_AGENT},
                    timeout=HTTP_TIMEOUT,
                )
                if r.status_code == 200:
                    return r.json()
                else:
                    last_err = f"{endpoint} HTTP {r.status_code}"
            except requests.RequestException as e:
                last_err = f"{endpoint} {type(e).__name__}: {e}"

            # exponential-ish backoff
            sleep_s = 2 ** attempt
            time.sleep(sleep_s)

    raise RuntimeError(f"Overpass failed after retries. Last error: {last_err}")


def overpass_fetch_restaurants_tiled(main_bbox):
    tiles = tile_bbox(main_bbox, TILE_ROWS, TILE_COLS)
    all_elements = []
    seen_ids = set()

    for i, tb in enumerate(tiles, start=1):
        query = overpass_query_for_bbox(tb)
        data = overpass_post_with_retries(query)
        elements = data.get("elements", [])

        # De-dupe by (type,id) because tiles overlap
        for el in elements:
            key = (el.get("type"), el.get("id"))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            all_elements.append(el)

        print(f"Overpass tile {i}/{len(tiles)}: got {len(elements)} elements (total unique {len(all_elements)})")

        # polite delay for Overpass
        time.sleep(1)

    return all_elements


def extract_address(tags: dict) -> str:
    parts = []
    for k in ("addr:housenumber", "addr:street", "addr:suburb", "addr:city"):
        v = tags.get(k)
        if v:
            parts.append(v)
    return ", ".join(parts)


def scrape_website_for_app_links(website_url: str) -> dict:
    result = {
        "has_android_app": False,
        "has_ios_app": False,
        "evidence_android_url": None,
        "evidence_ios_url": None,
        "notes": "",
        "confidence": 0.0,
    }

    url = normalize_url(website_url)
    if not url:
        result["notes"] = "invalid_website_url"
        result["confidence"] = 0.1
        return result

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            result["notes"] = f"http_{resp.status_code}"
            result["confidence"] = 0.2
            return result

        soup = BeautifulSoup(resp.text, "html.parser")

        hrefs = []
        for a in soup.select("a[href]"):
            href = a.get("href", "").strip()
            if href:
                hrefs.append(urljoin(resp.url, href))

        play = next((h for h in hrefs if PLAYSTORE_RE.search(h)), None)
        apple = next((h for h in hrefs if APPLE_APPS_RE.search(h)), None)

        if play:
            result["has_android_app"] = True
            result["evidence_android_url"] = play
        if apple:
            result["has_ios_app"] = True
            result["evidence_ios_url"] = apple

        if result["has_android_app"] or result["has_ios_app"]:
            result["notes"] = "store_link_found_on_website"
            result["confidence"] = 0.95
        else:
            text = soup.get_text(" ", strip=True)
            if APP_TEXT_HINT_RE.search(text):
                result["notes"] = "app_text_hint_but_no_store_link"
                result["confidence"] = 0.6
            else:
                result["notes"] = "no_store_links_found_on_homepage"
                result["confidence"] = 0.85

        return result

    except requests.RequestException as e:
        result["notes"] = f"request_error:{type(e).__name__}"
        result["confidence"] = 0.2
        return result
    except Exception as e:
        result["notes"] = f"parse_error:{type(e).__name__}"
        result["confidence"] = 0.2
        return result


def dedupe_key(name, website, lat, lon):
    n = (name or "").strip().lower()
    w = (website or "").strip().lower()
    if lat is None or lon is None:
        return f"{n}|{w}|no_coords"
    return f"{n}|{w}|{round(lat,4)}|{round(lon,4)}"


# -------------------------
# MAIN
# -------------------------

def main():
    elements = overpass_fetch_restaurants_tiled(RAWALPINDI_BBOX)

    restaurants = []
    seen = set()

    for el in elements:
        tags = el.get("tags", {}) or {}
        name = tags.get("name")
        if not name:
            continue

        website = tags.get("website") or tags.get("contact:website") or tags.get("url")
        website = normalize_url(website) if website else None

        phone = tags.get("phone") or tags.get("contact:phone") or ""
        address = extract_address(tags)

        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            center = el.get("center") or {}
            lat = center.get("lat")
            lon = center.get("lon")

        key = dedupe_key(name, website or "", lat, lon)
        if key in seen:
            continue
        seen.add(key)

        restaurants.append({
            "name": name,
            "address": address,
            "phone": phone,
            "website": website or "",
            "lat": lat if lat is not None else "",
            "lon": lon if lon is not None else "",
            "source": "OSM/Overpass",
            "osm_type": el.get("type", ""),
            "osm_id": el.get("id", ""),
        })

    audit_rows = []
    for idx, r in enumerate(restaurants, start=1):
        if r["website"]:
            appinfo = scrape_website_for_app_links(r["website"])
            time.sleep(DELAY_BETWEEN_SITES_SEC)
        else:
            appinfo = {
                "has_android_app": False,
                "has_ios_app": False,
                "evidence_android_url": None,
                "evidence_ios_url": None,
                "notes": "no_website_in_osm",
                "confidence": 0.2,
            }

        has_any_app = appinfo["has_android_app"] or appinfo["has_ios_app"]

        audit_rows.append({
            **r,
            "has_android_app": int(appinfo["has_android_app"]),
            "has_ios_app": int(appinfo["has_ios_app"]),
            "has_any_app": int(has_any_app),
            "evidence_android_url": appinfo["evidence_android_url"] or "",
            "evidence_ios_url": appinfo["evidence_ios_url"] or "",
            "notes": appinfo["notes"],
            "confidence": f"{appinfo['confidence']:.2f}",
        })

        if idx % 50 == 0:
            print(f"Website checks: {idx}/{len(restaurants)}")

    audit_csv = "rawalpindi_restaurants_app_audit.csv"
    fields = list(audit_rows[0].keys()) if audit_rows else []
    with open(audit_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(audit_rows)

    NO_APP_CONF_THRESHOLD = 0.80
    no_app_rows = [
        row for row in audit_rows
        if row["website"]
        and row["has_any_app"] == 0
        and float(row["confidence"]) >= NO_APP_CONF_THRESHOLD
        and row["notes"] in ("no_store_links_found_on_homepage", "app_text_hint_but_no_store_link")
    ]

    no_app_csv = "rawalpindi_restaurants_no_app.csv"
    with open(no_app_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(no_app_rows)

    print("\nDONE")
    print(f"- Full audit: {audit_csv}  (rows: {len(audit_rows)})")
    print(f"- No-app output: {no_app_csv}  (rows: {len(no_app_rows)})")
    print("\nNote: Restaurants without websites are excluded from no-app CSV.")


if __name__ == "__main__":
    main()
