import os
import sqlite3
from urllib.parse import urlparse

import psycopg2


def get_database_url():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        if os.environ.get("VERCEL") == "1":
            raise RuntimeError("Set DATABASE_URL to a persistent PostgreSQL database on Vercel.")
        database_url = "sqlite:///college_attendance_app.db"
        os.environ["DATABASE_URL"] = database_url
    if os.environ.get("VERCEL") == "1" and database_url.startswith("sqlite"):
        raise RuntimeError("SQLite is not persistent on Vercel. Set DATABASE_URL to a persistent PostgreSQL database.")
    return database_url


def get_local_db_path():
    database_url = get_database_url()
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/") or "college_attendance_app.db"
    if not os.path.isabs(db_name):
        db_name = os.path.join(os.path.dirname(__file__), db_name)
    return db_name


def setup_database():
    database_url = get_database_url()
    if database_url.startswith("sqlite"):
        conn = sqlite3.connect(get_local_db_path())
        try:
            with conn:
                conn.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, college_name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, total_periods INTEGER DEFAULT 6)")
                conn.execute("CREATE TABLE IF NOT EXISTS teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id TEXT NOT NULL, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, subject TEXT NOT NULL, college_id INTEGER, UNIQUE(teacher_id, college_id))")
                conn.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, roll_no TEXT NOT NULL, student_name TEXT NOT NULL, father_name TEXT NOT NULL, phone_number TEXT NOT NULL, program TEXT NOT NULL, part TEXT NOT NULL, college_id INTEGER, UNIQUE(roll_no, college_id))")
                conn.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, student_roll TEXT, attendance_date TEXT, period_no INTEGER NOT NULL, status TEXT, marked_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, college_id INTEGER)")
                conn.execute("INSERT OR IGNORE INTO admins (college_name, username, password, total_periods) VALUES (?, ?, ?, ?)", ("Punjab College", "admin1", "pc123", 8))
                conn.execute("INSERT OR IGNORE INTO admins (college_name, username, password, total_periods) VALUES (?, ?, ?, ?)", ("Superior College", "admin2", "sc123", 5))
        finally:
            conn.close()
        print("Database schema is ready; existing records were preserved.")
        return

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id SERIAL PRIMARY KEY,
                    college_name TEXT NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    total_periods INTEGER DEFAULT 6
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS teachers (
                    id SERIAL PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE,
                    UNIQUE(teacher_id, college_id)
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id SERIAL PRIMARY KEY,
                    roll_no TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    father_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    program TEXT NOT NULL,
                    part TEXT NOT NULL,
                    college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE,
                    UNIQUE(roll_no, college_id)
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    student_roll TEXT,
                    attendance_date TEXT,
                    period_no INTEGER NOT NULL,
                    status TEXT,
                    marked_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_roll, college_id) REFERENCES students(roll_no, college_id) ON DELETE CASCADE
                )
                """)
                cursor.execute(
                    "INSERT INTO admins (college_name, username, password, total_periods) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    ("Punjab College", "admin1", "pc123", 8)
                )
                cursor.execute(
                    "INSERT INTO admins (college_name, username, password, total_periods) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    ("Superior College", "admin2", "sc123", 5)
                )
    finally:
        conn.close()
    print("Database schema is ready; existing records were preserved.")


if __name__ == "__main__":
    setup_database()
