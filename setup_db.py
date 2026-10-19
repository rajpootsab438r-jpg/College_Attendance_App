import os
import sqlite3
from urllib.parse import urlparse

import psycopg2
from werkzeug.security import generate_password_hash


ACADEMIC_PROGRAM_SEEDS = (
    ('FA', 'FA (Arts)', 'Intermediate', ('Part-1', 'Part-2')),
    ('FA IT', 'FA IT (Arts in IT)', 'Intermediate', ('Part-1', 'Part-2')),
    ('FSc Pre-Medical', 'FSc Pre-Medical', 'Intermediate', ('Part-1', 'Part-2')),
    ('FSc Pre-Engineering', 'FSc Pre-Engineering', 'Intermediate', ('Part-1', 'Part-2')),
    ('FSc', 'FSc (Legacy)', 'Intermediate', ('Part-1', 'Part-2')),
    ('ICS', 'ICS (Computer Science)', 'Intermediate', ('Part-1', 'Part-2')),
    ('I.Com', 'I.Com (Commerce)', 'Intermediate', ('Part-1', 'Part-2')),
    ('General Science', 'General Science', 'Intermediate', ('Part-1', 'Part-2')),
    ('BS-CS', 'BS-CS (Computer Science)', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS-IT', 'BS-IT (Information Technology)', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Commerce', 'BS Commerce', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS English', 'BS English', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Chemistry', 'BS Chemistry', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Physics', 'BS Physics', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Mathematics', 'BS Mathematics', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Zoology', 'BS Zoology', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Botany', 'BS Botany', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BS Psychology', 'BS Psychology', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('BBA', 'BBA (Business Administration)', 'BS Degree', tuple(f'Semester-{n}' for n in range(1, 9))),
    ('DIT', 'DIT (Diploma in Information Technology)', 'Professional Diploma', ('Part-1', 'Part-2')),
    ('D.Com', 'D.Com (Diploma in Commerce)', 'Professional Diploma', ('Part-1', 'Part-2')),
)
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
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                conn.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, college_name TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '', username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, total_periods INTEGER DEFAULT 6)")
                admin_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(admins)").fetchall()
                }
                if 'display_name' not in admin_columns:
                    conn.execute("ALTER TABLE admins ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
                conn.execute("UPDATE admins SET display_name = college_name WHERE display_name = ''")
                conn.execute("CREATE TABLE IF NOT EXISTS developer_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
                if not conn.execute("SELECT 1 FROM developer_accounts LIMIT 1").fetchone():
                    conn.execute(
                        "INSERT INTO developer_accounts (username, password) VALUES (?, ?)",
                        ("Cukur", generate_password_hash("Cukur301r"))
                    )
                conn.execute("CREATE TABLE IF NOT EXISTS teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id TEXT NOT NULL, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, subject TEXT NOT NULL, profile_image TEXT, college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE, UNIQUE(teacher_id, college_id))")
                conn.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, roll_no TEXT NOT NULL, student_name TEXT NOT NULL, father_name TEXT NOT NULL, phone_number TEXT NOT NULL, program TEXT NOT NULL, part TEXT NOT NULL, profile_image TEXT, college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE, UNIQUE(roll_no, college_id))")
                for table_name in ('teachers', 'students'):
                    columns = {
                        row[1] for row in
                        conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                    }
                    if 'profile_image' not in columns:
                        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN profile_image TEXT")
                conn.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, student_roll TEXT, attendance_date TEXT, period_no INTEGER NOT NULL, status TEXT, marked_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, client_timestamp TEXT, college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE, FOREIGN KEY (student_roll, college_id) REFERENCES students(roll_no, college_id) ON DELETE CASCADE)")
                attendance_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(attendance)").fetchall()
                }
                if 'client_timestamp' not in attendance_columns:
                    conn.execute("ALTER TABLE attendance ADD COLUMN client_timestamp TEXT")
                conn.execute("CREATE TABLE IF NOT EXISTS sync_operations (operation_id TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                conn.execute("CREATE TABLE IF NOT EXISTS global_notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT NOT NULL, image_path TEXT, college_id INTEGER REFERENCES admins(id) ON DELETE SET NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                notice_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(global_notifications)").fetchall()
                }
                if 'college_id' not in notice_columns:
                    conn.execute(
                        "ALTER TABLE global_notifications ADD COLUMN college_id INTEGER REFERENCES admins(id) ON DELETE SET NULL"
                    )
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS developer_releases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        image_data TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                release_columns = {
                    row[1] for row in
                    conn.execute("PRAGMA table_info(developer_releases)").fetchall()
                }
                if 'image_data' not in release_columns:
                    conn.execute("ALTER TABLE developer_releases ADD COLUMN image_data TEXT")
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS admins_delete_cascade_legacy
                    AFTER DELETE ON admins
                    BEGIN
                        DELETE FROM attendance WHERE college_id = OLD.id;
                        DELETE FROM teachers WHERE college_id = OLD.id;
                        DELETE FROM students WHERE college_id = OLD.id;
                        UPDATE global_notifications SET college_id = NULL
                        WHERE college_id = OLD.id;
                    END;
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS students_delete_cascade_legacy
                    AFTER DELETE ON students
                    BEGIN
                        DELETE FROM attendance
                        WHERE student_roll = OLD.roll_no
                          AND college_id = OLD.college_id;
                    END;
                """)
                conn.execute("CREATE TABLE IF NOT EXISTS academic_programs (program_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, level TEXT NOT NULL, parts TEXT NOT NULL)")
                for program_key, display_name, level, parts in ACADEMIC_PROGRAM_SEEDS:
                    conn.execute(
                        "INSERT INTO academic_programs (program_key, display_name, level, parts) "
                        "VALUES (?, ?, ?, ?) ON CONFLICT (program_key) DO UPDATE SET "
                        "display_name = excluded.display_name, level = excluded.level, "
                        "parts = excluded.parts",
                        (program_key, display_name, level, ','.join(parts))
                    )
                conn.execute("INSERT OR IGNORE INTO admins (college_name, display_name, username, password, total_periods) VALUES (?, ?, ?, ?, ?)", ("Punjab College", "Punjab College Admin", "admin1", "pc123", 8))
                conn.execute("INSERT OR IGNORE INTO admins (college_name, display_name, username, password, total_periods) VALUES (?, ?, ?, ?, ?)", ("Superior College", "Superior College Admin", "admin2", "sc123", 5))
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
                    display_name TEXT NOT NULL DEFAULT '',
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    total_periods INTEGER DEFAULT 6
                )
                """)
                cursor.execute("ALTER TABLE admins ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT ''")
                cursor.execute("UPDATE admins SET display_name = college_name WHERE display_name = ''")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS developer_accounts (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
                """)
                cursor.execute("SELECT 1 FROM developer_accounts LIMIT 1")
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO developer_accounts (username, password) VALUES (%s, %s)",
                        ("Cukur", generate_password_hash("Cukur301r"))
                    )
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS teachers (
                    id SERIAL PRIMARY KEY,
                    teacher_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    profile_image TEXT,
                    college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE,
                    UNIQUE(teacher_id, college_id)
                )
                """)
                cursor.execute("ALTER TABLE teachers ADD COLUMN IF NOT EXISTS profile_image TEXT")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    id SERIAL PRIMARY KEY,
                    roll_no TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    father_name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    program TEXT NOT NULL,
                    part TEXT NOT NULL,
                    profile_image TEXT,
                    college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE,
                    UNIQUE(roll_no, college_id)
                )
                """)
                cursor.execute("ALTER TABLE students ADD COLUMN IF NOT EXISTS profile_image TEXT")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    student_roll TEXT,
                    attendance_date TEXT,
                    period_no INTEGER NOT NULL,
                    status TEXT,
                    marked_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    client_timestamp TEXT,
                    college_id INTEGER REFERENCES admins(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_roll, college_id) REFERENCES students(roll_no, college_id) ON DELETE CASCADE
                )
                """)
                cursor.execute("ALTER TABLE attendance ADD COLUMN IF NOT EXISTS client_timestamp TEXT")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS sync_operations (
                    operation_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS global_notifications (
                    id SERIAL PRIMARY KEY,
                    message TEXT NOT NULL,
                    image_path TEXT,
                    college_id INTEGER REFERENCES admins(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute(
                    "ALTER TABLE global_notifications ADD COLUMN IF NOT EXISTS "
                    "college_id INTEGER REFERENCES admins(id) ON DELETE SET NULL"
                )
                cursor.execute(
                    "ALTER TABLE global_notifications ALTER COLUMN image_path TYPE TEXT"
                )
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS developer_releases (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    image_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                cursor.execute(
                    "ALTER TABLE developer_releases ADD COLUMN IF NOT EXISTS image_data TEXT"
                )
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS academic_programs (
                    program_key TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    level TEXT NOT NULL,
                    parts TEXT NOT NULL
                )
                """)
                for program_key, display_name, level, parts in ACADEMIC_PROGRAM_SEEDS:
                    cursor.execute(
                        "INSERT INTO academic_programs (program_key, display_name, level, parts) "
                        "VALUES (%s, %s, %s, %s) ON CONFLICT (program_key) DO UPDATE SET "
                        "display_name = EXCLUDED.display_name, level = EXCLUDED.level, "
                        "parts = EXCLUDED.parts",
                        (program_key, display_name, level, ','.join(parts))
                    )
                cursor.execute(
                    "INSERT INTO admins (college_name, display_name, username, password, total_periods) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    ("Punjab College", "Punjab College Admin", "admin1", "pc123", 8)
                )
                cursor.execute(
                    "INSERT INTO admins (college_name, display_name, username, password, total_periods) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    ("Superior College", "Superior College Admin", "admin2", "sc123", 5)
                )
    finally:
        conn.close()
    print("Database schema is ready; existing records were preserved.")


if __name__ == "__main__":
    setup_database()
