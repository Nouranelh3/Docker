import os
import time
from contextlib import closing

import psycopg2
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "devsecret")

DB = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "name": os.getenv("DB_NAME", "appdb"),
    "user": os.getenv("DB_USER", "appuser"),
    "pass": os.getenv("DB_PASS", "changeme123"),
}


def get_conn():
    return psycopg2.connect(
        host=DB["host"],
        port=DB["port"],
        dbname=DB["name"],
        user=DB["user"],
        password=DB["pass"],
        connect_timeout=3,
    )


def init_db(retries=10):
    for attempt in range(retries):
        try:
            with closing(get_conn()) as conn:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS tasks (
                                id SERIAL PRIMARY KEY,
                                title TEXT NOT NULL,
                                done BOOLEAN NOT NULL DEFAULT FALSE,
                                created_at TIMESTAMP NOT NULL DEFAULT NOW()
                            );
                        """)
            return
        except psycopg2.Error as error:
            print(
                f"[init_db] waiting for db... "
                f"({attempt + 1}/{retries}) {error}",
                flush=True,
            )
            if attempt == retries - 1:
                raise RuntimeError("DB not ready after retries") from error
            time.sleep(2)


@app.get("/health")
def health():
    try:
        with closing(get_conn()) as conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
        return {"ok": True}, 200
    except psycopg2.Error as error:
        return {"ok": False, "error": str(error)}, 500


@app.get("/tasks")
def list_tasks():
    with closing(get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, title, done, created_at "
                    "FROM tasks ORDER BY id;"
                )
                rows = cur.fetchall()

    return jsonify([
        {
            "id": row[0],
            "title": row[1],
            "done": row[2],
            "created_at": row[3].isoformat(),
        }
        for row in rows
    ])


@app.post("/tasks")
def add_task():
    data = request.get_json(force=True)
    if not isinstance(data, dict):
        return {"error": "JSON object required"}, 400

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        return {"error": "title required"}, 400

    with closing(get_conn()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tasks(title) VALUES (%s) RETURNING id;",
                    (title,),
                )
                new_id = cur.fetchone()[0]

    return {"id": new_id, "title": title, "done": False}, 201


# Gunicorn imports this module, so initialize the table on import.
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
