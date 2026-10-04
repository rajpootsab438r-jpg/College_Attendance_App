from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime

app = Flask(__name__)
app.secret_key = "attendance_cukur_secret_key_123"

# 🌍 Neon.tech Database Connection Function
def get_db_connection():
    DATABASE_URL = "postgresql://neondb_owner:npg_M7bJcCfdkN3e@ep-dry-cherry-b5iifiwq-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    conn = psycopg2.connect(DATABASE_URL)
    return conn
# 1. Welcome Portal
@app.route('/')
def welcome():
    return """
    <html>
        <head>
            <title>College Attendance System</title>
            <style>
                body { 
                    font-family: 'Segoe UI', Arial, sans-serif; text-align: center; margin: 0; 
                    background-image: linear-gradient(rgba(0, 0, 0, 0.5), rgba(0, 0, 0, 0.5)), url('https://unsplash.com');
                    background-size: cover; background-position: center; background-attachment: fixed; padding-top: 100px;
                }
                .container { background: rgba(255, 255, 255, 0.95); padding: 40px; display: inline-block; border-radius: 16px; box-shadow: 0px 8px 30px rgba(0,0,0,0.3); width: 100%; max-width: 400px; }
                h1 { color: #2c3e50; font-size: 26px; margin-bottom: 5px; }
                p { color: #7f8c8d; font-size: 15px; margin-bottom: 25px; }
                .btn { display: block; padding: 14px; margin: 12px 0; font-size: 16px; color: white; text-decoration: none; font-weight: bold; border-radius: 8px; transition: all 0.2s ease; }
                .btn-admin { background-color: #007bff; }
                .btn-admin:hover { background-color: #0056b3; }
                .btn-teacher { background-color: #28a745; }
                .btn-teacher:hover { background-color: #218838; }
                .btn-dev { background-color: #6f42c1; }
                .btn-dev:hover { background-color: #5a32a3; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🏫 College Attendance Portal</h1>
                <p>Select your module to continue</p>
                <a href="/login/admin" class="btn btn-admin">👑 College Admin Entry</a>
                <a href="/login/teacher" class="btn btn-teacher">🧑‍🏫 Faculty Teacher Entry</a>
                <a href="/login/developer" class="btn btn-dev">Super Developer Portal</a>
                <div style="margin-top: 15px; font-size: 13px; color: #555; font-weight: 500;"> Support/WhatsApp: 03426600749</div>
                <div style="margin-top: 10px; font-size: 14px; color: #6f42c1; font-weight: bold; font-family: Arial; letter-spacing: 0.5px;">Çukur</div>
            </div>
        </body>
    </html>
    """
