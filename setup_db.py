import psycopg2

def reset_and_setup_database():
    DATABASE_URL = "postgresql://neondb_owner:npg_M7bJcCfdkN3e@ep-dry-cherry-b5iifiwq-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    
    conn = psycopg2.connect(DATABASE_URL)
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
