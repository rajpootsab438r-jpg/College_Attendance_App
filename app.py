from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime

app = Flask(__name__)
# 🏷️ Branded core security token signature context mapped to Çukur Systems
app.secret_key = "attendance_cukur_secret_key_123"

# 🌍 Neon.tech Database Connection Function
def get_db_connection():
    DATABASE_URL = "postgresql://neondb_owner:npg_M7bJcCfdkN3e@ep-dry-cherry-b5iifiwq-pooler.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# 🌐 Global Multi-Language System Core Engine Matrix
LANG_DICT = {
    'en': {
        'title': 'College Attendance Portal',
        'subtitle': 'Select your module to continue',
        'admin_btn': '👑 College Admin Entry',
        'teacher_btn': '🧑‍🏫 Faculty Teacher Entry',
        'dev_btn': 'Super Developer Portal',
        'support': 'Support/WhatsApp',
        'lang_toggle': 'اردو 🇵🇰'
    },
    'ur': {
        'title': 'کالج اٹینڈنس پورٹل',
        'subtitle': 'آگے بڑھنے کے لیے اپنے ماڈیول کا انتخاب کریں',
        'admin_btn': '👑 کالج ایڈمن انٹری',
        'teacher_btn': '🧑‍🏫 فیکلٹی ٹیچر انٹری',
        'dev_btn': 'سپر ڈیولپر پورٹل',
        'support': 'سپورٹ / واٹس ایپ',
        'lang_toggle': 'English 🇬🇧'
    }
}

# 🔄 Global Language Router Handler Gateway
@app.route('/set_language/<lang>')
def set_language(lang):
    if lang in ['en', 'ur']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('welcome'))
# 1. Welcome Portal (English Default with Global Multi-Language Corner Interface Switches)
@app.route('/')
def welcome():
    current_lang = session.get('lang', 'en')
    t = LANG_DICT[current_lang]
    next_lang = 'ur' if current_lang == 'en' else 'en'
    
    return f"""
    <html>
        <head>
            <title>{t['title']} | Çukur</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <style>
                body {{ 
                    font-family: 'Segoe UI', Arial, sans-serif; text-align: center; margin: 0; padding: 0;
                    height: 100vh; display: flex; justify-content: center; align-items: center;
                    background-color: #f4f6f9; direction: {'rtl' if current_lang == 'ur' else 'ltr'};
                }}
                .lang-switcher-bar {{
                    position: fixed; top: 20px; right: 20px; z-index: 9999;
                }}
                .lang-btn {{
                    background: #ffffff; color: #6f42c1; border: 1px solid #6f42c1;
                    padding: 8px 16px; font-weight: bold; border-radius: 20px;
                    text-decoration: none; font-size: 13px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);
                    transition: 0.2s;
                }}
                .lang-btn:hover {{
                    background: #6f42c1; color: white;
                }}
                .container {{ 
                    background: #ffffff; padding: 40px; border-radius: 16px; 
                    box-shadow: 0px 8px 30px rgba(0,0,0,0.15); width: 90%; max-width: 400px; z-index: 1;
                    box-sizing: border-box;
                }}
                h1 {{ color: #2c3e50; font-size: 24px; margin-top: 0; margin-bottom: 5px; font-weight: 700; }}
                p {{ color: #7f8c8d; font-size: 15px; margin-bottom: 25px; }}
                .btn {{ display: block; padding: 14px; margin: 12px 0; font-size: 16px; color: white; text-decoration: none; font-weight: bold; border-radius: 8px; transition: all 0.2s ease; text-align: center; }}
                .btn-admin {{ background-color: #007bff; }}
                .btn-admin:hover {{ background-color: #0056b3; }}
                .btn-teacher {{ background-color: #28a745; }}
                .btn-teacher:hover {{ background-color: #218838; }}
                .btn-dev {{ background-color: #6f42c1; }}
                .btn-dev:hover {{ background-color: #5a32a3; }}
            </style>
        </head>
        <body>
            <div class="lang-switcher-bar">
                <a href="/set_language/{next_lang}" class="lang-btn">{t['lang_toggle']}</a>
            </div>
            <div class="container">
                <h1>{t['title']}</h1>
                <p>{t['subtitle']}</p>
                <a href="/login/admin" class="btn btn-admin">{t['admin_btn']}</a>
                <a href="/login/teacher" class="btn btn-teacher">{t['teacher_btn']}</a>
                <a href="/login/developer" class="btn btn-dev">{t['dev_btn']}</a>
                <div style="margin-top: 15px; font-size: 13px; color: #555; font-weight: 500;"> {t['support']}: 03426600749</div>
                <div style="margin-top: 10px; font-size: 14px; color: #6f42c1; font-weight: bold; font-family: Arial; letter-spacing: 0.5px;">Çukur</div>
            </div>
        </body>
    </html>
    """
