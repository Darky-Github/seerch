from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import time
import re

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

rate_store = {}
cache = {}
cache_time = {}

LIMIT = 30
WINDOW = 60
CACHE_TTL = 300

TITLE_BOOST = 5
KNOWN_BOOST = 30

# ------------------ RATE LIMIT ------------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host
    now = time.time()

    rate_store.setdefault(ip, [])
    rate_store[ip] = [t for t in rate_store[ip] if now - t < WINDOW]

    if len(rate_store[ip]) >= LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests")

    rate_store[ip].append(now)
    return await call_next(request)


# ------------------ HOME ------------------

@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


# ------------------ TOKENIZE ------------------

def tokenize(q):
    return re.findall(r"\b\w+\b", q.lower())


# ------------------ VOCAB BUILD ------------------

def build_vocab():
    res = supabase.table("pages").select("title,text").execute()
    pages = res.data or []

    vocab = {}

    for p in pages:
        text = ((p.get("title") or "") + " " + (p.get("text") or "")).lower()
        for w in tokenize(text):
            vocab[w] = vocab.get(w, 0) + 1

    return vocab


VOCAB = build_vocab()


# ------------------ LEVENSHTEIN ------------------

def levenshtein(a, b):
    if abs(len(a) - len(b)) > 2:
        return 999

    dp = list(range(len(b) + 1))

    for i, ca in enumerate(a, 1):
        prev = dp[0]
        dp[0] = i

        for j, cb in enumerate(b, 1):
            temp = dp[j]
            cost = 0 if ca == cb else 1

            dp[j] = min(
                dp[j] + 1,
                dp[j - 1] + 1,
                prev + cost
            )

            prev = temp

    return dp[-1]


# ------------------ SPELL CHECK ------------------

def correct_query(words):
    corrected = []
    changed = False

    for w in words:
        if w in VOCAB:
            corrected.append(w)
            continue

        best = None
        best_score = 999

        for v in VOCAB:
            d = levenshtein(w, v)
            if d < best_score:
                best_score = d
                best = v

        if best_score <= 2 and best:
            corrected.append(best)
            changed = True
        else:
            corrected.append(w)

    corrected_query = " ".join(corrected)

    if changed:
        return corrected_query

    return None


# ------------------ SEARCH ------------------

def get_known():
    res = supabase.table("known_sites").select("*").execute()
    return res.data or []


def get_known_set():
    return {k["url"].lower() for k in get_known() if k.get("url")}


def score_page(page, words, known_set):
    text = (page.get("text") or "").lower()
    title = (page.get("title") or "").lower()
    url = (page.get("url") or "").lower()

    score = 0

    for w in words:
        score += text.count(w)
        if w in title:
            score += TITLE_BOOST

    if url in known_set:
        score += KNOWN_BOOST

    return max(1, min(100, score))


@app.get("/search")
def search(q: str, limit: int = 20, offset: int = 0):

    q = q.lower().strip()
    cache_key = f"{q}:{limit}:{offset}"

    if cache_key in cache and time.time() - cache_time.get(cache_key, 0) < CACHE_TTL:
        return cache[cache_key]

    words = tokenize(q)

    did_you_mean = correct_query(words)
    if did_you_mean:
        words = tokenize(did_you_mean)

    known = get_known()
    known_set = get_known_set()

    results = []

    for site in known:
        name = (site.get("name") or "").lower()
        category = (site.get("category") or "").lower()

        if q == name or q in name or q in category:
            results.append({
                "title": site["name"],
                "url": site["url"],
                "score": 100,
                "type": "known",
                "status": "known"
            })
            break

    pages_res = supabase.table("pages") \
        .select("id,title,url,text") \
        .limit(200) \
        .execute()

    pages = pages_res.data or []

    scored = []

    for page in pages:
        score = score_page(page, words, known_set)

        if score > 1:
            scored.append({
                "title": page["title"],
                "url": page["url"],
                "score": score,
                "type": "page",
                "status": "page"
            })

    scored.sort(key=lambda x: x["score"], reverse=True)

    final = results + scored[offset:offset + limit]

    response = {
        "did_you_mean": did_you_mean,
        "results": final
    }

    cache[cache_key] = response
    cache_time[cache_key] = time.time()

    return response
