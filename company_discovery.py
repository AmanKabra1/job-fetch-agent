"""
Company discovery for a city / locality / sector / pincode.
==========================================================

Fetches EVERY named business (offices, IT/software firms, shops, agencies,
coworking spaces, etc.) inside an area using ONLY free, no-key public data:

  * Nominatim (OpenStreetMap geocoder) — "Noida Sector 62" -> bounding box.
  * Overpass API (OpenStreetMap)       — every node/way tagged office=*, shop=*,
    amenity (bank/coworking/…), company, craft with a name inside that box.

Both are free and need no API key (just a real User-Agent + polite rate limits).
Website enrichment (tech stack, emails, socials, careers) is done on demand from
the company's own site — also free.

What free data CANNOT do (be honest in the UI):
  * LinkedIn/Crunchbase/Glassdoor/Naukri/JustDial/IndiaMART — no public API.
  * MCA/GST/MSME "all companies in a pincode" — no such free bulk endpoint.
  * Every individual tenant inside a coworking tower — OSM rarely lists them.
Optional key-based sources (Google Places, Foursquare, Mapbox, Bing) can be
slotted into merge() later; they need a key + signup and are left as stubs.
"""

import re
import time
import json
import html
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

_UA = {"User-Agent": "company-discovery/1.0 (business directory; contact: local use)"}
_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_OVERPASS = "https://overpass-api.de/api/interpreter"
_TIMEOUT = 30

# Known coworking brands — flag these buildings (tenant-level enumeration isn't
# available from free data, but we at least mark the space).
_COWORKING = (
    "wework", "awfis", "smartworks", "91springboard", "innov8", "regus", "indiqube",
    "table space", "tablespace", "cowrks", "incuspaze", "worknest", "spring house",
    "springhouse", "devx", "collab", "myhq", "coworking", "co-working",
)

# OSM office=* value -> (industry, is_technical). Covers the spec's categories.
_OFFICE_INDUSTRY = {
    "it": ("IT / Software", True),
    "software": ("IT / Software", True),
    "telecommunication": ("Telecom", True),
    "engineer": ("Engineering", True),
    "research": ("Research / R&D", True),
    "company": ("Company (general)", False),
    "consulting": ("Consulting", False),
    "advertising_agency": ("Advertising / Marketing", False),
    "marketing": ("Digital Marketing", False),
    "financial": ("Finance", False),
    "financial_advisor": ("Finance", False),
    "insurance": ("Insurance", False),
    "accountant": ("Accounting", False),
    "tax_advisor": ("Accounting / Tax", False),
    "lawyer": ("Legal", False),
    "estate_agent": ("Real Estate", False),
    "employment_agency": ("Recruitment / HR", False),
    "educational_institution": ("Education", False),
    "logistics": ("Logistics", False),
    "coworking": ("Coworking Space", False),
    "government": ("Government", False),
    "ngo": ("NGO / Non-profit", False),
    "association": ("Association", False),
    "newspaper": ("Media", False),
    "travel_agent": ("Travel", False),
    "architect": ("Architecture", False),
}

