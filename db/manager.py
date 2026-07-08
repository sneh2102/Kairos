"""SQLite persistence — JobsDB (scraped/screened, in-progress) and AppliedDB
(final applied jobs, full historical record). Port of the old project's
db_manager.py with the openpyxl/Excel-mirroring dropped: SQLite is the only
source of truth here.
"""
import sqlite3
from pathlib import Path

import config

JOBS_COLS = [
    "ai_recommendation", "company", "title", "link", "location", "site",
    "years_required", "role_level", "skills_match_pct", "matched_skills",
    "missing_skills", "reasoning", "description", "posted_date", "application_status",
]

# Columns added after the initial release — migrated in with ALTER TABLE so
# existing jobs.db/applied.db files on disk don't need to be deleted.
JOBS_MIGRATED_COLS = {
    "latex_content": "TEXT DEFAULT ''",
    "cover_letter_content": "TEXT DEFAULT ''",
    "ats_score": "INTEGER DEFAULT 0",
    "resume_path": "TEXT DEFAULT ''",
    "cover_path": "TEXT DEFAULT ''",
}

APPLIED_MIGRATED_COLS = {
    "years_required": "TEXT DEFAULT ''",
    "role_level": "TEXT DEFAULT ''",
    "skills_match_pct": "TEXT DEFAULT ''",
    "matched_skills": "TEXT DEFAULT ''",
    "missing_skills": "TEXT DEFAULT ''",
    "reasoning": "TEXT DEFAULT ''",
    "description": "TEXT DEFAULT ''",
    "posted_date": "TEXT DEFAULT ''",
    "site": "TEXT DEFAULT ''",
    "ai_recommendation": "TEXT DEFAULT ''",
}


def _migrate(con: sqlite3.Connection, table: str, columns: dict[str, str]):
    existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    for name, decl in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


