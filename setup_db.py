import os
import sqlite3
import psycopg2

def get_database_url():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        database_url = "sqlite:///college_attendance_app.db"
        os.environ["DATABASE_URL"] = database_url
    return database_url


def get_local_db_path():
    database_url = get_database_url()
    if not database_url.startswith("sqlite"):
        return None
    parsed = __import__("urllib.parse").parse.urlparse(database_url)
    db_name = parsed.path.lstrip("/") or "college_attendance_app.db"
    if not os.path.isabs(db_name):
        db_name = os.path.join(os.path.dirname(__file__), db_name)
    return db_name

def reset_and_setup_database():
    database_url = get_database_url()
    if database_url.startswith("sqlite"):
        db_path = get_local_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY AUTOINCREMENT, college_name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, total_periods INTEGER DEFAULT 6)")
        conn.execute("CREATE TABLE IF NOT EXISTS teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, teacher_id TEXT NOT NULL, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, subject TEXT NOT NULL, college_id INTEGER, UNIQUE(teacher_id, college_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, roll_no TEXT NOT NULL, student_name TEXT NOT NULL, father_name TEXT NOT NULL, phone_number TEXT NOT NULL, program TEXT NOT NULL, part TEXT NOT NULL, college_id INTEGER, UNIQUE(roll_no, college_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, student_roll TEXT, attendance_date TEXT, period_no INTEGER NOT NULL, status TEXT, marked_by TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, college_id INTEGER)")
        conn.execute("DELETE FROM attendance")
        conn.execute("DELETE FROM students")
        conn.execute("DELETE FROM teachers")
        conn.execute("DELETE FROM admins")
        conn.execute("INSERT INTO admins (college_name, username, password, total_periods) VALUES (?, ?, ?, ?)", ("Punjab College", "admin1", "pc123", 8))
        conn.execute("INSERT INTO admins (college_name, username, password, total_periods) VALUES (?, ?, ?, ?)", ("Superior College", "admin2", "sc123", 5))
        conn.commit()
        conn.close()
        print("?? Fresh Local SQLite Database Ready!")
        return
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    print("Resetting Neon PostgreSQL database with Period-Wise architecture...")
    
    cursor.execute("DROP TABLE IF EXISTS attendance CASCADE")
    cursor.execute("DROP TABLE IF EXISTS students CASCADE")
    cursor.execute("DROP TABLE IF EXISTS teachers CASCADE")
    cursor.execute("DROP TABLE IF EXISTS admins CASCADE")
    
    # 1. Admins Table (Har college ke total periods alag se save honge)
    cursor.execute("""
        CREATE TABLE admins (
            id SERIAL PRIMARY KEY,
            college_name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            total_periods INTEGER DEFAULT 6
        )
    """)
    
    # 2. Teachers Table
    cursor.execute("""
        CREATE TABLE teachers (
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
    
    # 3. Students Table
    cursor.execute("""
        CREATE TABLE students (
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
    
    # 4. Attendance Table (Ab har day aur har period ka record bilkul alag save hoga)
    cursor.execute("""
        CREATE TABLE attendance (
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
    
    # Initial Admin accounts with default 6 and 8 periods config
    cursor.execute("INSERT INTO admins (college_name, username, password, total_periods) VALUES (%s, %s, %s, %s)", 
                   ("Punjab College", "admin1", "pc123", 8))
    cursor.execute("INSERT INTO admins (college_name, username, password, total_periods) VALUES (%s, %s, %s, %s)", 
                   ("Superior College", "admin2", "sc123", 5))
        
    conn.commit()
    conn.close()
    print("🚀 Fresh Online Period-Wise PostgreSQL Database Ready!")

if __name__ == "__main__":
    reset_and_setup_database()