# Website technology signatures (substring / regex on fetched HTML + headers).
_TECH = {
    "React": ["react", "_next/static/chunks", "data-reactroot"],
    "Next.js": ["/_next/", "__next", "next.js"],
    "Angular": ["ng-version", "angular"],
    "Vue": ["vue", "__vue__", "data-v-"],
    "Nuxt": ["__nuxt", "nuxt"],
    "Node.js": ["x-powered-by: express", "node"],
    "Express": ["x-powered-by: express"],
    "NestJS": ["nestjs"],
    "Laravel": ["laravel_session", "laravel"],
    "PHP": ["x-powered-by: php", ".php"],
    "Django": ["csrfmiddlewaretoken", "django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "swagger-ui"],
    "Spring Boot": ["jsessionid", "spring"],
    ".NET": ["asp.net", "__viewstate", "x-aspnet-version"],
    "Ruby on Rails": ["csrf-param", "rails"],
    "WordPress": ["wp-content", "wp-includes", "wordpress"],
    "Shopify": ["cdn.shopify.com", "shopify"],
    "WooCommerce": ["woocommerce"],
    "Magento": ["magento", "mage/"],
    "Wix": ["wix.com", "_wix"],
    "Webflow": ["webflow"],
    "Squarespace": ["squarespace"],
    "Cloudflare": ["cf-ray", "cloudflare"],
    "AWS": ["x-amz-", "amazonaws.com", "cloudfront"],
    "Google Analytics": ["gtag(", "google-analytics.com", "googletagmanager"],
    "HubSpot": ["hs-scripts", "hubspot"],
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SOCIAL = {
    "linkedin": re.compile(r"https?://[\w.]*linkedin\.com/[^\s\"'<>]+", re.I),
    "facebook": re.compile(r"https?://[\w.]*facebook\.com/[^\s\"'<>]+", re.I),
    "instagram": re.compile(r"https?://[\w.]*instagram\.com/[^\s\"'<>]+", re.I),
    "twitter": re.compile(r"https?://[\w.]*(?:twitter|x)\.com/[^\s\"'<>]+", re.I),
    "youtube": re.compile(r"https?://[\w.]*youtube\.com/[^\s\"'<>]+", re.I),
    "github": re.compile(r"https?://[\w.]*github\.com/[^\s\"'<>]+", re.I),
}


def geocode_area(area: str):
    """Resolve a free-text area ('Noida Sector 62', a pincode, a locality) to a
    bounding box + center via Nominatim. Returns None if not found."""
    try:
        r = requests.get(_NOMINATIM, params={
            "q": area, "format": "json", "limit": 1,
            "countrycodes": "in", "addressdetails": 1,
        }, headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ! geocode failed: {e}", flush=True)
        return None
    if not data:
        return None
    top = data[0]
    # Nominatim boundingbox = [south, north, west, east] (strings).
    s, n, w, e = (float(x) for x in top["boundingbox"])
    lat, lon = float(top["lat"]), float(top["lon"])
    # Nominatim often returns a tiny road/point box for "Sector 62". Pad to at
    # least ~2.2 km each way around the center so a whole locality is covered
    # (but never SHRINK a genuinely large area like a full city).
    MIN_HALF = 0.02                              # ~2.2 km in degrees
    s = min(s, lat - MIN_HALF); n = max(n, lat + MIN_HALF)
    w = min(w, lon - MIN_HALF); e = max(e, lon + MIN_HALF)
    # Safety cap so a huge query can't blow the Overpass timeout (~28 km max span).
    MAX_HALF = 0.13
    s = max(s, lat - MAX_HALF); n = min(n, lat + MAX_HALF)
    w = max(w, lon - MAX_HALF); e = min(e, lon + MAX_HALF)
    return {
        "display_name": top.get("display_name", area),
        "lat": lat, "lon": lon,
        "bbox": (s, w, n, e),        # Overpass wants (south,west,north,east)
    }


def _overpass_query(bbox):
    s, w, n, e = bbox
    b = f"{s},{w},{n},{e}"
    # Every named business-like entity in the box. `nwr` = node+way+relation, so
    # we catch far more than nodes alone. Covers offices, shops, crafts, health,
    # education, coworking, companies AND named commercial/industrial buildings.
    return f"""
[out:json][timeout:50];
(
  nwr["name"]["office"]({b});
  nwr["name"]["company"]({b});
  nwr["name"]["shop"]({b});
  nwr["name"]["craft"]({b});
  nwr["name"]["healthcare"]({b});
  nwr["name"]["amenity"~"^(coworking_space|bank|clinic|hospital|pharmacy|college|university|school|restaurant|cafe|fuel|car_rental|marketplace)$"]({b});
  nwr["name"]["building"~"^(commercial|office|industrial|retail)$"]({b});
  nwr["name"]["industrial"]({b});
  nwr["name"]["landuse"="commercial"]({b});
);
out center tags 4000;
"""


def fetch_overpass(bbox):
    """All named businesses inside the bbox from OpenStreetMap. Free, no key."""
    for attempt in range(3):
        try:
            r = requests.post(_OVERPASS, data={"data": _overpass_query(bbox)},
                              headers=_UA, timeout=90)
            r.raise_for_status()
            return r.json().get("elements", [])
        except Exception as e:
            print(f"  ! overpass attempt {attempt+1} failed: {e}", flush=True)
            time.sleep(2 * (attempt + 1))
    return []


# Name keywords that strongly imply an IT / software / tech company, so it's
# classified as IT even when OSM only tags it generically (office=company / a
# plain named node) — most Indian IT firms aren't tagged office=it in OSM.
_IT_NAME_HINTS = (
    "software", "technolog", "infotech", "info tech", "it solution", "it services",
    "systems", "solutions", "infosys", "cybernetics", "cyber", "datalab",
    "data systems", "cloud", "websoft", "webtech", "web solution", "app labs",
    "analytics", "saas", "digital", "infocom", "technosoft", "e-solutions",
    "esolutions", "technologies", "technova", "infoway", "softtech", "soft tech",
    "netsol", "software labs", "ai labs", "tech labs",
)


def _looks_it(name: str) -> bool:
    n = " " + name.lower() + " "
    return any(h in n for h in _IT_NAME_HINTS)


def _classify(tags: dict):
    """Map OSM tags -> (industry, business_type, technical, non_technical)."""
    office = (tags.get("office") or "").lower()
    shop = (tags.get("shop") or "").lower()
    amenity = (tags.get("amenity") or "").lower()
    building = (tags.get("building") or "").lower()
    name = tags.get("name") or ""

    is_coworking = (office == "coworking" or amenity == "coworking_space"
                    or any(c in name.lower() for c in _COWORKING))
    if is_coworking:
        return "Coworking Space", "Coworking", False, True
    # Specific, trustworthy office types first (but not the generic office=company).
    if office and office in _OFFICE_INDUSTRY and office != "company":
        ind, tech = _OFFICE_INDUSTRY[office]
        return ind, "Company / Office", tech, not tech
    # Name-based IT/software detection for generic offices, companies, or plain
    # named nodes/buildings (OSM rarely tags Indian IT firms as office=it).
    if not shop and not amenity and _looks_it(name):
        return "IT / Software", "Company / Office", True, False
    if office == "company":
        return "Company (general)", "Company / Office", False, True
    if office:
        return f"Office ({office})", "Company / Office", False, True
    if shop:
        return f"Retail ({shop})", "Local Business / Retail", False, True
    if tags.get("healthcare") or amenity in ("clinic", "hospital", "pharmacy"):
        return "Healthcare", "Healthcare", False, True
    if amenity in ("college", "university", "school"):
        return "Education", "Education", False, True
    if amenity == "bank":
        return "Finance / Banking", "Company / Office", False, True
    if amenity:
        return amenity.replace("_", " ").title(), "Local Business", False, True
    if tags.get("craft"):
        return f"Craft ({tags['craft']})", "Small Business", False, True
    if building in ("commercial", "office", "retail") or tags.get("landuse") == "commercial":
        return "Commercial Building", "Building", False, True
    if building == "industrial" or tags.get("industrial"):
        return "Industrial", "Building", False, True
    return "Business", "Business", False, True


def _norm(el):
    """One raw OSM element -> the output company record (fields we can fill)."""
    tags = el.get("tags", {})
    name = tags.get("name")
    if not name:
        return None
    lat = el.get("lat") or (el.get("center") or {}).get("lat")
    lon = el.get("lon") or (el.get("center") or {}).get("lon")
    industry, btype, tech_work, nontech_work = _classify(tags)

    # Address from OSM addr:* tags.
    addr_parts = [tags.get("addr:housenumber"), tags.get("addr:street"),
                  tags.get("addr:suburb"), tags.get("addr:city"),
                  tags.get("addr:state"), tags.get("addr:postcode")]
    address = ", ".join(p for p in addr_parts if p)

    website = (tags.get("website") or tags.get("contact:website")
               or tags.get("url") or "")
    is_cowork = btype == "Coworking"
    return {
        "company_name": name,
        "legal_name": tags.get("official_name") or "",
        "website": website,
        "linkedin": tags.get("contact:linkedin") or "",
        "google_maps": (f"https://www.google.com/maps/search/?api=1&query="
                        f"{lat},{lon}" if lat and lon else ""),
        "address": address,
        "city": tags.get("addr:city") or "",
        "state": tags.get("addr:state") or "",
        "pincode": tags.get("addr:postcode") or "",
        "latitude": lat, "longitude": lon,
        "industry": industry,
        "business_type": btype,
        "technical_work": tech_work,
        "non_technical_work": nontech_work,
        "technologies": [],                       # filled on demand via enrich()
        "employees": "",
        "founded": tags.get("start_date") or "",
        "careers": "",
        "hiring": None,
        "emails": [e for e in [tags.get("contact:email") or tags.get("email")] if e],
        "phones": [p for p in [tags.get("phone") or tags.get("contact:phone")] if p],
        "social_links": {k: tags[t] for k, t in (
            ("facebook", "contact:facebook"), ("instagram", "contact:instagram"),
            ("twitter", "contact:twitter"), ("youtube", "contact:youtube"))
            if tags.get(t)},
        "ratings": {},
        "coworking_name": name if is_cowork else "",
        "building_name": tags.get("addr:housename") or "",
        "office_images": [],
        "opening_hours": tags.get("opening_hours") or "",
        "source": ["OpenStreetMap"],
        "osm_id": f"{el.get('type')}/{el.get('id')}",
        "confidence": 0,      # set in discover()
    }


def _dedupe(rows):
    """Merge duplicates by website, then by (name + rounded coords)."""
    out, by_key = [], {}
    for r in rows:
        keys = []
        if r.get("website"):
            keys.append(("web", re.sub(r"^https?://(www\.)?", "", r["website"].lower()).rstrip("/")))
        if r.get("latitude") and r.get("longitude"):
            keys.append(("geo", r["company_name"].strip().lower(),
                         round(r["latitude"], 4), round(r["longitude"], 4)))
        merged = None
        for k in keys:
            if k in by_key:
                merged = by_key[k]
                break
        if merged:
            # keep the richer record; union sources
            for src in r.get("source", []):
                if src not in merged["source"]:
                    merged["source"].append(src)
            if not merged.get("website") and r.get("website"):
                merged["website"] = r["website"]
        else:
            out.append(r)
            for k in keys:
                by_key[k] = r
    return out


def _confidence(r):
    """0-100: how confident/complete this record is."""
    score = 40                                    # on the map at all
    if r.get("website"):
        score += 25
    if r.get("address"):
        score += 10
    if r.get("phones"):
        score += 10
    if r.get("industry") not in ("Unknown", ""):
        score += 10
    if len(r.get("source", [])) > 1:
        score += 5
    return min(100, score)


import os

# Aggregators/social/govt lookup sites — their URLs aren't a company's own site,
# so we skip them when harvesting company websites from web search.
_DIRECTORY_DOMAINS = (
    "justdial", "sulekha", "indiamart", "tradeindia", "linkedin", "indeed",
    "glassdoor", "ambitionbox", "naukri", "facebook", "instagram", "twitter",
    "x.com", "youtube", "wikipedia", "google.", "maps.google", "yelp",
    "crunchbase", "zaubacorp", "tofler", "goodfirms", "clutch.co", "yellowpages",
    "mca.gov", "quora", "reddit", "medium.com", "slideshare", "pinterest",
    "whatsapp", "t.me", "bing.com", "duckduckgo", "scribd", "apna.co", "foundit",
    "monster", "timesjobs", "shine.com", "hirist", "cutshort", "angel.co",
    "wellfound", "freshersworld", "placementindia", "instahyre", "glassdoor",
    "6figr", "ambitionbox", "trustpilot", "mouthshut", "issuu", "coursehero",
)


# Company names inside directory/listicle page text (e.g. JustDial "Top IT
# companies") — "<Capitalized words> <company suffix>". One page lists many.
_COMPANY_NAME_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.'\-]*(?:[ ][A-Z0-9][A-Za-z0-9&.'\-]*){0,4}[ ]"
    r"(?:Technologies|Technology|Solutions|Software|Softwares|Softech|Systems|"
    r"Infotech|Infosystems|Labs|Consulting|Consultancy|Consultants|Services|"
    r"Digital|Networks|Analytics|Innovations|Infoway|Infocom|Pvt\.?[ ]?Ltd|"
    r"Private[ ]Limited|LLP|Inc\.?|Corporation|Enterprises|Ventures))\b")
