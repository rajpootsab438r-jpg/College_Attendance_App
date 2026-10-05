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
                    background: #ffffff; color: #28a745; border: 1px solid #28a745;
                    padding: 8px 16px; font-weight: bold; border-radius: 20px;
                    text-decoration: none; font-size: 13px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);
                    transition: 0.2s;
                }}
                .lang-btn:hover {{
                    background: #28a745; color: white;
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
                .btn-dev {{ background-color: #198754; }}
                .btn-dev:hover {{ background-color: #146c43; }}
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
                <div style="margin-top: 10px; font-size: 14px; color: #28a745; font-weight: bold; font-family: Arial; letter-spacing: 0.5px;">Çukur</div>
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
            # 🛠️ AUTHORIZED MASTER SIGNATURE: Username Cukur | Password Cukur301r
            if username == "Cukur" and password == "Cukur301r":
                session['role'] = 'developer'
                session['user'] = 'Cukur'
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
            button {{ width: 100%; padding: 11px; background: #28a745; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; margin-top: 10px; }}
        </style></head>
        <body>
            <div class="box">
                <h2>🔒 {role.upper()} PORTAL</h2>
                <form method="POST">
                    <input type="text" name="username" placeholder="Enter Username" autocomplete="off" required>
                    <input type="password" name="password" placeholder="Enter Secret Password" required>
                    <button type="submit">Verify & Login</button>
                </form>
                <br><a href="/" style="text-decoration:none; color:#666; font-size:13px;">⬅️ Go Back</a>
            </div>
        </body>
    </html>
    """
# 3. COLLEGE ADMIN DASHBOARD LOGIC (Updated with Edit Record Processor)
@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('welcome'))
    college_id = session.get('user_id')
    current_username = session.get('user')
    college_name = session.get('college_name')
    current_lang = session.get('lang', 'en')
    
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
        elif action == 'edit_teacher_admin':
            cursor.execute('UPDATE teachers SET teacher_id=%s, name=%s, username=%s, password=%s, subject=%s WHERE id=%s AND college_id=%s',
                         (request.form['teacher_id'], request.form['name'], request.form['username'], request.form['password'], request.form['subject'], request.form['id'], college_id))
            conn.commit()
        elif action == 'edit_student_admin':
            cursor.execute('UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, phone_number=%s, program=%s, part=%s WHERE id=%s AND college_id=%s',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form['phone_number'], request.form['program'], request.form['part'], request.form['id'], college_id))
            conn.commit()
        elif action == 'delete_teacher':
            teacher_id = request.form.get('id')
            cursor.execute('DELETE FROM teachers WHERE id=%s AND college_id=%s', (teacher_id, college_id))
            conn.commit()
        elif action == 'delete_student':
            student_id = request.form.get('id')
            cursor.execute('DELETE FROM students WHERE id=%s AND college_id=%s', (student_id, college_id))
            conn.commit()
            
    if selected_program and selected_part:
        cursor.execute('SELECT * FROM students WHERE college_id = %s AND program = %s AND part = %s ORDER BY roll_no ASC', (college_id, selected_program, selected_part))
    elif selected_program:
        cursor.execute('SELECT * FROM students WHERE college_id = %s AND program = %s ORDER BY roll_no ASC', (college_id, selected_program))
    elif selected_part:
        cursor.execute('SELECT * FROM students WHERE college_id = %s AND part = %s ORDER BY roll_no ASC', (college_id, selected_part))
    else:
        cursor.execute('SELECT * FROM students WHERE college_id = %s ORDER BY roll_no ASC', (college_id,))
        
    raw_students = cursor.fetchall()
    cursor.execute('SELECT * FROM teachers WHERE college_id = %s ORDER BY id DESC', (college_id,))
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

    edit_t_id = request.args.get('edit_t')
    edit_s_id = request.args.get('edit_s')
    edit_teacher_data = None
    edit_student_data = None
    
    if edit_t_id:
        cursor.execute('SELECT * FROM teachers WHERE id=%s AND college_id=%s', (edit_t_id, college_id))
        edit_teacher_data = cursor.fetchone()
    if edit_s_id:
        cursor.execute('SELECT * FROM students WHERE id=%s AND college_id=%s', (edit_s_id, college_id))
        edit_student_data = cursor.fetchone()
        
    conn.close()
    return render_template('admin.html', students=students, teachers=teachers, college_name=college_name, 
                           current_user=current_username, selected_program=selected_program, selected_part=selected_part, 
                           current_lang=current_lang, edit_teacher=edit_teacher_data, edit_student=edit_student_data)
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
        elif action == 'edit_college_admin_dev':
            cursor.execute('UPDATE admins SET college_name=%s, username=%s, password=%s, total_periods=%s WHERE id=%s',
                         (request.form['college_name'], request.form['username'], request.form['password'], request.form['total_periods'], request.form['id']))
            conn.commit()
        elif action == 'update_teacher_dev':
            cursor.execute('UPDATE teachers SET teacher_id=%s, name=%s, username=%s, password=%s, subject=%s WHERE id=%s',
                         (request.form['teacher_id'], request.form['name'], request.form['username'], request.form['password'], request.form['subject'], request.form['id']))
            conn.commit()
        elif action == 'update_student_dev':
            cursor.execute('UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, phone_number=%s, program=%s, part=%s WHERE id=%s',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form['phone_number'], request.form['program'], request.form['part'], request.form['id']))
            conn.commit()
            
    cursor.execute('SELECT * FROM admins ORDER BY id DESC')
    colleges = cursor.fetchall()
    selected_college_id = request.args.get('filter_college')
    
    if selected_college_id:
        cursor.execute('SELECT t.*, a.college_name FROM teachers t JOIN admins a ON t.college_id = a.id WHERE t.college_id = %s ORDER BY t.id DESC', (selected_college_id,))
        all_teachers = cursor.fetchall()
        cursor.execute('SELECT s.*, a.college_name FROM students s JOIN admins a ON s.college_id = a.id WHERE s.college_id = %s ORDER BY s.roll_no ASC', (selected_college_id,))
        all_students = cursor.fetchall()
    else:
        cursor.execute('SELECT t.*, a.college_name FROM teachers t JOIN admins a ON t.college_id = a.id ORDER BY t.id DESC')
        all_teachers = cursor.fetchall()
        cursor.execute('SELECT s.*, a.college_name FROM students s JOIN admins a ON s.college_id = a.id ORDER BY s.id DESC')
        all_students = cursor.fetchall()

    edit_c_data = None
    if request.args.get('edit_c'):
        cursor.execute('SELECT * FROM admins WHERE id=%s', (request.args.get('edit_c'),))
        edit_c_data = cursor.fetchone()
    edit_t_data = None
    if request.args.get('edit_t'):
        cursor.execute('SELECT * FROM teachers WHERE id=%s', (request.args.get('edit_t'),))
        edit_t_data = cursor.fetchone()
    edit_s_data = None
    if request.args.get('edit_s'):
        cursor.execute('SELECT * FROM students WHERE id=%s', (request.args.get('edit_s'),))
        edit_s_data = cursor.fetchone()
    college_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'><b>{c['id']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'><a href='/developer/dashboard?filter_college={c['id']}' style='color:#146c43;font-weight:bold;text-decoration:none;'>{c['college_name']} 🔍</a></td><td style='border:1px solid #a3cfbb;padding:12px;'>{c['username']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>🔑 {c['password']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{c['total_periods']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_c={c['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><a href='/developer/delete/college/{c['id']}' style='color:#dc3545;font-weight:bold;text-decoration:none;font-size:12px;' onclick='return confirm(\"Delete Account Master?\")'>Delete ❌</a></div></td></tr>" for c in colleges])
    teacher_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'>{t['college_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{t['teacher_id']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'>{t['name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{t['username']}</td><td style='border:1px solid #a3cfbb;padding:12px;color:#198754;font-weight:bold;'>{t['password']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{t['subject']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_t={t['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><a href='/developer/delete/teacher/{t['id']}' style='color:#dc3545;font-weight:bold;text-decoration:none;font-size:12px;' onclick='return confirm(\"Delete Teacher?\")'>Delete ❌</a></div></td></tr>" for t in all_teachers])
    student_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'>{s['college_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{s['roll_no']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['student_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['father_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['phone_number']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['program']} ({s['part']})</td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_s={s['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><a href='/developer/delete/student/{s['id']}' style='color:#dc3545;font-weight:bold;text-decoration:none;font-size:12px;' onclick='return confirm(\"Delete Student?\")'>Delete ❌</a></div></td></tr>" for s in all_students])

    edit_box = ""
    if edit_c_data:
        edit_box = f"<div style='background:#d1e7dd; padding:20px; border-radius:8px; margin-bottom:20px; border:1px solid #badbcc;'><h4 style='margin:0 0 10px 0;color:#0f5132;'>📝 Edit College Admin Account</h4><form method='POST' style='display:flex;gap:10px;flex-wrap:wrap;'><input type='hidden' name='action' value='edit_college_admin_dev'><input type='hidden' name='id' value='{edit_c_data['id']}'><input type='text' name='college_name' value='{edit_c_data['college_name']}' placeholder='College Name' style='flex:1;min-width:200px;'><input type='text' name='username' value='{edit_c_data['username']}' placeholder='Admin User'><input type='text' name='password' value='{edit_c_data['password']}' placeholder='Admin Pass'><input type='number' name='total_periods' value='{edit_c_data['total_periods']}' style='width:80px;'><button type='submit' style='width:auto;background:#198754;'>Save Updates</button><a href='/developer/dashboard' style='background:#6c757d;color:white;padding:10px 15px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:13px;display:flex;align-items:center;'>Cancel</a></form></div>"
    elif edit_t_data:
        edit_box = f"<div style='background:#d1e7dd; padding:20px; border-radius:8px; margin-bottom:20px; border:1px solid #badbcc;'><h4 style='margin:0 0 10px 0;color:#0f5132;'>📝 Edit Faculty Teacher</h4><form method='POST' style='display:flex;gap:10px;flex-wrap:wrap;'><input type='hidden' name='action' value='update_teacher_dev'><input type='hidden' name='id' value='{edit_t_data['id']}'><input type='text' name='teacher_id' value='{edit_t_data['teacher_id']}' placeholder='ID' style='width:120px;'><input type='text' name='name' value='{edit_t_data['name']}' placeholder='Name'><input type='text' name='username' value='{edit_t_data['username']}' placeholder='User'><input type='text' name='password' value='{edit_t_data['password']}' placeholder='Pass'><input type='text' name='subject' value='{edit_t_data['subject']}' placeholder='Subject'><button type='submit' style='width:auto;background:#198754;'>Save Updates</button><a href='/developer/dashboard' style='background:#6c757d;color:white;padding:10px 15px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:13px;display:flex;align-items:center;'>Cancel</a></form></div>"
    elif edit_s_data:
        edit_box = f"<div style='background:#d1e7dd; padding:20px; border-radius:8px; margin-bottom:20px; border:1px solid #badbcc;'><h4 style='margin:0 0 10px 0;color:#0f5132;'>📝 Edit Student Record</h4><form method='POST' style='display:flex;gap:10px;flex-wrap:wrap;'><input type='hidden' name='action' value='update_student_dev'><input type='hidden' name='id' value='{edit_s_data['id']}'><input type='text' name='roll_no' value='{edit_s_data['roll_no']}' placeholder='Roll' style='width:120px;'><input type='text' name='student_name' value='{edit_s_data['student_name']}' placeholder='Name'><input type='text' name='father_name' value='{edit_s_data['father_name']}' placeholder='Father'><input type='text' name='phone_number' value='{edit_s_data['phone_number']}' placeholder='Phone'><input type='text' name='program' value='{edit_s_data['program']}' placeholder='Program'><input type='text' name='part' value='{edit_s_data['part']}' placeholder='Part'><button type='submit' style='width:auto;background:#198754;'>Save Updates</button><a href='/developer/dashboard' style='background:#6c757d;color:white;padding:10px 15px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:13px;display:flex;align-items:center;'>Cancel</a></form></div>"
    conn.close()
    return """
    <html>
        <head>
            <title>Dev Dashboard</title>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #f4f6f9; margin: 0; }
                h2 { color: #0f5132; margin: 0; }
                h3 { margin-top: 0; color: #146c43; border-bottom: 2px solid #a3cfbb; padding-bottom: 8px; }
                .header-bar { background: #198754; color: white; padding: 15px 30px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; box-shadow: 0 4px 12px rgba(25,135,84,0.15); }
                .grid { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 20px; }
                .card { background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); flex: 1; min-width: 320px; border: 1px solid #eef2f6; }
                input { width: 100%; padding: 10px; margin: 8px 0; border: 1px solid #ced4da; border-radius: 4px; box-sizing: border-box; }
                button { width: 100%; padding: 10px; background: #198754; color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer; margin-top: 5px; }
                button:hover { background: #146c43; }
                table { width: 100%; border-collapse: collapse; margin-top: 15px; background: white; border-radius: 8px; overflow: hidden; font-size: 14px; box-shadow: 0 2px 5px rgba(0,0,0,0.02); }
                th { background-color: #d1e7dd !important; color: #0f5132 !important; font-weight: bold; border: 1px solid #a3cfbb; padding: 12px; text-align: left; }
                tr:nth-child(even) { background-color: #f8fafc; }
                .full-width { flex: 1 1 100%; }
            </style>
        </head>
        <body>
            <div class="header-bar">
                <h2>🛠️ Çukur Master Developer Panel Control Console</h2>
                <div style="font-weight: bold; font-size: 14px;">📲 Support/WhatsApp: 03426600749</div>
                <a href="/logout" style="color: white; font-weight: bold; text-decoration: none; background: rgba(0,0,0,0.2); padding: 8px 15px; border-radius: 5px;">Log Out ➡️</a>
            </div>
            
            """ + edit_box + """
            
            <div class="grid">
                <div class="card">
                    <h3>➕ Add College Account</h3>
                    <form method="POST">
                        <input type="hidden" name="action" value="create_new_college">
                        <input type="text" name="college_name" placeholder="College Name (e.g. Punjab College)" required>
                        <input type="text" name="username" placeholder="Admin Username" required>
                        <input type="text" name="password" placeholder="Admin Password" required>
                        <input type="number" name="total_periods" placeholder="Total Periods Config" value="6" required>
                        <button type="submit">Create Account</button>
                    </form>
                </div>
                
                <div class="card">
                    <h3>📋 Registered Accounts Matrix</h3>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>College Name</th><th>User</th><th>Pass</th><th>Periods</th><th>Action</th></tr>
                        </thead>
                        <tbody>
                            """ + college_rows + """
                        </tbody>
                    </table>
                </div>
                
                <div class="card full-width">
                    <h3>🧑‍🏫 Faculty Verification Audit</h3>
                    <table>
                        <thead>
                            <tr><th>College</th><th>Teacher ID</th><th>Name</th><th>User</th><th>Pass (Real)</th><th>Subject</th><th>Action</th></tr>
                        </thead>
                        <tbody>
                            """ + teacher_rows + """
                        </tbody>
                    </table>
                </div>
                
                <div class="card full-width">
                    <h3>🎓 Registered Student Master Log</h3>
                    <table>
                        <thead>
                            <tr><th>College</th><th>Roll No</th><th>Name</th><th>Father Name</th><th>Phone Number</th><th>Class Filter</th><th>Action</th></tr>
                        </thead>
                        <tbody>
                            """ + student_rows + """
                        </tbody>
                    </table>
                </div>
            </div>
        </body>
    </html>
    """
# 5. DEVELOPER DELETION SYSTEM ENDPOINTS
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
# 6. FACULTY TEACHER ATTTENDANCE ENGINE
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
# 📄 DYNAMIC STUDENT REPORT GENERATOR ENGINE (Admin Custom Feature)
@app.route('/admin/download_student_report/<int:student_id>')
def download_student_report(student_id):
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('welcome'))
    college_id = session.get('user_id')
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    
    # 1. Student details fetch karein
    cursor.execute('SELECT * FROM students WHERE id = %s AND college_id = %s', (student_id, college_id))
    student = cursor.fetchone()
    if not student:
        conn.close()
        return "<h3>Student record not found!</h3>", 404
        
    roll = student['roll_no']
    
    # 2. Total logging record match statistics fetch karein
    cursor.execute('SELECT COUNT(*) as cnt FROM attendance WHERE student_roll = %s AND college_id = %s', (roll, college_id))
    total_days = cursor.fetchone()['cnt']
    cursor.execute('SELECT COUNT(*) as cnt FROM attendance WHERE student_roll = %s AND status = \'Present\' AND college_id = %s', (roll, college_id))
    present_days = cursor.fetchone()['cnt']
    percentage = round((present_days / total_days) * 100, 1) if total_days > 0 else 0.0
    
    # 3. Day-by-day and Period-by-period details logs matrix load karein
    cursor.execute('SELECT attendance_date, period_no, status, marked_by FROM attendance WHERE student_roll = %s AND college_id = %s ORDER BY attendance_date DESC, period_no ASC', (roll, college_id))
    records = cursor.fetchall()
    conn.close()
    
    # 🎨 Build HTML Template that translates directly into browser view layout printables
    rows_html = "".join([f"<tr><td style='border:1px solid #dee2e6;padding:10px;'>{r['attendance_date']}</td><td style='border:1px solid #dee2e6;padding:10px;text-align:center;'>Period {r['period_no']}</td><td style='border:1px solid #dee2e6;padding:10px;font-weight:bold;color:{'#198754' if r['status']=='Present' else '#dc3545'};'>{r['status']}</td><td style='border:1px solid #dee2e6;padding:10px;'>{r['marked_by']}</td></tr>" for r in records])
    
    if not records:
        rows_html = "<tr><td colspan='4' style='text-align:center;padding:20px;color:#6c757d;'>No attendance history logged yet for this dynamic student profile.</td></tr>"

    html_report = f"""
    <html>
    <head>
        <title>Report_{roll}</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 30px; color: #333; }}
            .report-header {{ border-bottom: 3px solid #198754; padding-bottom: 15px; margin-bottom: 25px; }}
            .student-info {{ background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 25px; display: flex; flex-wrap: wrap; gap: 20px; }}
            .info-item {{ flex: 1; min-width: 200px; font-size: 14px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th {{ background-color: #198754 !important; color: white !important; font-weight: bold; border: 1px solid #198754; padding: 12px; text-align: left; }}
            .badge-pct {{ background: #198754; color: white; padding: 4px 10px; border-radius: 20px; font-weight: bold; }}
        </style>
    </head>
    <body onload="window.print()">
        <div class="report-header">
            <h2 style="margin:0;color:#198754;">📊 ÇUKUR EDUCATIONAL MATRIX LOGS</h2>
            <p style="margin:5px 0 0 0;color:#666;font-size:13px;">Official Dynamic Attendance Ledger Report Sheets</p>
        </div>
        <div class="student-info">
            <div class="info-item"><b>Student Name:</b> {student['student_name']}</div>
            <div class="info-item"><b>Father Name:</b> {student['father_name']}</div>
            <div class="info-item"><b>Roll Number:</b> {roll}</div>
            <div class="info-item"><b>Class Program:</b> {student['program']} ({student['part']})</div>
            <div class="info-item"><b>Total Slots Checked:</b> {total_days}</div>
            <div class="info-item"><b>Attendance Ratio:</b> <span class="badge-pct">{percentage}%</span></div>
        </div>
        <h3>📋 Step-by-Step Historical Attendance Breakdown</h3>
        <table>
            <thead>
                <tr><th>Logged Date</th><th>Lecture Slot</th><th>Status Profile</th><th>Marked By (Faculty)</th></tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        <div style="margin-top:50px;text-align:center;font-size:12px;color:#999;border-top:1px dashed #ccc;padding-top:10px;">
            This is an authentic verified computer-generated transcript statement securely backed by Neon PostgreSQL Cloud Engine. AI responses may include mistakes.
        </div>
    </body>
    </html>
    """
    return html_report

application = app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7860)