# 2. Secure Login Panel Gateway
@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        if role == 'admin':
            cursor.execute('SELECT * FROM admins WHERE username = %s AND password = %s', (username, password))
            user = cursor.fetchone()
            if user:
                session['role'] = 'admin'
                session['user_id'] = user['id']
                session['user'] = user['username']
                session['college_name'] = user['college_name']
                conn.close()
                return redirect(url_for('admin_dashboard'))
        elif role == 'teacher':
            cursor.execute('SELECT * FROM teachers WHERE username = %s AND password = %s', (username, password))
            user = cursor.fetchone()
            if user:
                session['role'] = 'teacher'
                session['user_id'] = user['id']
                session['user'] = user['username']
                session['teacher_name'] = user['name']
                session['subject'] = user['subject']
                session['college_id'] = user['college_id']
                conn.close()
                return redirect(url_for('teacher_dashboard'))
        elif role == 'developer':
            if username == "cukur" and password == "cukur749":
                session['role'] = 'developer'
                session['user'] = 'cukur'
                conn.close()
                return redirect(url_for('developer_dashboard'))
                
        conn.close()
        return "<h3>Invalid Credentials! Please try again.</h3>"
        
    return f"""
    <html>
        <head><title>{role.capitalize()} Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ font-family: 'Segoe UI', Arial; background: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin:0; }}
            .box {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); width: 100%; max-width: 340px; text-align: center; }}
            input {{ width: 100%; padding: 11px; margin: 10px 0; border: 1px solid #ced4da; border-radius: 4px; box-sizing: border-box; }}
            button {{ width: 100%; padding: 11px; background: #007bff; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; margin-top: 10px; }}
        </style></head>
        <body>
            <div class="box">
                <h2>🔒 {role.upper()} PORTAL</h2>
                <form method="POST">
                    <input type="text" name="username" placeholder="Enter Username" autocomplete="off" required>
                    <input type="password" name="password" placeholder="Enter Secret Password" required>
                    <button type="submit">Verify & Login</button>
                </form>
                <br><a href="/" style="text-decoration:none; color:#666; font-size:13px;">⬅️ Go Back Back</a>
            </div>
        </body>
    </html>
    """