class JobsDB:
    def __init__(self, path: str | None = None):
        # every caller (server.py, scrape_graph.py, apply_graph.py, main.py)
        # must land on the SAME file — a bare relative default here previously
        # resolved against the process's cwd, which differs from DATA_DIR in
        # the packaged app, silently splitting scraped jobs across two DBs
        self.path = path or str(config.DATA_DIR / "jobs.db")
        self._init_schema()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_schema(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    ai_recommendation  TEXT,
                    company            TEXT,
                    title              TEXT,
                    link               TEXT UNIQUE,
                    location           TEXT,
                    site               TEXT,
                    years_required     TEXT,
                    role_level         TEXT,
                    skills_match_pct   TEXT,
                    matched_skills     TEXT,
                    missing_skills     TEXT,
                    reasoning          TEXT,
                    description        TEXT,
                    posted_date        TEXT,
                    application_status TEXT DEFAULT 'pending',
                    created_at         TEXT DEFAULT (datetime('now'))
                )
            """)
            _migrate(con, "jobs", JOBS_MIGRATED_COLS)

    def upsert(self, row: dict):
        row = {k.lower(): v for k, v in row.items()}
        link = row.get("link", "").strip()
        if not link:
            raise ValueError("upsert requires a non-empty 'link'")
        cols = [c for c in JOBS_COLS if c in row]
        values = [str(row[c]) for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "link")
        with self._connect() as con:
            con.execute(
                f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(link) DO UPDATE SET {updates}",
                values,
            )

    def set_verdict(self, job_id: int, verdict: str):
        with self._connect() as con:
            con.execute("UPDATE jobs SET ai_recommendation=? WHERE id=?", (verdict, job_id))

    def save_build_artifacts(self, job_id: int, latex_content: str, cover_letter_content: str,
                              ats_score: int, resume_path: str, cover_path: str):
        with self._connect() as con:
            con.execute(
                "UPDATE jobs SET latex_content=?, cover_letter_content=?, ats_score=?, "
                "resume_path=?, cover_path=? WHERE id=?",
                (latex_content, cover_letter_content, ats_score, resume_path, cover_path, job_id),
            )

    def get_by_id(self, job_id: int) -> dict | None:
        rows = self._rows_where("id=?", (job_id,))
        return rows[0] if rows else None

    def get_by_link(self, link: str) -> dict | None:
        rows = self._rows_where("link=?", (link,))
        return rows[0] if rows else None

    def delete_by_link(self, link: str):
        with self._connect() as con:
            con.execute("DELETE FROM jobs WHERE link=?", (link,))

    def delete_by_id(self, job_id: int):
        with self._connect() as con:
            con.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def delete_by_verdict(self, verdict: str) -> int:
        with self._connect() as con:
            cur = con.execute("DELETE FROM jobs WHERE lower(ai_recommendation)=?", (verdict.lower(),))
            return cur.rowcount

    def delete_not_applied(self) -> int:
        """Applied jobs are physically moved to applied.db (see mark_applied),
        so every row left in jobs.db is, by construction, not applied — this
        clears the whole pending queue while leaving applied.db untouched."""
        with self._connect() as con:
            cur = con.execute("DELETE FROM jobs WHERE lower(coalesce(application_status,'')) != 'applied'")
            return cur.rowcount

    def delete_all(self) -> int:
        with self._connect() as con:
            cur = con.execute("DELETE FROM jobs")
            return cur.rowcount

    def delete_by_companies(self, companies: list[str]) -> int:
        """Removes every job whose company contains one of the given names —
        case-insensitive substring, the same match rule the screener's
        blacklist uses."""
        terms = [c.strip().lower() for c in companies if c and c.strip()]
        if not terms:
            return 0
        where = " OR ".join("instr(lower(company), ?) > 0" for _ in terms)
        with self._connect() as con:
            cur = con.execute(f"DELETE FROM jobs WHERE {where}", terms)
            return cur.rowcount

    def get_all_urls(self) -> set[str]:
        with self._connect() as con:
            return {r[0] for r in con.execute("SELECT link FROM jobs")}

    def get_buildable(self, verdicts: tuple[str, ...] = ("yes",)) -> list[dict]:
        """Jobs matching the given verdicts that don't have a resume built yet — what the
        Build tab processes in bulk."""
        placeholders = ",".join("?" for _ in verdicts)
        return self._rows_where(
            f"lower(ai_recommendation) IN ({placeholders}) AND (latex_content IS NULL OR latex_content='') "
            "ORDER BY id ASC",
            tuple(v.lower() for v in verdicts),
        )

    def search(self, status: str = "", verdict: str = "", q: str = "") -> list[dict]:
        clauses, params = [], []
        if status:
            clauses.append("application_status=?")
            params.append(status)
        if verdict:
            clauses.append("lower(ai_recommendation)=?")
            params.append(verdict.lower())
        if q:
            clauses.append("(lower(title) LIKE ? OR lower(company) LIKE ?)")
            params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])
        where = " AND ".join(clauses) if clauses else "1=1"
        return self._rows_where(f"{where} ORDER BY id DESC", tuple(params))

    def verdict_counts(self) -> dict[str, int]:
        with self._connect() as con:
            rows = con.execute("SELECT lower(ai_recommendation), COUNT(*) FROM jobs GROUP BY 1").fetchall()
            return {r[0]: r[1] for r in rows}

    def count(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def _rows_where(self, where_clause: str, params: tuple = ()) -> list[dict]:
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(f"SELECT * FROM jobs WHERE {where_clause}", params).fetchall()
            return [dict(r) for r in rows]


class AppliedDB:
    def __init__(self, path: str | None = None):
        self.path = path or str(config.DATA_DIR / "applied.db")
        self._init_schema()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_schema(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS applied_jobs (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    company              TEXT,
                    title                TEXT,
                    job_url              TEXT,
                    location             TEXT,
                    applied_date         TEXT,
                    ats_score            INTEGER DEFAULT 0,
                    status               TEXT DEFAULT 'applied',
                    tex_content          TEXT,
                    cover_letter_content TEXT,
                    resume_path          TEXT,
                    cover_path           TEXT,
                    created_at           TEXT DEFAULT (datetime('now'))
                )
            """)
            _migrate(con, "applied_jobs", APPLIED_MIGRATED_COLS)

    def add_from_job(self, job: dict, applied_date: str) -> int:
        """Copies a full JobsDB row (scraped metadata + any build artifacts)
        into applied_jobs — called when a job is marked Applied."""
        data = {
            "company": job.get("company", ""), "title": job.get("title", ""),
            "job_url": job.get("link", ""), "location": job.get("location", ""),
            "applied_date": applied_date, "ats_score": job.get("ats_score", 0) or 0,
            "status": "applied", "tex_content": job.get("latex_content", "") or "",
            "cover_letter_content": job.get("cover_letter_content", "") or "",
            "resume_path": job.get("resume_path", "") or "", "cover_path": job.get("cover_path", "") or "",
            "years_required": job.get("years_required", ""), "role_level": job.get("role_level", ""),
            "skills_match_pct": job.get("skills_match_pct", ""), "matched_skills": job.get("matched_skills", ""),
            "missing_skills": job.get("missing_skills", ""), "reasoning": job.get("reasoning", ""),
            "description": job.get("description", ""), "posted_date": job.get("posted_date", ""),
            "site": job.get("site", ""), "ai_recommendation": job.get("ai_recommendation", ""),
        }
        cols = list(data.keys())
        placeholders = ", ".join("?" for _ in cols)
        with self._connect() as con:
            cur = con.execute(
                f"INSERT INTO applied_jobs ({', '.join(cols)}) VALUES ({placeholders})",
                [data[c] for c in cols],
            )
            return cur.lastrowid

    def add(self, data: dict) -> int:
        cols = [c for c in (
            "company", "title", "job_url", "location", "applied_date", "ats_score",
            "status", "tex_content", "cover_letter_content", "resume_path", "cover_path",
        ) if c in data]
        placeholders = ", ".join("?" for _ in cols)
        with self._connect() as con:
            cur = con.execute(
                f"INSERT INTO applied_jobs ({', '.join(cols)}) VALUES ({placeholders})",
                [data[c] for c in cols],
            )
            return cur.lastrowid

    def get_urls(self) -> set[str]:
        with self._connect() as con:
            return {r[0] for r in con.execute("SELECT job_url FROM applied_jobs")}

    def get_applied_pairs(self) -> set[tuple[str, str]]:
        with self._connect() as con:
            return {(c.lower(), t.lower()) for c, t in con.execute("SELECT company, title FROM applied_jobs")}

    def get_all(self) -> list[dict]:
        """Excludes tex/cover_letter content — those are large; fetch via get_by_id."""
        cols = ("id, company, title, job_url, location, applied_date, ats_score, status, "
                "resume_path, cover_path, role_level, skills_match_pct")
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(f"SELECT {cols} FROM applied_jobs ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def get_by_id(self, applied_id: int) -> dict | None:
        with self._connect() as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT * FROM applied_jobs WHERE id=?", (applied_id,)).fetchone()
            return dict(row) if row else None

    def update_tex(self, applied_id: int, tex_content: str, resume_path: str):
        with self._connect() as con:
            con.execute("UPDATE applied_jobs SET tex_content=?, resume_path=? WHERE id=?",
                        (tex_content, resume_path, applied_id))

    def delete_by_id(self, applied_id: int):
        with self._connect() as con:
            con.execute("DELETE FROM applied_jobs WHERE id=?", (applied_id,))

    def applied_by_date(self) -> list[tuple[str, int]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT applied_date, COUNT(*) FROM applied_jobs GROUP BY applied_date ORDER BY applied_date"
            ).fetchall()
            return list(rows)

    def ats_scores(self) -> list[int]:
        with self._connect() as con:
            return [r[0] for r in con.execute("SELECT ats_score FROM applied_jobs ORDER BY id")]

    def count(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM applied_jobs").fetchone()[0]


def ensure_output_dirs(base: str):
    Path(base).mkdir(parents=True, exist_ok=True)


def mark_applied(jobs_db: JobsDB, applied_db: AppliedDB, job_id: int, applied_date: str) -> dict | None:
    """Moves a job from jobs.db to applied.db, carrying over everything
    scraped/generated so far (JD, location, years, latex, cover letter, ...)."""
    job = jobs_db.get_by_id(job_id)
    if not job:
        return None
    applied_id = applied_db.add_from_job(job, applied_date)
    jobs_db.delete_by_id(job_id)
    return applied_db.get_by_id(applied_id)


def unmark_applied(jobs_db: JobsDB, applied_db: AppliedDB, applied_id: int) -> dict | None:
    """Moves a job back from applied.db to jobs.db (undo)."""
    row = applied_db.get_by_id(applied_id)
    if not row:
        return None
    jobs_db.upsert({
        "ai_recommendation": row.get("ai_recommendation", "") or "yes", "company": row.get("company", ""),
        "title": row.get("title", ""), "link": row.get("job_url", ""), "location": row.get("location", ""),
        "site": row.get("site", ""), "years_required": row.get("years_required", ""),
        "role_level": row.get("role_level", ""), "skills_match_pct": row.get("skills_match_pct", ""),
        "matched_skills": row.get("matched_skills", ""), "missing_skills": row.get("missing_skills", ""),
        "reasoning": row.get("reasoning", ""), "description": row.get("description", ""),
        "posted_date": row.get("posted_date", ""),
    })
    job = jobs_db.get_by_link(row.get("job_url", ""))
    if job:
        jobs_db.save_build_artifacts(
            job["id"], row.get("tex_content", "") or "", row.get("cover_letter_content", "") or "",
            row.get("ats_score", 0) or 0, row.get("resume_path", "") or "", row.get("cover_path", "") or "",
        )
    applied_db.delete_by_id(applied_id)
    return job
