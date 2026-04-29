from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import time
import re
from math import log

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

# ---------------- STATE ----------------

rate_store = {}
cache = {}
cache_time = {}

LIMIT = 30
WINDOW = 60
CACHE_TTL = 300

TITLE_BOOST = 3
KNOWN_BOOST = 30

DOC_FREQ = {}
DOC_COUNT = 0


# ---------------- RATE LIMIT ----------------

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


# ---------------- FRONTEND ----------------

@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


# ---------------- TOKENIZE ----------------

def tokenize(text):
    return re.findall(r"\b\w+\b", text.lower())


# ---------------- BUILD IDF ----------------

def build_idf():
    global DOC_FREQ, DOC_COUNT

    res = supabase.table("pages").select("title,text").execute()
    pages = res.data or []

    DOC_COUNT = len(pages)

    for p in pages:
        words = set(tokenize((p.get("title") or "") + " " + (p.get("text") or "")))
        for w in words:
            DOC_FREQ[w] = DOC_FREQ.get(w, 0) + 1


def idf(word):
    df = DOC_FREQ.get(word, 0)
    return log((DOC_COUNT + 1) / (df + 1)) + 1


build_idf()


# ---------------- SPELLCHECK ----------------

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
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp

    return dp[-1]


def correct_query(words):
    vocab = DOC_FREQ.keys()
    corrected = []
    changed = False

    for w in words:
        if w in DOC_FREQ:
            corrected.append(w)
            continue

        best = None
        best_score = 999

        for v in vocab:
            d = levenshtein(w, v)
            if d < best_score:
                best_score = d
                best = v

        if best_score <= 2 and best:
            corrected.append(best)
            changed = True
        else:
            corrected.append(w)

    return " ".join(corrected) if changed else None


# ---------------- DATA ----------------

def get_known():
    return supabase.table("known_sites").select("*").execute().data or []


def get_known_set():
    return {k["url"].lower() for k in get_known() if k.get("url")}


# ---------------- INVERTED INDEX ----------------

def get_candidate_pages(words):
    res = supabase.table("inverted_index") \
        .select("page_id, weight") \
        .in_("word", words) \
        .execute()

    data = res.data or []

    scores = {}

    for row in data:
        pid = row["page_id"]
        scores[pid] = scores.get(pid, 0) + row["weight"]

    return scores


def fetch_pages(page_ids):
    if not page_ids:
        return []

    res = supabase.table("pages") \
        .select("id,title,url,text") \
        .in_("id", page_ids) \
        .execute()

    return res.data or []


# ---------------- SNIPPET ----------------

def make_snippet(text):
    words = text.split()
    return " ".join(words[:60]) + "..." if len(words) > 60 else text


# ---------------- MODE FILTER ----------------

def apply_mode(results, mode):

    if mode == "raw":
        return results

    if mode == "social":
        keywords = ["twitter", "reddit", "instagram", "facebook", "youtube", "vk", "bilibili", "niconico", "quora", "discord", "4chan", "whatsapp", "telegram", "viber", "signal"]
        return [r for r in results if any(k in r["url"].lower() for k in keywords)]

    if mode == "family":
        blocked = ["xxx", "porn", "adultery", "rape", "nude"]
        return [r for r in results if not any(b in r["url"].lower() for b in blocked)]

    if mode == "learner":
        boost = ["wikipedia", "edu", "docs", "learn", "education", "wikihow", "wiki", "documents"]
        for r in results:
            if any(b in r["url"].lower() for b in boost):
                r["score"] += 50

    return results


# ---------------- SEARCH ----------------

@app.get("/search")
def search(q: str, mode: str = "casual", limit: int = 20, offset: int = 0):

    q = q.lower().strip()
    cache_key = f"{q}:{mode}:{limit}:{offset}"

    if cache_key in cache and time.time() - cache_time.get(cache_key, 0) < CACHE_TTL:
        return cache[cache_key]

    words = tokenize(q)
    did_you_mean = correct_query(words)

    if did_you_mean:
        words = tokenize(did_you_mean)

    known = get_known()
    known_set = get_known_set()

    results = []

    # VERIFIED
    for site in known:
        name = (site.get("name") or "").lower()
        category = (site.get("category") or "").lower()

        if q == name or q in name or q in category:
            results.append({
                "title": site["name"],
                "url": site["url"],
                "score": 999999,
                "trust": "Verified",
                "snippet": ""
            })
            break

    # INVERTED INDEX
    candidate_scores = get_candidate_pages(words)
    page_ids = list(candidate_scores.keys())
    pages = fetch_pages(page_ids)

    scored = []

    for p in pages:
        base = candidate_scores.get(p["id"], 0)

        tfidf = 0
        text = (p.get("text") or "").lower()
        title = (p.get("title") or "").lower()

        for w in words:
            tf = text.count(w)
            if tf:
                tfidf += tf * idf(w)
            if w in title:
                tfidf += TITLE_BOOST * idf(w)

        url = (p.get("url") or "").lower()

        if url in known_set:
            tfidf += KNOWN_BOOST

        final_score = base + tfidf

        if final_score > 0:
            scored.append({
                "title": p["title"],
                "url": p["url"],
                "score": round(final_score, 2),
                "trust": "Verified" if url in known_set else "Normal",
                "snippet": make_snippet(p.get("text") or "")
            })

    scored = apply_mode(scored, mode)
    scored.sort(key=lambda x: x["score"], reverse=True)

    final = results + scored[offset:offset + limit]

    response = {
        "did_you_mean": did_you_mean,
        "results": final
    }

    cache[cache_key] = response
    cache_time[cache_key] = time.time()

    return response
