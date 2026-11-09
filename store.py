"""앱 기록용 SQLite. 에이전트 진행 상태는 체크포인터(checkpoints.sqlite)에 따로 저장된다.

- submissions: 들어온 추천 (thread_id = 추천 id)
- published:   시상식 화면에 공개된 상. publish 노드만 여기에 쓴다 (= 바깥으로 나가는 일)
- decisions:   담당자가 내린 결정과 사유
"""
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
# AWARD_EXAMPLE=1 이면 가상 이름 예시로 돌고 기록도 따로 둔다 (REPORT 캡처용, 실명 데모와 섞이지 않게)
EXAMPLE = os.getenv("AWARD_EXAMPLE") == "1"
# AWARD_DB_DIR 을 주면 그 폴더에 기록을 둔다 (시험용 임시 폴더)
DB_DIR = os.getenv("AWARD_DB_DIR") or (os.path.join(DATA, "example") if EXAMPLE else DATA)
DB_PATH = os.path.join(DB_DIR, "app.sqlite")
CHECKPOINT_PATH = os.path.join(DB_DIR, "checkpoints.sqlite")
LOCK = threading.Lock()  # 예시 30건을 동시에 넣을 때 쓰기가 겹치지 않게


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS submissions (
        id TEXT PRIMARY KEY, created TEXT, from_name TEXT, to_name TEXT, to_role TEXT, reason TEXT);
    CREATE TABLE IF NOT EXISTS published (
        id TEXT PRIMARY KEY, to_name TEXT, title TEXT, citation TEXT, via TEXT, published_at TEXT);
    CREATE TABLE IF NOT EXISTS decisions (
        n INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, action TEXT, detail TEXT, approver TEXT, at TEXT);
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    return con


def add_submission(con, from_name, to_name, to_role, reason):
    sid = "R" + uuid.uuid4().hex[:8]
    with LOCK:
        con.execute("INSERT INTO submissions VALUES (?,?,?,?,?,?)", (sid, _now(), from_name, to_name, to_role, reason))
        con.commit()
    return sid


def submissions(con):
    return [dict(r) for r in con.execute("SELECT * FROM submissions ORDER BY created, id")]


def count_from(con, from_name):
    return con.execute("SELECT COUNT(*) FROM submissions WHERE from_name=?", (from_name,)).fetchone()[0]


def publish(con, sid, to_name, title, citation, via):
    # 같은 건이 두 번 공개되지 않도록 id로 덮어쓴다 (노드가 재실행돼도 한 번만 남는다)
    with LOCK:
        con.execute("INSERT OR REPLACE INTO published VALUES (?,?,?,?,?,?)", (sid, to_name, title, citation, via, _now()))
        con.commit()


def published(con):
    return [dict(r) for r in con.execute("SELECT * FROM published ORDER BY published_at, id")]


def log_decision(con, sid, action, detail, approver):
    with LOCK:
        con.execute("INSERT INTO decisions (id, action, detail, approver, at) VALUES (?,?,?,?,?)",
                    (sid, action, json.dumps(detail, ensure_ascii=False), approver, _now()))
        con.commit()


def decisions(con):
    rows = [dict(r) for r in con.execute("SELECT * FROM decisions ORDER BY n")]
    for r in rows:
        r["detail"] = json.loads(r["detail"])
    return rows


def reset(con):
    """기록만 지운다. meta(예시를 처음 한 번 넣었다는 표시)는 남겨서 다시 자동으로 채우지 않는다."""
    with LOCK:
        con.executescript("DELETE FROM submissions; DELETE FROM published; DELETE FROM decisions;")
        con.commit()


def get_meta(con, key):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(con, key, value):
    with LOCK:
        con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))
        con.commit()


def has_samples(con, samples):
    """예시 추천이 전부 들어가 있는지 (추천한 사람, 받는 사람, 이유가 같은 추천이 있는지로 본다)."""
    have = {(r["from_name"], r["to_name"], r["reason"]) for r in submissions(con)}
    return all((x["from"], x["to"], x["reason"]) in have for x in samples)
