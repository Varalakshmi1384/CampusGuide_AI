"""
Data layer for CampusGuide AI.

If DATABASE_URL is set (Supabase/Postgres connection string), everything —
services, chat history, feedback, users, sessions — is persisted in real
PostgreSQL tables. If it's not set, or the connection fails for any reason,
the app automatically falls back to the original in-memory behaviour so a
demo never breaks because of a database hiccup.
"""
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SESSION_TTL_HOURS = 24 * 7  # 7 days

# ---------------------------------------------------------------- passwords
def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex). PBKDF2-SHA256, stdlib only (no compiled deps)."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    _, computed = hash_password(password, salt_hex)
    return secrets.compare_digest(computed, hash_hex)


# ------------------------------------------------------------- Postgres impl
class PostgresStore:
    def __init__(self, database_url: str):
        import psycopg2
        import psycopg2.extras
        from psycopg2.pool import SimpleConnectionPool

        self.psycopg2 = psycopg2
        self.extras = psycopg2.extras
        # Only force sslmode if the connection string doesn't already specify one
        # (Supabase URIs sometimes already include it — passing it twice raises an error).
        pool_kwargs = {"dsn": database_url}
        if "sslmode" not in database_url:
            pool_kwargs["sslmode"] = "require"
        self.pool = SimpleConnectionPool(1, 5, **pool_kwargs)
        self._init_schema()

    def _conn(self):
        return self.pool.getconn()

    def _put(self, conn):
        self.pool.putconn(conn)

    def _init_schema(self):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        registration_number TEXT,
                        password_salt TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS sessions (
                        token TEXT PRIMARY KEY,
                        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        created_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS services (
                        id INTEGER PRIMARY KEY,
                        service_name TEXT NOT NULL,
                        sample_query TEXT,
                        intent TEXT,
                        department TEXT,
                        building TEXT,
                        room_number TEXT,
                        fees TEXT,
                        office_hours TEXT,
                        processing_time TEXT,
                        is_online BOOLEAN,
                        required_documents JSONB,
                        procedure_steps JSONB,
                        contact_email TEXT,
                        portal_link TEXT,
                        rejection_policy TEXT,
                        keywords TEXT,
                        category TEXT,
                        priority TEXT,
                        status TEXT
                    );
                    CREATE TABLE IF NOT EXISTS chat_history (
                        chat_id SERIAL PRIMARY KEY,
                        session_id TEXT,
                        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        query TEXT NOT NULL,
                        matched_service_id INTEGER,
                        answer TEXT,
                        confidence_score REAL,
                        response_time_ms INTEGER,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS feedback (
                        id SERIAL PRIMARY KEY,
                        chat_id INTEGER,
                        rating INTEGER,
                        comment TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_history(created_at);
                    CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
                """)
                # Migration for databases created before this column existed
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS registration_number TEXT;")
            conn.commit()

            # seed services table from services.json exactly once
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM services;")
                count = cur.fetchone()[0]
            if count == 0:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                with open(os.path.join(base_dir, "services.json")) as f:
                    services = json.load(f)
                with conn.cursor() as cur:
                    for s in services:
                        cur.execute("""
                            INSERT INTO services (id, service_name, sample_query, intent, department,
                                building, room_number, fees, office_hours, processing_time, is_online,
                                required_documents, procedure_steps, contact_email, portal_link,
                                rejection_policy, keywords, category, priority, status)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            ON CONFLICT (id) DO NOTHING;
                        """, (
                            s["id"], s["service_name"], s.get("sample_query"), s.get("intent"),
                            s.get("department"), s.get("building"), s.get("room_number"), s.get("fees"),
                            s.get("office_hours"), s.get("processing_time"), s.get("is_online"),
                            self.extras.Json(s.get("required_documents") or []),
                            self.extras.Json(s.get("procedure_steps") or []),
                            s.get("contact_email"), s.get("portal_link"), s.get("rejection_policy"),
                            s.get("keywords"), s.get("category"), s.get("priority"), s.get("status"),
                        ))
                conn.commit()
        finally:
            self._put(conn)

    def _dictcur(self, conn):
        return conn.cursor(cursor_factory=self.extras.RealDictCursor)

    # ---- services
    def get_services(self):
        conn = self._conn()
        try:
            with self._dictcur(conn) as cur:
                cur.execute("SELECT * FROM services ORDER BY id;")
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._put(conn)

    # ---- chat / feedback
    def add_chat(self, entry: dict) -> int:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_history (session_id, user_id, query, matched_service_id,
                        answer, confidence_score, response_time_ms)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING chat_id;
                """, (entry["session_id"], entry.get("user_id"), entry["query"],
                      entry["matched_service_id"], entry["answer"], entry["confidence_score"],
                      entry["response_time_ms"]))
                chat_id = cur.fetchone()[0]
            conn.commit()
            return chat_id
        finally:
            self._put(conn)

    def add_feedback(self, chat_id: int, rating: int, comment: str | None):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO feedback (chat_id, rating, comment) VALUES (%s,%s,%s);",
                            (chat_id, rating, comment))
            conn.commit()
        finally:
            self._put(conn)

    def get_analytics(self, services_by_id: dict):
        conn = self._conn()
        try:
            with self._dictcur(conn) as cur:
                cur.execute("SELECT COUNT(*) AS c FROM chat_history;")
                total = cur.fetchone()["c"]
                cur.execute("SELECT COALESCE(AVG(confidence_score),0) AS a FROM chat_history;")
                avg_conf = round(float(cur.fetchone()["a"] or 0), 3)
                cur.execute("SELECT COALESCE(AVG(response_time_ms),0) AS a FROM chat_history;")
                avg_resp = round(float(cur.fetchone()["a"] or 0))
                cur.execute("SELECT COALESCE(AVG(rating),0) AS a FROM feedback;")
                avg_rating = round(float(cur.fetchone()["a"] or 0), 2)
                cur.execute("SELECT COUNT(*) AS c FROM chat_history WHERE matched_service_id IS NULL;")
                unanswered = cur.fetchone()["c"]
                cur.execute("""
                    SELECT matched_service_id, COUNT(*) AS c FROM chat_history
                    WHERE matched_service_id IS NOT NULL
                    GROUP BY matched_service_id ORDER BY c DESC LIMIT 5;
                """)
                top_rows = cur.fetchall()
                cur.execute("""
                    SELECT session_id, query, confidence_score, created_at
                    FROM chat_history ORDER BY created_at DESC LIMIT 10;
                """)
                recent = [dict(r) for r in cur.fetchall()]
        finally:
            self._put(conn)

        top_services, dept_counts = [], {}
        for row in top_rows:
            svc = services_by_id.get(row["matched_service_id"])
            if svc:
                top_services.append((svc["service_name"], row["c"]))
                dept_counts[svc["department"]] = dept_counts.get(svc["department"], 0) + row["c"]
        dept_breakdown = sorted(dept_counts.items(), key=lambda x: -x[1])[:10]

        for r in recent:
            r["created_at"] = r["created_at"].isoformat()

        return {
            "total_queries": total, "avg_confidence": avg_conf, "avg_response_time_ms": avg_resp,
            "avg_feedback_rating": avg_rating, "unanswered_count": unanswered,
            "top_services": top_services, "department_breakdown": dept_breakdown,
            "recent_queries": recent,
        }

    # ---- users / auth
    def create_user(self, name: str, email: str, salt_hex: str, hash_hex: str, registration_number: str | None = None) -> dict:
        conn = self._conn()
        try:
            with self._dictcur(conn) as cur:
                cur.execute("""
                    INSERT INTO users (name, email, registration_number, password_salt, password_hash)
                    VALUES (%s,%s,%s,%s,%s) RETURNING id, name, email, registration_number;
                """, (name, email, registration_number, salt_hex, hash_hex))
                row = dict(cur.fetchone())
            conn.commit()
            return row
        finally:
            self._put(conn)

    def get_user_by_email(self, email: str):
        conn = self._conn()
        try:
            with self._dictcur(conn) as cur:
                cur.execute("SELECT * FROM users WHERE email=%s;", (email,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put(conn)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=SESSION_TTL_HOURS)
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (%s,%s,%s);",
                            (token, user_id, expires))
            conn.commit()
            return token
        finally:
            self._put(conn)

    def get_user_by_token(self, token: str):
        conn = self._conn()
        try:
            with self._dictcur(conn) as cur:
                cur.execute("""
                    SELECT u.id, u.name, u.email, u.registration_number FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.token=%s AND s.expires_at > NOW();
                """, (token,))
                row = cur.fetchone()
                return dict(row) if row else None
        finally:
            self._put(conn)

    def delete_session(self, token: str):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE token=%s;", (token,))
            conn.commit()
        finally:
            self._put(conn)


# ------------------------------------------------------------- in-memory impl
class MemoryStore:
    """Original demo behaviour — used automatically if DATABASE_URL isn't set
    or the Postgres connection fails, so the app never crashes on startup."""

    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, "services.json")) as f:
            self.services = json.load(f)
        self.chat_history = []
        self.feedback = []
        self.users = {}       # email -> user dict (with salt/hash)
        self.users_by_id = {}
        self.sessions = {}    # token -> (user_id, expires_at)
        self._next_user_id = 1

    def get_services(self):
        return self.services

    def add_chat(self, entry: dict) -> int:
        entry = dict(entry)
        entry["chat_id"] = len(self.chat_history) + 1
        entry["created_at"] = datetime.utcnow()
        self.chat_history.append(entry)
        return entry["chat_id"]

    def add_feedback(self, chat_id: int, rating: int, comment: str | None):
        self.feedback.append({"chat_id": chat_id, "rating": rating, "comment": comment,
                               "created_at": datetime.utcnow()})

    def get_analytics(self, services_by_id: dict):
        total = len(self.chat_history)
        avg_conf = round(sum(c["confidence_score"] for c in self.chat_history) / total, 3) if total else 0
        avg_resp = round(sum(c["response_time_ms"] for c in self.chat_history) / total) if total else 0
        avg_rating = round(sum(f["rating"] for f in self.feedback) / len(self.feedback), 2) if self.feedback else 0

        from collections import Counter
        service_counts, dept_counts = Counter(), Counter()
        for c in self.chat_history:
            if c["matched_service_id"]:
                svc = services_by_id.get(c["matched_service_id"])
                if svc:
                    service_counts[svc["service_name"]] += 1
                    dept_counts[svc["department"]] += 1

        recent = list(reversed(self.chat_history[-10:]))
        recent = [{"session_id": r["session_id"], "query": r["query"],
                   "confidence_score": r["confidence_score"],
                   "created_at": r["created_at"].isoformat()} for r in recent]

        return {
            "total_queries": total, "avg_confidence": avg_conf, "avg_response_time_ms": avg_resp,
            "avg_feedback_rating": avg_rating,
            "unanswered_count": sum(1 for c in self.chat_history if c["matched_service_id"] is None),
            "top_services": service_counts.most_common(5),
            "department_breakdown": dept_counts.most_common(10),
            "recent_queries": recent,
        }

    def create_user(self, name: str, email: str, salt_hex: str, hash_hex: str, registration_number: str | None = None) -> dict:
        if email in self.users:
            raise ValueError("exists")
        user = {"id": self._next_user_id, "name": name, "email": email,
                "registration_number": registration_number,
                "password_salt": salt_hex, "password_hash": hash_hex}
        self.users[email] = user
        self.users_by_id[user["id"]] = user
        self._next_user_id += 1
        return {"id": user["id"], "name": name, "email": email, "registration_number": registration_number}

    def get_user_by_email(self, email: str):
        return self.users.get(email)

    def create_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token] = (user_id, time.time() + SESSION_TTL_HOURS * 3600)
        return token

    def get_user_by_token(self, token: str):
        entry = self.sessions.get(token)
        if not entry:
            return None
        user_id, expires = entry
        if time.time() > expires:
            del self.sessions[token]
            return None
        user = self.users_by_id.get(user_id)
        if not user:
            return None
        return {"id": user["id"], "name": user["name"], "email": user["email"],
                "registration_number": user.get("registration_number")}

    def delete_session(self, token: str):
        self.sessions.pop(token, None)


# ------------------------------------------------------------------ factory
def build_store():
    """Returns (store, backend_name). Always succeeds — falls back to memory
    on any connection error so the deploy can never crash on startup."""
    if DATABASE_URL:
        try:
            return PostgresStore(DATABASE_URL), "postgres"
        except Exception as e:
            print(f"[store] DATABASE_URL set but Postgres connection failed, "
                  f"falling back to in-memory store: {e}")
    return MemoryStore(), "memory"