# 2. Secure Login Panel Gateway
@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if role == 'developer':
            if username == 'Cukurdeveloper' and password == 'Cukur301r':
                session['user'] = username
                session['role'] = 'developer'
                return redirect(url_for('developer_dashboard'))
            else:
                return "<h2> Galat Developer Credentials!</h2><a href='/login/developer'>Wapas Jayein</a>"
        
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        if role == 'admin':
            cursor.execute('SELECT * FROM admins WHERE username = %s AND password = %s', (username, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user['id']
                session['user'] = user['username']
                session['college_name'] = user['college_name']
                session['role'] = 'admin'
                conn.close()
                return redirect(url_for('admin_dashboard'))
                
        elif role == 'teacher':
            cursor.execute('SELECT * FROM teachers WHERE username = %s AND password = %s', (username, password))
            user = cursor.fetchone()
            if user:
                session['user'] = username
                session['role'] = 'teacher'
                session['teacher_name'] = user['name']
                session['subject'] = user['subject']
                session['college_id'] = user['college_id']
                conn.close()
                return redirect(url_for('teacher_dashboard'))
                
        conn.close()
        return "<h2> Galat Credentials!</h2><a href='/'>Wapas Jayein</a>"

    role_title = " Admin Sign-In" if role == 'admin' else (" Developer Sign-In" if role == 'developer' else " Teacher Sign-In")
    bg_color = "#007bff" if role == 'admin' else ("#6f42c1" if role == 'developer' else "#28a745")
    return f"""
    <html>
        <head>
            <style>
                body {{ 
                    font-family: Arial; text-align: center; margin: 0;
                    background-image: linear-gradient(rgba(0, 0, 0, 0.4), rgba(0, 0, 0, 0.4)), url('https://unsplash.com');
                    background-size: cover; background-position: center; padding-top: 120px;
                }}
                .box {{ background: rgba(255, 255, 255, 0.96); padding: 35px; display: inline-block; border-radius: 12px; box-shadow: 0px 6px 25px rgba(0,0,0,0.25); width: 280px; }}
                h2 {{ color: {bg_color}; }}
                input {{ width: 100%; padding: 11px; margin: 10px 0; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }}
                button {{ width: 100%; padding: 12px; background: {bg_color}; color: white; border: none; font-weight: bold; border-radius: 6px; cursor: pointer; }}
            </style>
        </head>
        <body>
            <div class="box">
                <h2>{role_title}</h2>
                <form method="POST">
                    <input type="text" name="username" placeholder="Username" autocomplete="off" required>
                    <input type="password" name="password" placeholder="Password" autocomplete="off" required>
                    <button type="submit">Sign In</button>
                </form>
                <a href="/" style="display:block; margin-top:15px; color:#666; text-decoration:none;">⬅️ Back</a>
            </div>
        </body>
    </html>
    """
# 3. SUPER DEVELOPER PORTAL
@app.route('/developer/dashboard', methods=['GET', 'POST'])
def developer_dashboard():
    if 'role' not in session or session['role'] != 'developer':
        return redirect(url_for('welcome'))
        
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_new_college':
            c_name = request.form['college_name']
            c_user = request.form['username']
            c_pass = request.form['password']
            c_periods = request.form.get('total_periods', 6)
            try:
                cursor.execute('INSERT INTO admins (college_name, username, password, total_periods) VALUES (%s, %s, %s, %s)', (c_name, c_user, c_pass, c_periods))
                conn.commit()
            except psycopg2.IntegrityError:
                conn.rollback()
                
        elif action == 'update_college_periods':
            col_id = request.form['college_id']
            new_periods = request.form['total_periods']
            cursor.execute('UPDATE admins SET total_periods=%s WHERE id=%s', (new_periods, col_id))
            conn.commit()
            
        elif action == 'update_teacher_dev':
            cursor.execute('UPDATE teachers SET teacher_id=%s, name=%s, username=%s, password=%s, subject=%s WHERE id=%s',
                         (request.form['teacher_id'], request.form['name'], request.form['username'], request.form['password'], request.form['subject'], request.form['id']))
            conn.commit()
            
        elif action == 'update_student_dev':
            cursor.execute('UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, phone_number=%s, program=%s, part=%s WHERE id=%s',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form['phone_number'], request.form['program'], request.form['part'], request.form['id']))
            conn.commit()
            
    cursor.execute('SELECT * FROM admins')
    colleges = cursor.fetchall()
    
    selected_college_id = request.args.get('filter_college')
    
    if selected_college_id:
        cursor.execute('SELECT t.*, a.college_name FROM teachers t JOIN admins a ON t.college_id = a.id WHERE t.college_id = %s', (selected_college_id,))
        all_teachers = cursor.fetchall()
        cursor.execute('SELECT s.*, a.college_name FROM students s JOIN admins a ON s.college_id = a.id WHERE s.college_id = %s', (selected_college_id,))
        all_students = cursor.fetchall()
        cursor.execute('SELECT college_name FROM admins WHERE id = %s', (selected_college_id,))
        active_filter_name = cursor.fetchone()
        filter_heading = f"📊 Showing Results for: <span style='color:#ffc107;'>{active_filter_name['college_name']}</span> | <a href='/developer/dashboard' style='color:white; font-size:14px; text-decoration:underline;'>Show All Colleges</a>"
    else:
        cursor.execute('SELECT t.*, a.college_name FROM teachers t JOIN admins a ON t.college_id = a.id')
        all_teachers = cursor.fetchall()
        cursor.execute('SELECT s.*, a.college_name FROM students s JOIN admins a ON s.college_id = a.id')
        all_students = cursor.fetchall()
        filter_heading = "🌐 Master Audit Log (All Registered Colleges Combined)"

    edit_t_id = request.args.get('edit_t')
    edit_s_id = request.args.get('edit_s')
    
    edit_t_data = None
    if edit_t_id:
        cursor.execute('SELECT * FROM teachers WHERE id=%s', (edit_t_id,))
        edit_t_data = cursor.fetchone()
        
    edit_s_data = None
    if edit_s_id:
        cursor.execute('SELECT * FROM students WHERE id=%s', (edit_s_id,))
        edit_s_data = cursor.fetchone()
        
    college_rows = ""
    for c in colleges:
        college_rows += f"""<tr>
            <td><b>{c['id']}</b></td>
            <td><a href="/developer/dashboard?filter_college={c['id']}" style="color:#6f42c1; font-weight:bold; text-decoration:none;" title="Click to filter details">{c['college_name']} 🔍</a></td>
            <td>{c['username']}</td>
            <td>🔑 {c['password']}</td>
            <td>
                <form method="POST" style="display:inline; margin:0;">
                    <input type="hidden" name="action" value="update_college_periods">
                    <input type="hidden" name="college_id" value="{c['id']}">
                    <input type="number" name="total_periods" value="{c['total_periods']}" style="width:50px; padding:2px; margin:0;" min="1" max="15">
                    <button type="submit" style="width:auto; padding:2px 5px; font-size:11px; background:#28a745; margin:0;">Set ⚙️</button>
                </form>
            </td>
            <td><a href="/developer/delete/college/{c['id']}" style="color:red; font-weight:bold; text-decoration:none;" onclick="return confirm('Delete College?')">Delete Account ❌</a></td>
        </tr>"""
    teacher_rows = ""
    for t in all_teachers:
        teacher_rows += f"""<tr>
            <td>{t['college_name']}</td>
            <td><b>{t['teacher_id']}</b></td>
            <td>{t['name']}</td>
            <td>{t['username']}</td>
            <td style="color:#28a745; font-weight:bold;">{t['password']}</td>
            <td>{t['subject']}</td>
            <td>
                <a href="/developer/dashboard?edit_t={t['id']}" style="color:#007bff; font-weight:bold; margin-right:10px;">Edit 📝</a>
                <a href="/developer/delete/teacher/{t['id']}" style="color:red; font-weight:bold;" onclick="return confirm('Delete Teacher?')">Delete ❌</a>
            </td>
        </tr>"""
        
    student_rows = ""
    for s in all_students:
        student_rows += f"""<tr>
            <td>{s['college_name']}</td>
            <td><b>{s['roll_no']}</b></td>
            <td>{s['student_name']}</td>
            <td>{s['father_name']}</td>
            <td>{s['phone_number']}</td>
            <td>{s['program']} ({s['part']})</td>
            <td>
                <a href="/developer/dashboard?edit_s={s['id']}" style="color:#007bff; font-weight:bold; margin-right:10px;">Edit 📝</a>
                <a href="/developer/delete/student/{s['id']}" style="color:red; font-weight:bold;" onclick="return confirm('Delete Student?')">Delete ❌</a>
            </td>
        </tr>"""

    edit_box = ""
    if edit_t_data:
        edit_box = f"""<div class="card" style="background:#fff3cd;"><h3>📝 Edit Faculty Teacher</h3>
        <form method="POST"><input type="hidden" name="action" value="update_teacher_dev"><input type="hidden" name="id" value="{edit_t_data['id']}">
        <input type="text" name="teacher_id" value="{edit_t_data['teacher_id']}" required><input type="text" name="name" value="{edit_t_data['name']}" required>
        <input type="text" name="username" value="{edit_t_data['username']}" required><input type="text" name="password" value="{edit_t_data['password']}" required>
        <input type="text" name="subject" value="{edit_t_data['subject']}" required><button type="submit">Save Updates</button></form></div>"""
    elif edit_s_data:
        edit_box = f"""<div class="card" style="background:#fff3cd;"><h3>📝 Edit Student Record</h3>
        <form method="POST"><input type="hidden" name="action" value="update_student_dev"><input type="hidden" name="id" value="{edit_s_data['id']}">
        <input type="text" name="roll_no" value="{edit_s_data['roll_no']}" required><input type="text" name="student_name" value="{edit_s_data['student_name']}" required>
        <input type="text" name="father_name" value="{edit_s_data['father_name']}" required><input type="text" name="phone_number" value="{edit_s_data['phone_number']}" required>
        <input type="text" name="program" value="{edit_s_data['program']}" required><input type="text" name="part" value="{edit_s_data['part']}" required><button type="submit">Save Updates</button></form></div>"""

    conn.close()
    return f"""
    <html>
        <head>
            <title>Super Developer Dashboard</title>
            <style>
                body {{ font-family: 'Segoe UI', Arial; background-color: #f4f6f9; padding: 25px; margin: 0; }}
                .header {{ background: #6f42c1; color: white; padding: 15px 30px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }}
                .grid {{ display: flex; gap: 20px; flex-wrap: wrap; margin-top: 20px; }}
                .card {{ background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); flex: 1; min-width: 320px; }}
                input {{ width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ced4da; border-radius: 4px; box-sizing: border-box; }}
                button {{ width: 100%; padding: 10px; background: #6f42c1; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 15px; background: white; border-radius: 8px; overflow: hidden; font-size: 14px; }}
                th, td {{ border: 1px solid #dee2e6; padding: 10px; text-align: left; }}
                th {{ background-color: #e9ecef; color: #495057; }}
                .full-width {{ flex: 1 1 100%; }}
                .filter-bar {{ background: #4b2896; color: white; padding: 12px; border-radius: 6px; margin-top: 20px; font-weight: bold; font-size: 16px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>🛠️ Cukur Developer Portal Control Console</h2>
                <div style="font-weight: bold; font-size: 15px;">📲 WhatsApp Support: 03426600749</div>
                <a href="/logout" style="color: white; font-weight: bold; text-decoration: none;">Log Out ➡️</a>
            </div>
            {edit_box}
            <div class="grid">
                <div class="card">
                    <h3>➕ Naye College Ka Admin Create Karein</h3>
                    <form method="POST">
                        <input type="hidden" name="action" value="create_new_college">
                        <input type="text" name="college_name" placeholder="College Name (e.g. Punjab College)" required>
                        <input type="text" name="username" placeholder="Admin Username" required>
                        <input type="text" name="password" placeholder="Admin Password" required>
                        <input type="number" name="total_periods" placeholder="Total Periods (e.g. 6)" value="6" required>
                        <button type="submit">Create Account</button>
                    </form>
                </div>
                <div class="card">
                    <h3>📋 Registered Colleges Accounts</h3>
                    <table>
                        <thead><tr><th>ID</th><th>College Name</th><th>Username</th><th>Password</th><th>Periods Config</th><th>Action</th></tr></thead>
                        <tbody>{college_rows}</tbody>
                    </table>
                </div>
                <div class="filter-bar full-width">{filter_heading}</div>
                <div class="card full-width">
                    <h3>📚 Teachers Audit List</h3>
                    <table>
                        <thead><tr><th>College</th><th>Teacher ID</th><th>Name</th><th>Username</th><th>Password (Real)</th><th>Subject</th><th>Actions</th></tr></thead>
                        <tbody>{teacher_rows}</tbody>
                    </table>
                </div>
                <div class="card full-width">
                    <h3>🎓 Students Audit List</h3>
                    <table>
                        <thead><tr><th>College</th><th>Roll No</th><th>Name</th><th>Father Name</th><th>Phone Number</th><th>Class Filter</th><th>Actions</th></tr></thead>
                        <tbody>{student_rows}</tbody>
                    </table>
                </div>
            </div>
        </body>
    </html>
    """
@app.route('/developer/delete/college/<int:id>')
def dev_delete_college(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/delete/teacher/<int:id>')
def dev_delete_teacher(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM teachers WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/delete/student/<int:id>')
def dev_delete_student(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM students WHERE id=%s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('developer_dashboard'))
# 👑 College Admin Dashboard Logic (Updated with Class Filter Engine)
@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('welcome'))
    college_id = session.get('user_id')
    current_username = session.get('user')
    college_name = session.get('college_name')
    
    # Filter selection URL params fetch karein
    selected_program = request.args.get('program', '')
    selected_part = request.args.get('part', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'change_username':
            new_user = request.form['new_username']
            cursor.execute('UPDATE admins SET username = %s WHERE id = %s', (new_user, college_id))
            conn.commit()
            session['user'] = new_user
            current_username = new_user
        elif action == 'add_teacher':
            cursor.execute('INSERT INTO teachers (teacher_id, name, username, password, subject, college_id) VALUES (%s, %s, %s, %s, %s, %s)',
                         (request.form['teacher_id'], request.form['name'], request.form['username'], request.form['password'], request.form['subject'], college_id))
            conn.commit()
        elif action == 'add_student':
            cursor.execute('INSERT INTO students (roll_no, student_name, father_name, phone_number, program, part, college_id) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form['phone_number'], request.form['program'], request.form['part'], college_id))
            conn.commit()
        elif action == 'update_teacher':
            cursor.execute('UPDATE teachers SET teacher_id=%s, name=%s, username=%s, password=%s, subject=%s WHERE id=%s',
                         (request.form['teacher_id'], request.form['name'], request.form['username'], request.form['password'], request.form['subject'], request.form['id']))
            conn.commit()
        elif action == 'update_student':
            cursor.execute('UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, phone_number=%s, program=%s, part=%s WHERE id=%s',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form['phone_number'], request.form['program'], request.form['part'], request.form['id']))
            conn.commit()
        elif action == 'delete_teacher':
            teacher_id = request.form.get('id')
            cursor.execute('DELETE FROM teachers WHERE id=%s', (teacher_id,))
            conn.commit()
        elif action == 'delete_student':
            student_id = request.form.get('id')
            cursor.execute('DELETE FROM students WHERE id=%s', (student_id,))
            conn.commit()
            
    # Dynamic Query Mapping logic based on filter choices
    if selected_program and selected_part:
        cursor.execute('SELECT * FROM students WHERE college_id = %s AND program = %s AND part = %s', (college_id, selected_program, selected_part))
    elif selected_program:
        cursor.execute('SELECT * FROM students WHERE college_id = %s AND program = %s', (college_id, selected_program))
    elif selected_part:
        cursor.execute('SELECT * FROM students WHERE college_id = %s AND part = %s', (college_id, selected_part))
    else:
        cursor.execute('SELECT * FROM students WHERE college_id = %s', (college_id,))
        
    raw_students = cursor.fetchall()
    cursor.execute('SELECT * FROM teachers WHERE college_id = %s', (college_id,))
    raw_teachers = cursor.fetchall()
    
    teachers = [dict(t) for t in raw_teachers]
    students = []
    
    for s in raw_students:
        s_dict = dict(s)
        roll = s['roll_no']
        cursor.execute('SELECT COUNT(*) as cnt FROM attendance WHERE student_roll = %s AND college_id = %s', (roll, college_id))
        total_days = cursor.fetchone()['cnt']
        cursor.execute('SELECT COUNT(*) as cnt FROM attendance WHERE student_roll = %s AND status = \'Present\' AND college_id = %s', (roll, college_id))
        present_days = cursor.fetchone()['cnt']
        s_dict['percentage'] = round((present_days / total_days) * 100, 1) if total_days > 0 else 0.0
        students.append(s_dict)
        
    conn.close()
    return render_template('admin.html', students=students, teachers=teachers, college_name=college_name, 
                           current_user=current_username, selected_program=selected_program, selected_part=selected_part)

# 5. Teacher Dashboard Engine
@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'role' not in session or session['role'] != 'teacher': return redirect(url_for('welcome'))
    subject = session.get('subject')
    teacher_name = session.get('teacher_name')
    college_id = session.get('college_id')
    selected_program = request.args.get('program')
    selected_part = request.args.get('part')
    selected_date = request.args.get('attendance_date', datetime.today().strftime('%Y-%m-%d'))
    selected_period = request.args.get('period_no', '1')
    students = []
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('SELECT total_periods FROM admins WHERE id = %s', (college_id,))
    col_info = cursor.fetchone()
    total_periods = col_info['total_periods'] if col_info else 6
    
    if selected_program and selected_part:
        cursor.execute('SELECT * FROM students WHERE program = %s AND part = %s AND college_id = %s', (selected_program, selected_part, college_id))
        raw_students = cursor.fetchall()
        
        for s in raw_students:
            s_dict = dict(s)
            cursor.execute('SELECT status FROM attendance WHERE student_roll = %s AND attendance_date = %s AND period_no = %s AND college_id = %s', 
                           (s['roll_no'], selected_date, int(selected_period), college_id))
            att_record = cursor.fetchone()
            # 🛠️ FIXED: Agar record nahi hai, to default status bilkul khali (empty string) rahega
            s_dict['saved_status'] = att_record['status'] if att_record else ''
            students.append(s_dict)
            
    conn.close()
    return render_template('attendance.html', students=students, subject=subject, teacher_name=teacher_name, 
                           selected_program=selected_program, selected_part=selected_part, 
                           selected_date=selected_date, selected_period=selected_period, total_periods=total_periods)

# ⚡ Instant Live Save Gateway (AJAX Engine)
@app.route('/teacher/quick_attendance', methods=['POST'])
def quick_attendance():
    if 'role' not in session or session['role'] != 'teacher': return {"status": "error", "message": "Unauthorized"}, 401
    
    data = request.get_json()
    roll = data.get('roll')
    status = data.get('status')
    att_date = data.get('date')
    period_no = int(data.get('period', 1))
    teacher_username = session.get('user')
    college_id = session.get('college_id')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    cursor.execute('SELECT id FROM attendance WHERE student_roll = %s AND attendance_date = %s AND period_no = %s AND college_id = %s', 
                   (roll, att_date, period_no, college_id))
    existing = cursor.fetchone()
    
    if existing: 
        cursor.execute('UPDATE attendance SET status = %s, marked_by = %s, created_at = CURRENT_TIMESTAMP WHERE id = %s', (status, teacher_username, existing['id']))
    else: 
        cursor.execute('INSERT INTO attendance (student_roll, attendance_date, period_no, status, marked_by, college_id) VALUES (%s, %s, %s, %s, %s, %s)', 
                       (roll, att_date, period_no, status, teacher_username, college_id))
        
    conn.commit()
    conn.close()
    return {"status": "success", "current_status": status}

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('welcome'))

application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)