_NAME_STOP = ("top ", "best ", "list ", "companies in", "list of", "the ", "these ",
              "our ", "software company", "it company", "click ", "read ", "view ")
# First words that mean it's a job-title / heading fragment, not a company name
# (e.g. "Backend Software", "Lead Solutions", "Senior Systems").
_NAME_BAD_FIRST = {
    "backend", "frontend", "full", "fullstack", "lead", "senior", "junior", "sr",
    "jr", "principal", "staff", "associate", "software", "web", "mobile", "cloud",
    "data", "devops", "qa", "ui", "ux", "the", "top", "best", "new", "our", "other",
    "more", "all", "various", "many", "several", "hire", "hiring", "job", "jobs",
    "apply", "view", "read", "click", "about", "contact", "home", "leading", "based",
    "global", "digital", "product", "service", "services", "custom", "enterprise",
}


def _norm_name(n: str) -> str:
    n = re.sub(r"\b(pvt\.?|private|limited|ltd\.?|llp|inc\.?|corp\.?|the)\b", "",
               (n or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def _extract_names(text: str):
    """Company names harvested from a page's text (dedup, filtered)."""
    out, seen = [], set()
    for m in _COMPANY_NAME_RE.finditer(text or ""):
        name = re.sub(r"\s+", " ", m.group(1)).strip(" .,-")
        low = name.lower()
        first = low.split()[0] if low.split() else ""
        words = name.split()
        if (len(name) < 5 or len(name) > 60 or low in seen or first in _NAME_BAD_FIRST
                or len(words) < 2                      # a lone "Technologies" etc.
                or any(low.startswith(s) or s in low for s in _NAME_STOP)):
            continue
        seen.add(low)
        out.append(name)
    return out[:40]                                   # cap per page


def _web_record(name, website, industry, tech, source="Web (Tavily)"):
    return {
        "company_name": name, "legal_name": "", "website": website or "",
        "linkedin": "", "google_maps": "", "address": "", "city": "", "state": "",
        "pincode": "", "latitude": None, "longitude": None, "industry": industry,
        "business_type": "Company / Office", "technical_work": tech,
        "non_technical_work": not tech, "technologies": [], "employees": "",
        "founded": "", "careers": "", "hiring": None, "emails": [], "phones": [],
        "social_links": {}, "ratings": {}, "coworking_name": "", "building_name": "",
        "office_images": [], "opening_hours": "", "source": [source], "osm_id": "",
        "confidence": 0,
    }


def _tavily_search(key, q, max_results=10):
    try:
        r = requests.post("https://api.tavily.com/search", json={
            "api_key": key, "query": q, "max_results": max_results,
            "search_depth": "basic", "include_raw_content": True,
        }, headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  ! tavily {q!r} failed: {e}", flush=True)
        return []


def fetch_tavily_companies(area: str):
    """Extra coverage via Tavily web search (needs TAVILY_API_KEY):
      1) harvest company OWN websites from results (skip directories), and
      2) EXTRACT company names from directory/listicle page text (one page lists
         many) — great for reaching small firms OSM never mapped.
    Records have no coordinates (list-only, no map pin). Queries run in parallel."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    # Developer / IT-focused + general queries — cast a wide net.
    queries = [
        (f"IT and software companies in {area}", "IT / Software", True),
        (f"software development company in {area}", "IT / Software", True),
        (f"web and app development company {area}", "IT / Software", True),
        (f"companies hiring software developers in {area}", "IT / Software", True),
        (f"product based software companies {area}", "IT / Software", True),
        (f"startups in {area} hiring", "Startup", True),
        (f"list of IT companies in {area}", "IT / Software", True),
        (f"companies in {area} office address", "Company (general)", False),
    ]
    rows, dom_seen, name_seen = [], set(), set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_tavily_search, key, q, 10): (ind, tech)
                for q, ind, tech in queries}
        for fut in as_completed(futs):
            industry, tech = futs[fut]
            for res in fut.result():
                url = res.get("url", "")
                dom = re.sub(r"^https?://(www\.)?", "", url.lower()).split("/")[0] if url else ""
                is_dir = any(d in dom for d in _DIRECTORY_DOMAINS)
                # (1) company's own website
                if url and dom and not is_dir and dom not in dom_seen:
                    dom_seen.add(dom)
                    title = (res.get("title", "") or "").strip()
                    for sep in (" | ", " - ", " – ", " :: ", " — ", ": "):
                        title = title.split(sep)[0]
                    nm = title.strip()[:80] or dom
                    name_seen.add(_norm_name(nm))
                    ind2 = "IT / Software" if _looks_it(nm) else industry
                    rows.append(_web_record(nm, url.split("?")[0], ind2, tech or _looks_it(nm)))
                # (2) names harvested from the page text (esp. directory listicles)
                blob = (res.get("title", "") + "\n" + (res.get("content") or "")
                        + "\n" + (res.get("raw_content") or ""))
                for nm in _extract_names(blob):
                    nn = _norm_name(nm)
                    if len(nn) < 4 or nn in name_seen:
                        continue
                    name_seen.add(nn)
                    rows.append(_web_record(nm, "", "IT / Software" if _looks_it(nm) else industry,
                                            _looks_it(nm)))
    print(f"    -> tavily web: {len(rows)} companies (sites + directory names)", flush=True)
    return rows


_DISCOVER_CACHE = {}          # area -> (timestamp, result). Saves Tavily credits.
_CACHE_TTL = 6 * 3600         # 6 hours


def discover(area: str, limit: int = 1000):
    """Main entry: area text -> list of companies (deduped, scored) + geo center.
    Merges OpenStreetMap (mapped, with coords) with Tavily web search (extra
    company sites + names OSM misses). Cached per area for 6h."""
    ck = area.strip().lower()
    hit = _DISCOVER_CACHE.get(ck)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        res = dict(hit[1])
        res["cached"] = True
        res["companies"] = res["companies"][:limit]
        res["count"] = len(res["companies"])
        return res

    geo = geocode_area(area)
    if not geo:
        return {"error": f"Could not locate '{area}'. Try a more specific area, "
                         f"locality, or pincode.", "companies": []}
    time.sleep(1)                                 # Nominatim politeness
    osm_rows, web_rows = [], []
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_osm = ex.submit(fetch_overpass, geo["bbox"])
        f_web = ex.submit(fetch_tavily_companies, geo["display_name"].split(",")[0] or area)
        try:
            osm_rows = [r for r in (_norm(e) for e in f_osm.result()) if r]
        except Exception as e:
            print(f"  ! osm failed: {e}", flush=True)
        try:
            web_rows = f_web.result()
        except Exception as e:
            print(f"  ! tavily failed: {e}", flush=True)

    allr = osm_rows + web_rows
    # Rich records (have coords and/or a website) dedupe by website/coords.
    rich = _dedupe([r for r in allr if r.get("latitude") or r.get("website")])
    rich_names = {_norm_name(r["company_name"]) for r in rich}
    # Name-only records (from directory listicles): keep those not already present.
    extra, seen = [], set()
    for r in allr:
        if r.get("latitude") or r.get("website"):
            continue
        nn = _norm_name(r["company_name"])
        if len(nn) < 4 or nn in rich_names or nn in seen:
            continue
        seen.add(nn)
        extra.append(r)
    rows = rich + extra
    for r in rows:
        r["confidence"] = _confidence(r)
    # Best first; mapped (coords) then website then name-only, within same score.
    rows.sort(key=lambda r: (r["confidence"], bool(r.get("latitude")), bool(r["website"])),
              reverse=True)
    result = {
        "area": area,
        "resolved": geo["display_name"],
        "center": {"lat": geo["lat"], "lon": geo["lon"]},
        "count": len(rows[:limit]),
        "total_found": len(rows),
        "sources": sorted({s for r in rows for s in r.get("source", [])}),
        "cached": False,
        "companies": rows[:limit],
    }
    _DISCOVER_CACHE[ck] = (time.time(), result)
    return result


# --------------------------------------------------------------------------- #
# On-demand website enrichment (tech stack, emails, socials, careers) — free.
# --------------------------------------------------------------------------- #
def _detect_tech(text_lower, headers_lower):
    blob = text_lower + " " + headers_lower
    return sorted({name for name, sigs in _TECH.items()
                   if any(s in blob for s in sigs)})


def enrich_website(url: str):
    """Fetch a company's site and pull tech stack, emails, socials, careers page.
    Best-effort and fast (single GET, short timeout). Free."""
    if not url:
        return {"error": "no url"}
    if not url.startswith("http"):
        url = "https://" + url
    try:
        r = requests.get(url, headers=_UA, timeout=12, allow_redirects=True)
        text = r.text[:400_000]
        headers_lower = "\n".join(f"{k}: {v}" for k, v in r.headers.items()).lower()
    except Exception as e:
        return {"error": str(e), "reachable": False}
    tl = text.lower()
    emails = sorted(set(_EMAIL_RE.findall(text)))[:8]
    socials = {}
    for name, rx in _SOCIAL.items():
        m = rx.search(text)
        if m:
            socials[name] = html.unescape(m.group(0)).rstrip('".,)')
    # Careers/jobs page link.
    careers = ""
    for m in re.finditer(r'href=["\']([^"\']+)["\']', text, re.I):
        href = m.group(1)
        if re.search(r"(career|careers|jobs|join-us|joinus|hiring|vacanc|we-?are-?hiring)", href, re.I):
            careers = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
            break
    hiring = bool(careers) or ("hiring" in tl or "we are hiring" in tl or "careers" in tl)
    return {
        "reachable": True,
        "verified_website": url,
        "technologies": _detect_tech(tl, headers_lower),
        "emails": emails,
        "hr_emails": [e for e in emails if re.search(r"(hr|career|jobs|recruit|talent)", e, re.I)],
        "social_links": socials,
        "careers": careers,
        "hiring": hiring,
    }
