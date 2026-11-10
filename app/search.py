"""Product search in Arabic, French and English.

Engine: Meilisearch (``FIHI_MEILI_URL``), with a built-in fallback used when
it is not configured or does not answer, so the storefront search never breaks.

Relevance
---------
- Every product is indexed with its Arabic name, optional French/English
  names, description and the three titles of its category, plus a ``terms``
  field holding the *folded* form of all of them (see ``fold``).
- Folding: lower case, Latin accents removed (``thé`` -> ``the``), Arabic
  short vowels and tatweel removed, letter variants unified (أ/إ/آ -> ا,
  ة -> ه, ى -> ي) and the article stripped (العسل / والعسل / بالعسل -> عسل).
  Queries are folded the same way, so spelling variants still match.
- Synonyms link the three languages (miel / honey / عسل ...): a French or
  English word finds products whose names are only written in Arabic.
- Meilisearch ranks by matched words, typos, proximity, attribute weight
  (name first, then translated names, category, description) and exactness;
  it tolerates typos and matches word prefixes while typing.
"""

import json
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request

from . import config, logs
from . import db as database

log = logs.get("search")

_AR_DIACRITICS = re.compile("[ً-ٰٟـ]")
_AR_MAP = str.maketrans(
    {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"}
)
_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_ARABIC_RE = re.compile("[؀-ۿ]")

# Same concept in the three languages (folded forms).
SYNONYM_GROUPS = [
    ("miel", "miels", "honey", "عسل"),
    ("huile", "huiles", "oil", "oils", "زيت", "زيوت"),
    ("argan", "اركان"),
    ("amlou", "املو"),
    ("olive", "olives", "زيتون"),
    ("amande", "amandes", "almond", "almonds", "لوز"),
    ("the", "thes", "tea", "teas", "شاي", "اتاي"),
    ("savon", "soap", "صابون", "صابونه"),
    ("parfum", "parfums", "perfume", "perfumes", "عطر", "عطور"),
    ("pack", "packs", "coffret", "باقه", "باقات"),
    ("recette", "recettes", "recipe", "recipes", "وصفه", "وصفات"),
    ("pollen", "لقاح"),
    ("propolis", "عكبر"),
    ("ginseng", "جيسينغ", "جيسينك"),
    ("vinaigre", "vinegar", "خل"),
    ("pomme", "apple", "تفاح"),
    ("thym", "thyme", "زعتر"),
    ("caroube", "carob", "خروب"),
    ("jujubier", "sidr", "سدر"),
    ("eucalyptus", "اكالبتوس"),
    ("sesame", "سمسم"),
    ("ricin", "castor", "خروع"),
    ("creme", "cream", "كريم"),
    ("rose", "ورد"),
    ("ghassoul", "غاسول"),
]
SYNONYMS = {w: [o for o in group if o != w] for group in SYNONYM_GROUPS for w in group}


def fold_token(token):
    token = unicodedata.normalize("NFKD", token.casefold())
    token = "".join(c for c in token if not unicodedata.combining(c) or _ARABIC_RE.match(c))
    token = _AR_DIACRITICS.sub("", unicodedata.normalize("NFC", token)).translate(_AR_MAP)
    if _ARABIC_RE.match(token):
        for prefix in _AR_PREFIXES:
            if token.startswith(prefix) and len(token) - len(prefix) >= 2:
                return token[len(prefix) :]
    return token


def fold(text):
    """Folded tokens of a text (see module docstring)."""
    return [fold_token(t) for t in _TOKEN_RE.findall(text or "")]


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------


def _documents():
    with database.live_db() as conn:
        cats = {
            r["slug"]: r
            for r in conn.execute("SELECT slug,title_ar,title_fr,title_en FROM categories")
        }
        prods = conn.execute(
            "SELECT id,seq,name,name_fr,name_en,cat,description FROM products ORDER BY seq"
        ).fetchall()
    docs = []
    for p in prods:
        cat = cats.get(p["cat"]) or {}
        fields = {
            "name": p["name"] or "",
            "name_fr": p["name_fr"] or "",
            "name_en": p["name_en"] or "",
            "cat_ar": cat.get("title_ar") or "",
            "cat_fr": cat.get("title_fr") or "",
            "cat_en": cat.get("title_en") or "",
            "description": (p["description"] or "")[:500],
        }
        docs.append(
            dict(
                fields,
                id=p["id"],
                seq=p["seq"],
                name_terms=" ".join(
                    fold(fields["name"] + " " + fields["name_fr"] + " " + fields["name_en"])
                ),
                cat_terms=" ".join(
                    fold(fields["cat_ar"] + " " + fields["cat_fr"] + " " + fields["cat_en"])
                ),
                desc_terms=" ".join(fold(fields["description"])),
            )
        )
    return docs


# ---------------------------------------------------------------------------
# Meilisearch
# ---------------------------------------------------------------------------

MEILI_SETTINGS = {
    "searchableAttributes": [
        "name",
        "name_terms",
        "name_fr",
        "name_en",
        "cat_terms",
        "cat_ar",
        "cat_fr",
        "cat_en",
        "desc_terms",
        "description",
    ],
    "displayedAttributes": ["id"],
    "sortableAttributes": ["seq"],
    "rankingRules": ["words", "typo", "proximity", "attribute", "exactness", "seq:asc"],
    "synonyms": SYNONYMS,
    "typoTolerance": {"minWordSizeForTypos": {"oneTypo": 4, "twoTypos": 8}},
    "pagination": {"maxTotalHits": 200},
}


def _meili(method, path, body=None, timeout=5):
    req = urllib.request.Request(  # noqa: S310 - URL from configuration
        config.MEILI_URL + path,
        data=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method=method,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + config.MEILI_KEY},
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310  # nosec B310
        data = res.read()
    return json.loads(data) if data else {}


def _meili_setup():
    index = config.MEILI_INDEX
    try:
        _meili("POST", "/indexes", {"uid": index, "primaryKey": "id"})
    except urllib.error.HTTPError as exc:
        if exc.code != 409:  # 409 = already exists (older versions answer with a task)
            raise
    _meili("PATCH", f"/indexes/{index}/settings", MEILI_SETTINGS)


def _meili_reindex(docs):
    index = config.MEILI_INDEX
    current = {d["id"] for d in docs}
    existing, offset = set(), 0
    while True:
        page = _meili("GET", f"/indexes/{index}/documents?fields=id&limit=1000&offset={offset}")
        existing |= {d["id"] for d in page.get("results", [])}
        offset += 1000
        if offset >= page.get("total", 0):
            break
    if docs:
        _meili("PUT", f"/indexes/{index}/documents?primaryKey=id", docs)
    stale = sorted(existing - current)
    if stale:
        _meili("POST", f"/indexes/{index}/documents/delete-batch", stale)


def _meili_search(query, limit):
    res = _meili(
        "POST",
        f"/indexes/{config.MEILI_INDEX}/search",
        {"q": query, "limit": limit, "attributesToRetrieve": ["id"]},
        timeout=2,
    )
    return [h["id"] for h in res.get("hits", [])]


# ---------------------------------------------------------------------------
# built-in fallback (same folding + synonyms, simple weighted scoring)
# ---------------------------------------------------------------------------

_local = {"version": None, "docs": []}
_WEIGHTS = (("name_terms", 4.0), ("cat_terms", 1.5), ("desc_terms", 1.0))


def _edit_distance_le(a, b, k):
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > k:
            return False
        prev = cur
    return prev[-1] <= k


def _token_score(q, words):
    best = 0.0
    for w in words:
        if w == q:
            return 1.0
        if w.startswith(q):
            best = max(best, 0.8)
        elif len(q) >= 3 and q in w:
            best = max(best, 0.5)
        elif len(q) >= 4 and _edit_distance_le(q, w, 1 if len(q) < 8 else 2):
            best = max(best, 0.4)
    return best


def _local_search(query, limit):
    from . import catalog

    version = catalog.catalog_version()
    if _local["version"] != version:
        _local.update(version=version, docs=_documents())
    tokens = fold(query)
    if not tokens:
        return []
    scored = []
    for doc in _local["docs"]:
        fields = [(doc[f].split(), w) for f, w in _WEIGHTS]
        total = 0.0
        for q in tokens:
            variants = [q] + SYNONYMS.get(q, [])
            best = max(
                (_token_score(v, words) * w * (1.0 if v == q else 0.9))
                for v in variants
                for words, w in fields
            )
            if best == 0:
                break  # every query word must match something
            total += best
        else:
            scored.append((-total, doc["seq"], doc["id"]))
    scored.sort()
    return [pid for _, _, pid in scored[:limit]]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def search(query, limit=24):
    """Ids of the products matching ``query``, most relevant first."""
    query = re.sub(r"\s+", " ", query or "").strip()[:100]
    limit = max(1, min(int(limit), 60))
    if not query:
        return {"ids": [], "engine": "none"}
    folded = " ".join(fold(query))
    if config.MEILI_URL and _state["ready"]:
        try:
            return {"ids": _meili_search(folded or query, limit), "engine": "meilisearch"}
        except (urllib.error.URLError, OSError, ValueError) as exc:
            log.warning("meilisearch unavailable, using built-in search", extra={"error": str(exc)})
    return {"ids": _local_search(query, limit), "engine": "builtin"}


_state = {"ready": False, "dirty": threading.Event(), "started": False}


def _worker():
    while True:
        _state["dirty"].wait()
        time.sleep(0.3)  # coalesce bursts of catalog writes
        _state["dirty"].clear()
        try:
            if not _state["ready"]:
                _meili_setup()
            _meili_reindex(_documents())
            _state["ready"] = True
        except Exception as exc:  # keep the worker alive whatever happens
            log.warning("search reindex failed", extra={"error": str(exc)})
            time.sleep(5)
            _state["dirty"].set()  # retry later


def start():
    """Start the background indexer and queue a full reindex (Meilisearch only)."""
    if not config.MEILI_URL or _state["started"]:
        return
    _state["started"] = True
    threading.Thread(target=_worker, name="search-indexer", daemon=True).start()
    _state["dirty"].set()


def schedule_reindex():
    if _state["started"]:
        _state["dirty"].set()