# 3. COLLEGE ADMIN DASHBOARD LOGIC
@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('welcome'))
    college_id = session.get('user_id')
    current_username = session.get('user')
    college_name = session.get('college_name')
    
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
        elif action == 'delete_teacher':
            teacher_id = request.form.get('id')
            cursor.execute('DELETE FROM teachers WHERE id=%s', (teacher_id,))
            conn.commit()
        elif action == 'delete_student':
            student_id = request.form.get('id')
            cursor.execute('DELETE FROM students WHERE id=%s', (student_id,))
            conn.commit()
            
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
# 4. SUPER DEVELOPER PORTAL
@app.route('/developer/dashboard', methods=['GET', 'POST'])
def developer_dashboard():
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_new_college':
            try:
                cursor.execute('INSERT INTO admins (college_name, username, password, total_periods) VALUES (%s, %s, %s, %s)', 
                             (request.form['college_name'], request.form['username'], request.form['password'], request.form.get('total_periods', 6)))
                conn.commit()
            except psycopg2.IntegrityError: conn.rollback()
        elif action == 'update_college_periods':
            cursor.execute('UPDATE admins SET total_periods=%s WHERE id=%s', (request.form['total_periods'], request.form['college_id']))
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
    else:
        cursor.execute('SELECT t.*, a.college_name FROM teachers t JOIN admins a ON t.college_id = a.id')
        all_teachers = cursor.fetchall()
        cursor.execute('SELECT s.*, a.college_name FROM students s JOIN admins a ON s.college_id = a.id')
        all_students = cursor.fetchall()

    edit_t_data = None
    if request.args.get('edit_t'):
        cursor.execute('SELECT * FROM teachers WHERE id=%s', (request.args.get('edit_t'),))
        edit_t_data = cursor.fetchone()
    edit_s_data = None
    if request.args.get('edit_s'):
        cursor.execute('SELECT * FROM students WHERE id=%s', (request.args.get('edit_s'),))
        edit_s_data = cursor.fetchone()
        
    college_rows = "".join([f"<tr><td>{c['id']}</td><td><a href='/developer/dashboard?filter_college={c['id']}'>{c['college_name']}</a></td><td>{c['username']}</td><td>{c['password']}</td><td><form method='POST'><input type='hidden' name='action' value='update_college_periods'><input type='hidden' name='college_id' value='{c['id']}'><input type='number' name='total_periods' value='{c['total_periods']}' style='width:50px;'><button type='submit'>Set</button></form></td><td><a href='/developer/delete/college/{c['id']}'>Delete</a></td></tr>" for c in colleges])
    teacher_rows = "".join([f"<tr><td>{t['college_name']}</td><td>{t['teacher_id']}</td><td>{t['name']}</td><td>{t['username']}</td><td>{t['password']}</td><td>{t['subject']}</td><td><a href='/developer/dashboard?edit_t={t['id']}'>Edit</a> | <a href='/developer/delete/teacher/{t['id']}'>Delete</a></td></tr>" for t in all_teachers])
    student_rows = "".join([f"<tr><td>{s['college_name']}</td><td>{s['roll_no']}</td><td>{s['student_name']}</td><td>{s['father_name']}</td><td>{s['phone_number']}</td><td>{s['program']} ({s['part']})</td><td><a href='/developer/dashboard?edit_s={s['id']}'>Edit</a> | <a href='/developer/delete/student/{s['id']}'>Delete</a></td></tr>" for s in all_students])

    edit_box = ""
    if edit_t_data:
        edit_box = f"<div style='background:#fff3cd; padding:20px;'><form method='POST'><input type='hidden' name='action' value='update_teacher_dev'><input type='hidden' name='id' value='{edit_t_data['id']}'><input type='text' name='teacher_id' value='{edit_t_data['teacher_id']}'><input type='text' name='name' value='{edit_t_data['name']}'><input type='text' name='username' value='{edit_t_data['username']}'><input type='text' name='password' value='{edit_t_data['password']}'><input type='text' name='subject' value='{edit_t_data['subject']}'><button type='submit'>Update</button></form></div>"
    elif edit_s_data:
        edit_box = f"<div style='background:#fff3cd; padding:20px;'><form method='POST'><input type='hidden' name='action' value='update_student_dev'><input type='hidden' name='id' value='{edit_s_data['id']}'><input type='text' name='roll_no' value='{edit_s_data['roll_no']}'><input type='text' name='student_name' value='{edit_s_data['student_name']}'><input type='text' name='father_name' value='{edit_s_data['father_name']}'><input type='text' name='phone_number' value='{edit_s_data['phone_number']}'><input type='text' name='program' value='{edit_s_data['program']}'><input type='text' name='part' value='{edit_s_data['part']}'><button type='submit'>Update</button></form></div>"

    conn.close()
    return f"""<html><head><title>Dev Dashboard</title><style>body{{font-family:Arial;padding:20px;background:#f4f6f9;}}table{{width:100%;border-collapse:collapse;background:white;margin-bottom:20px;}}th,td{{border:1px solid #ddd;padding:8px;}}th{{background:#eee;}}input{{padding:6px;margin:4px 0;}}button{{padding:6px 12px;background:#6f42c1;color:white;border:none;cursor:pointer;}}</style></head><body><h2>🛠️ Developer Control Console</h2><a href="/logout">Log Out</a>{edit_box}<div style="display:flex;gap:20px;margin-top:20px;"><div style="background:white;padding:20px;border-radius:8px;min-width:300px;"><h3>➕ Add College Account</h3><form method="POST"><input type="hidden" name="action" value="create_new_college"><input type="text" name="college_name" placeholder="College Name" required><input type="text" name="username" placeholder="Admin Username" required><input type="text" name="password" placeholder="Admin Password" required><input type="number" name="total_periods" value="6" required><button type="submit">Create Account</button></form></div><div style="background:white;padding:20px;border-radius:8px;flex:1;"><h3>🏫 Registered Accounts Matrix</h3><table><thead><tr><th>ID</th><th>College</th><th>User</th><th>Pass</th><th>Periods</th><th>Action</th></tr></thead><tbody>{college_rows}</tbody></table></div></div><h3>🧑‍🏫 Faculty Verification Audit</h3><table><thead><tr><th>College</th><th>ID</th><th>Name</th><th>User</th><th>Pass</th><th>Subject</th><th>Action</th></tr></thead><tbody>{teacher_rows}</tbody></table><h3>🎓 Registered Student Master Log</h3><table><thead><tr><th>College</th><th>Roll</th><th>Name</th><th>Father</th><th>Phone</th><th>Class</th><th>Action</th></tr></thead><tbody>{student_rows}</tbody></table></body></html>"""
# 🗑️ DEVELOPER DELETION SYSTEM ENDPOINTS
@app.route('/developer/delete/college/<int:id>')
def developer_delete_college(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM admins WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/delete/teacher/<int:id>')
def developer_delete_teacher(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM teachers WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/delete/student/<int:id>')
def developer_delete_student(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM students WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('developer_dashboard'))
# 5. FACULTY TEACHER ATTTENDANCE ENGINE
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
    current_lang = session.get('lang', 'en')
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
            s_dict['saved_status'] = att_record['status'] if att_record else ''
            students.append(s_dict)
    conn.close()
    return render_template('attendance.html', students=students, subject=subject, teacher_name=teacher_name, 
                           selected_program=selected_program, selected_part=selected_part, 
                           selected_date=selected_date, selected_period=selected_period, total_periods=total_periods, current_lang=current_lang)

# ⚡ Instant Live Save Gateway (AJAX Engine Updated For Blanks)
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
    cursor.execute('SELECT id FROM attendance WHERE student_roll = %s AND attendance_date = %s AND period_no = %s AND college_id = %s', (roll, att_date, period_no, college_id))
    existing = cursor.fetchone()
    
    if existing: 
        cursor.execute('UPDATE attendance SET status = %s, marked_by = %s, created_at = CURRENT_TIMESTAMP WHERE id = %s', (status, teacher_username, existing['id']))
    else: 
        cursor.execute('INSERT INTO attendance (student_roll, attendance_date, period_no, status, marked_by, college_id) VALUES (%s, %s, %s, %s, %s, %s)', (roll, att_date, period_no, status, teacher_username, college_id))
        
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
