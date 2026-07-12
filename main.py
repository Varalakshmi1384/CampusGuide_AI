import json
import math
import re
import time
import uuid
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

from store import build_store, hash_password, verify_password

BASE_DIR = Path(__file__).parent

app = FastAPI(title="CampusGuide AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STORE, BACKEND = build_store()
print(f"[startup] data backend = {BACKEND}")

SERVICES = STORE.get_services()
SERVICES_BY_ID = {s["id"]: s for s in SERVICES}

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
EMBEDDING_MODEL = "models/text-embedding-004"

STOPWORDS = {"i", "the", "a", "an", "is", "how", "do", "to", "my", "for", "of", "in", "on", "what", "where",
             "can", "get", "need", "am", "me", "and", "it", "at", "how do", "who"}


def tokenize(text: str):
    words = re.findall(r"[a-zA-Z]+", (text or "").lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def keyword_score(q_tokens: set, svc: dict) -> float:
    haystack = " ".join([svc["service_name"], svc.get("keywords") or "", svc.get("sample_query") or "",
                          svc.get("category") or ""])
    h_tokens = set(tokenize(haystack))
    if not h_tokens or not q_tokens:
        return 0.0
    overlap = len(q_tokens & h_tokens)
    return overlap / max(len(q_tokens), 1)


# =========================================================== SEMANTIC RETRIEVAL
# Real vector embeddings via Gemini's embedding API (no heavy local ML deps,
# so it stays deploy-friendly on a free Render instance). If no API key is
# configured, or the embedding calls fail, retrieval automatically falls back
# to pure keyword matching — same graceful-degradation pattern as the rest
# of the app.
_genai = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _genai = genai
    except Exception as e:
        print("[embeddings] google-generativeai unavailable:", e)


def embed_text(text: str, task_type: str):
    if not _genai:
        return None
    try:
        result = _genai.embed_content(model=EMBEDDING_MODEL, content=text, task_type=task_type)
        return result["embedding"]
    except Exception as e:
        print("[embeddings] embed_content failed:", e)
        return None


def cosine_similarity(a, b):
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def build_service_embedding_text(svc: dict) -> str:
    return " | ".join(filter(None, [
        svc.get("service_name"), svc.get("category"), svc.get("department"),
        svc.get("keywords"), svc.get("sample_query"), svc.get("intent"),
    ]))


def build_service_embeddings():
    """One-time startup cost: embed all 50 services. If it fails partway
    (rate limit, network), we keep whatever succeeded and run in hybrid
    mode for the rest — never blocks startup."""
    if not _genai:
        print("[embeddings] no GEMINI_API_KEY — retrieval will use keyword matching only")
        return {}
    embeddings = {}
    for svc in SERVICES:
        vec = embed_text(build_service_embedding_text(svc), task_type="retrieval_document")
        if vec:
            embeddings[svc["id"]] = vec
    print(f"[embeddings] embedded {len(embeddings)}/{len(SERVICES)} services")
    return embeddings


SERVICE_EMBEDDINGS = build_service_embeddings()
SEMANTIC_ENABLED = len(SERVICE_EMBEDDINGS) > 0


def find_best_match(query: str):
    """Hybrid retrieval: blends semantic (embedding cosine similarity) and
    lexical (keyword overlap) scores. Falls back to pure keyword matching
    if embeddings aren't available for a given service or at all."""
    q_tokens = set(tokenize(query))
    if not q_tokens:
        return None, 0.0

    query_vec = embed_text(query, task_type="retrieval_query") if SEMANTIC_ENABLED else None

    best, best_score = None, 0.0
    for svc in SERVICES:
        kw_score = keyword_score(q_tokens, svc)
        sem_score = 0.0
        if query_vec and svc["id"] in SERVICE_EMBEDDINGS:
            sem_score = max(0.0, cosine_similarity(query_vec, SERVICE_EMBEDDINGS[svc["id"]]))
            score = 0.65 * sem_score + 0.35 * kw_score
        else:
            score = kw_score
        if score > best_score:
            best, best_score = svc, score
    return best, round(min(best_score, 1.0), 3)


def build_prompt(query: str, service: dict) -> str:
    return f"""You are CampusGuide AI, a helpful student administrative assistant.
Answer the student's question using ONLY the information below. Be warm, clear, and concise.
Cover: what to do, where to go, documents needed, fees, and how long it takes.

Service info (JSON):
{json.dumps(service, indent=2, default=str)}

Student question: "{query}"

Write a short, friendly, structured answer (use short paragraphs or bullet points).
"""


def call_gemini(prompt: str) -> str | None:
    if not _genai:
        return None
    try:
        model = _genai.GenerativeModel(GEMINI_MODEL)
        resp = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        print("Gemini call failed:", e)
        return None


def fallback_answer(query: str, service: dict | None) -> str:
    if not service:
        return ("I couldn't find an exact match for that in my knowledge base yet. "
                "Try rephrasing, or contact the Administrative Office (Admin Block, Room 12) for general guidance.")
    docs = ", ".join(service["required_documents"])
    steps = " → ".join(service["procedure_steps"])
    return (
        f"For **{service['service_name']}**, head to the {service['department']} "
        f"({service['building']}, {service['room_number']}). "
        f"Fee: {service['fees']}. Processing time: {service['processing_time']}. "
        f"Documents needed: {docs}. "
        f"Steps: {steps}. "
        f"Contact: {service['contact_email']}. "
        f"If your request is rejected: {service['rejection_policy']}"
    )


# =========================================================== AUTH
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    registration_number: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def get_current_user(authorization: str | None = Header(None)):
    """Returns the logged-in user dict, or None. Never raises — auth is optional
    everywhere except the endpoints that explicitly require it (e.g. /auth/me)."""
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    return STORE.get_user_by_token(token)


@app.post("/auth/signup")
def signup(req: SignupRequest):
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    existing = STORE.get_user_by_email(req.email.lower())
    if existing:
        raise HTTPException(400, "An account with this email already exists")
    salt_hex, hash_hex = hash_password(req.password)
    try:
        user = STORE.create_user(req.name.strip(), req.email.lower(), salt_hex, hash_hex,
                                  req.registration_number.strip() if req.registration_number else None)
    except ValueError:
        raise HTTPException(400, "An account with this email already exists")
    token = STORE.create_session(user["id"])
    return {"token": token, "user": user}


@app.post("/auth/login")
def login(req: LoginRequest):
    user = STORE.get_user_by_email(req.email.lower())
    if not user or not verify_password(req.password, user["password_salt"], user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    token = STORE.create_session(user["id"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}


@app.get("/auth/me")
def get_me(current_user=Depends(get_current_user)):
    if not current_user:
        raise HTTPException(401, "Not logged in")
    return current_user


@app.post("/auth/logout")
def logout(authorization: str | None = Header(None)):
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        if token:
            STORE.delete_session(token)
    return {"status": "ok"}


# =========================================================== CHAT
class ChatRequest(BaseModel):
    session_id: str | None = None
    query: str


@app.post("/chat")
def chat(req: ChatRequest, current_user=Depends(get_current_user)):
    start = time.time()
    service, confidence = find_best_match(req.query)

    answer = None
    if service:
        prompt = build_prompt(req.query, service)
        answer = call_gemini(prompt)
    if not answer:
        answer = fallback_answer(req.query, service)

    response_time_ms = int((time.time() - start) * 1000)
    entry = {
        "session_id": req.session_id or str(uuid.uuid4()),
        "user_id": current_user["id"] if current_user else None,
        "query": req.query,
        "matched_service_id": service["id"] if service else None,
        "answer": answer,
        "confidence_score": confidence,
        "response_time_ms": response_time_ms,
    }
    chat_id = STORE.add_chat(entry)

    return {
        "answer": answer,
        "service": service,
        "confidence_score": confidence,
        "chat_id": chat_id,
    }


@app.get("/services")
def get_services(category: str | None = None, search: str | None = None):
    results = SERVICES
    if category:
        results = [s for s in results if (s.get("category") or "").lower() == category.lower()]
    if search:
        toks = set(tokenize(search))
        results = [s for s in results if toks & set(tokenize((s["service_name"] or "") + " " + (s.get("keywords") or "")))]
    return {"count": len(results), "services": results}


@app.get("/departments")
def get_departments():
    depts = {}
    for s in SERVICES:
        depts.setdefault(s["department"], {"department": s["department"], "building": s["building"], "services": 0})
        depts[s["department"]]["services"] += 1
    return list(depts.values())


class FeedbackRequest(BaseModel):
    chat_id: int
    rating: int
    comment: str | None = None


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    STORE.add_feedback(req.chat_id, req.rating, req.comment)
    return {"status": "ok"}


@app.get("/analytics")
def analytics():
    return STORE.get_analytics(SERVICES_BY_ID)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "backend": BACKEND,
        "services_loaded": len(SERVICES),
        "retrieval_mode": "hybrid-semantic" if SEMANTIC_ENABLED else "keyword-only",
        "services_embedded": len(SERVICE_EMBEDDINGS),
    }


# ---- Serve the frontend (single page app) ----
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
