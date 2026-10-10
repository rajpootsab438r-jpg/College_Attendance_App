import os
import sqlite3
import threading
from urllib.parse import urlparse
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, send_file, send_from_directory
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import io


class SQLiteCursorProxy:
    def __init__(self, connection, cursor):
        self._connection = connection
        self._cursor = cursor

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __setattr__(self, name, value):
        if name in {'_connection', '_cursor'}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._cursor, name, value)

    def execute(self, query, params=()):
        if params:
            query = query.replace('%s', '?')
        return self._cursor.execute(query, params)

    def executemany(self, query, seq_of_params):
        if seq_of_params:
            query = query.replace('%s', '?')
        return self._cursor.executemany(query, seq_of_params)


class SQLiteCompatConnection:
    def __init__(self, db_path):
        self._connection = sqlite3.connect(db_path)

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        if name == '_connection':
            object.__setattr__(self, name, value)
        else:
            setattr(self._connection, name, value)

    def cursor(self):
        return SQLiteCursorProxy(self, self._connection.cursor())

    def execute(self, query, params=()):
        return self.cursor().execute(query, params)

    def executemany(self, query, seq_of_params):
        return self.cursor().executemany(query, seq_of_params)

    def close(self):
        return self._connection.close()

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

app = Flask(__name__)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_DIR, "static")
# 🏷️ Branded core security token signature context mapped to Çukur Systems
app.secret_key = os.environ.get("SECRET_KEY", "attendance_cukur_secret_key_123")

class DatabaseConfigurationError(RuntimeError):
    pass


_database_initialized = False
_database_initialization_lock = threading.Lock()


def get_database_url():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        if os.environ.get("VERCEL") == "1":
            raise DatabaseConfigurationError(
                "DATABASE_URL is missing. Add your PostgreSQL connection string in "
                "Vercel Project Settings > Environment Variables, then redeploy."
            )
        database_url = "sqlite:///college_attendance_app.db"
        os.environ["DATABASE_URL"] = database_url
    if os.environ.get("VERCEL") == "1" and database_url.startswith("sqlite"):
        raise DatabaseConfigurationError(
            "SQLite storage is temporary on Vercel. Set DATABASE_URL to a persistent PostgreSQL connection string."
        )
    return database_url


@app.errorhandler(DatabaseConfigurationError)
def handle_database_configuration_error(error):
    app.logger.error("Database configuration error: %s", error)
    return jsonify({"status": "error", "message": str(error)}), 503


@app.errorhandler(psycopg2.OperationalError)
def handle_database_connection_error(error):
    app.logger.error("PostgreSQL connection failed: %s", error)
    return jsonify({
        "status": "error",
        "message": "The database is temporarily unavailable. Check DATABASE_URL and the database provider's network/SSL settings."
    }), 503


def get_local_db_path():
    database_url = get_database_url()
    if not database_url.startswith("sqlite"):
        return None
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/") or "college_attendance_app.db"
    if not os.path.isabs(db_name):
        db_name = os.path.join(os.path.dirname(__file__), db_name)
    return db_name

@app.route('/sw.js')
def serve_sw():
    return send_from_directory(STATIC_DIR, 'sw.js', mimetype='application/javascript')

@app.route('/offline')
@app.route('/offline.html')
def serve_offline_page():
    return send_from_directory(STATIC_DIR, 'offline.html', mimetype='text/html')

@app.route('/manifest.json')
def serve_manifest():
    manifest_path = os.path.join(PROJECT_DIR, 'manifest.json')
    if not os.path.isfile(manifest_path):
        manifest_path = os.path.join(STATIC_DIR, 'manifest.json')
    response = send_file(
        manifest_path,
        mimetype='application/manifest+json',
        max_age=0
    )
    response.headers['Cache-Control'] = 'no-cache'
    return response


def is_offline_sync_request():
    return request.headers.get('X-Offline-Sync') == '1'


def offline_sync_actor_matches(role, actor_id):
    if not is_offline_sync_request():
        return True
    expected_actor = f'{role}:{actor_id}'
    return request.headers.get('X-Sync-Actor') == expected_actor


def sync_json_response(status='success', http_status=200, **payload):
    return jsonify({"status": status, **payload}), http_status


def begin_sync_operation(cursor):
    if not is_offline_sync_request():
        return False
    operation_id = request.headers.get('X-Sync-Operation', '').strip()
    if not operation_id or len(operation_id) > 128:
        raise ValueError('A valid X-Sync-Operation header is required.')
    cursor.execute(
        'INSERT INTO sync_operations (operation_id) VALUES (%s) ON CONFLICT (operation_id) DO NOTHING',
        (operation_id,)
    )
    return cursor.rowcount == 0


def ensure_database_initialized():
    global _database_initialized
    if _database_initialized:
        return
    with _database_initialization_lock:
        if _database_initialized:
            return
        get_database_url()
        from setup_db import setup_database
        setup_database()
        _database_initialized = True


def get_db_connection():
    ensure_database_initialized()
    database_url = get_database_url()
    if database_url.startswith('sqlite'):
        conn = SQLiteCompatConnection(get_local_db_path())
        conn.row_factory = sqlite3.Row
        return conn
    conn = psycopg2.connect(database_url, cursor_factory=DictCursor)
    return conn


def delete_student_record(cursor, student_id, college_id):
    cursor.execute('SELECT roll_no FROM students WHERE id = %s AND college_id = %s', (student_id, college_id))
    student = cursor.fetchone()
    if student:
        cursor.execute('DELETE FROM attendance WHERE student_roll = %s AND college_id = %s', (student['roll_no'], college_id))
        cursor.execute('DELETE FROM students WHERE id = %s AND college_id = %s', (student_id, college_id))

# 🌐 Global Multi-Language System Core Engine Matrix
LANG_DICT = {
    'en': {
        'title': 'College Attendance Portal',
        'subtitle': 'Select your module to continue',
        'admin_btn': '👑 College Admin Entry',
        'teacher_btn': '🧑‍🏫 Faculty Teacher Entry',
        'dev_btn': 'Super Developer Portal',
        'support': 'Support/WhatsApp',
        'lang_toggle': 'اردو 🇵🇰',
        'download_app': '📥 Download App'
    },
    'ur': {
        'title': 'کالج اٹینڈنس پورٹل',
        'subtitle': 'آگے بڑھنے کے لیے اپنے ماڈیول کا انتخاب کریں',
        'admin_btn': '👑 کالج ایڈمن انٹری',
        'teacher_btn': '🧑‍🏫 فیکلٹی ٹیچر انٹری',
        'dev_btn': 'سپر ڈیولپر پورٹل',
        'support': 'سپورٹ / واٹس ایپ',
        'lang_toggle': 'English 🇬🇧',
        'download_app': '📥 Download App'
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
            <link rel="manifest" href="/manifest.json">
            <style>
                body {{ 
                    font-family: 'Segoe UI', Arial, sans-serif; text-align: center; margin: 0; padding: 0;
                    height: 100vh; display: flex; justify-content: center; align-items: center;
                    background-color: #f4f6f9; direction: {'rtl' if current_lang == 'ur' else 'ltr'};
                }}
                .lang-switcher-bar {{
                    position: fixed; top: 20px; right: 20px; z-index: 9999; display: flex; gap: 10px;
                }}
                .lang-btn, .catalog-btn {{
                    background: #ffffff; color: #28a745; border: 1px solid #28a745;
                    padding: 8px 16px; font-weight: bold; border-radius: 20px;
                    text-decoration: none; font-size: 13px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);
                    transition: 0.2s; display: inline-flex; align-items: center;
                }}
                .lang-btn:hover, .catalog-btn:hover {{
                    background: #28a745; color: white;
                }}
                .catalog-btn {{ color: #198754; border-color: #198754; }}
                .catalog-btn:hover {{ background: #198754; }}
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
                <a href="/static/app-release-signed.apk" class="catalog-btn" download>{t['download_app']}</a>
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
            <script>
                if ('serviceWorker' in navigator) {{
                    window.addEventListener('load', () => {{
                        navigator.serviceWorker.register('/sw.js', {{ scope: '/' }}).catch(() => {{}});
                    }});
                }}
            </script>
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
        cursor = conn.cursor()
        
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
        <link rel="manifest" href="/manifest.json">
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
# 3. COLLEGE ADMIN DASHBOARD LOGIC
@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return sync_json_response('error', 403, message='Queued action belongs to a different admin account.')
    college_id = session.get('user_id')
    current_username = session.get('user')
    college_name = session.get('college_name')
    current_lang = session.get('lang', 'en')
    
    selected_program = request.args.get('program', '')
    selected_part = request.args.get('part', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        action = request.form.get('action')
        mutation_actions = {
            'change_username', 'add_teacher', 'add_student', 'edit_teacher_admin',
            'edit_student_admin', 'delete_teacher', 'delete_student'
        }
        if is_offline_sync_request() and action not in mutation_actions:
            conn.close()
            return sync_json_response('error', 400, message='Unsupported admin action.')
        if action in mutation_actions:
            try:
                already_processed = begin_sync_operation(cursor)
            except ValueError as error:
                conn.close()
                return sync_json_response('error', 400, message=str(error))
            if already_processed:
                conn.commit()
                conn.close()
                return sync_json_response()
        if action == 'change_username':
            new_user = request.form['new_username']
            cursor.execute('UPDATE admins SET username = %s WHERE id = %s', (new_user, college_id))
            conn.commit()
            session['user'] = new_user
            current_username = new_user
        elif action == 'add_teacher':
            cursor.execute('INSERT INTO teachers (teacher_id, name, username, password, subject, college_id) VALUES (%s, %s, %s, %s, %s, %s)',
                         (request.form.get('teacher_id', ''), request.form['name'], request.form['username'], request.form['password'], request.form.get('subject', ''), college_id))
            conn.commit()
        elif action == 'add_student':
            cursor.execute('INSERT INTO students (roll_no, student_name, father_name, phone_number, program, part, college_id) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form.get('phone_number', ''), request.form['program'], request.form['part'], college_id))
            conn.commit()
        elif action == 'edit_teacher_admin':
            # 🛠️ FIXED 100% OPTIONAL: Teacher details ko edit karte waqt optional values khali chordne par system null strings handle karega
            t_id_val = request.form.get('teacher_id', '').strip()
            subject_val = request.form.get('subject', '').strip()
            cursor.execute('UPDATE teachers SET teacher_id=%s, name=%s, username=%s, password=%s, subject=%s WHERE id=%s AND college_id=%s',
                         (t_id_val, request.form['name'], request.form['username'], request.form['password'], subject_val, request.form['id'], college_id))
            conn.commit()
        elif action == 'edit_student_admin':
            # 🛠️ FIXED 100% OPTIONAL: Student phone number edit karte waqt khali chordne par string configuration crash nahi hogi
            phone_val = request.form.get('phone_number', '').strip()
            cursor.execute('UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, phone_number=%s, program=%s, part=%s WHERE id=%s AND college_id=%s',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], phone_val, request.form['program'], request.form['part'], request.form['id'], college_id))
            conn.commit()
        elif action == 'delete_teacher':
            teacher_id = request.form.get('id')
            cursor.execute('DELETE FROM teachers WHERE id=%s AND college_id=%s', (teacher_id, college_id))
            conn.commit()
        elif action == 'delete_student':
            student_id = request.form.get('id')
            delete_student_record(cursor, student_id, college_id)
            conn.commit()
        if is_offline_sync_request():
            conn.close()
            return sync_json_response()
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

@app.route('/admin/import_students', methods=['POST'])
def import_students():
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({"error": "Unauthorized"}), 401
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return sync_json_response('error', 403, message='Queued action belongs to a different admin account.')

    payload = request.get_json()
    rows = payload.get('rows') if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or len(rows) > 500:
        return jsonify({"error": "Provide between 1 and 500 student rows."}), 400

    clean_rows = []
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            return jsonify({"error": f"Row {row_number} is invalid."}), 400
        fields = {}
        for field in ('roll_no', 'student_name', 'father_name', 'phone_number', 'program', 'part'):
            value = row.get(field, '')
            if not isinstance(value, str):
                return jsonify({"error": f"Row {row_number}: {field} must be text."}), 400
            fields[field] = value.strip()
        if not all(fields[field] for field in ('roll_no', 'student_name', 'father_name', 'program', 'part')):
            return jsonify({"error": f"Row {row_number} is missing a required value."}), 400
        clean_rows.append(fields)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            already_processed = begin_sync_operation(cursor)
        except ValueError as error:
            return sync_json_response('error', 400, message=str(error))
        if already_processed:
            conn.commit()
            return sync_json_response(imported=0, skipped=len(clean_rows))
        imported = 0
        for row in clean_rows:
            cursor.execute(
                'INSERT INTO students (roll_no, student_name, father_name, phone_number, program, part, college_id) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (roll_no, college_id) DO NOTHING',
                (row['roll_no'], row['student_name'], row['father_name'], row['phone_number'],
                 row['program'], row['part'], session['user_id'])
            )
            imported += cursor.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return sync_json_response(imported=imported, skipped=len(clean_rows) - imported)

# 4. SUPER DEVELOPER PORTAL
@app.route('/developer/dashboard', methods=['GET', 'POST'])
def developer_dashboard():
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('developer', session.get('user')):
        return sync_json_response('error', 403, message='Queued action belongs to a different developer account.')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        action = request.form.get('action')
        mutation_actions = {
            'create_new_college', 'update_college_periods', 'edit_college_admin_dev',
            'update_teacher_dev', 'update_student_dev'
        }
        if is_offline_sync_request() and action not in mutation_actions:
            conn.close()
            return sync_json_response('error', 400, message='Unsupported developer action.')
        if action in mutation_actions:
            try:
                already_processed = begin_sync_operation(cursor)
            except ValueError as error:
                conn.close()
                return sync_json_response('error', 400, message=str(error))
            if already_processed:
                conn.commit()
                conn.close()
                return sync_json_response()
        if action == 'create_new_college':
            try:
                cursor.execute('INSERT INTO admins (college_name, username, password, total_periods) VALUES (%s, %s, %s, %s)', 
                             (request.form['college_name'], request.form['username'], request.form['password'], request.form.get('total_periods', 6)))
                conn.commit()
            except (sqlite3.IntegrityError, psycopg2.IntegrityError):
                conn.rollback()
                if is_offline_sync_request():
                    conn.close()
                    return sync_json_response('error', 409, message='That admin username already exists.')
                conn.close()
                return 'That admin username already exists.', 409
        elif action == 'update_college_periods':
            cursor.execute('UPDATE admins SET total_periods=%s WHERE id=%s', (request.form['total_periods'], request.form['college_id']))
            conn.commit()
        elif action == 'edit_college_admin_dev':
            cursor.execute('UPDATE admins SET college_name=%s, username=%s, password=%s, total_periods=%s WHERE id=%s',
                         (request.form['college_name'], request.form['username'], request.form['password'], request.form['total_periods'], request.form['id']))
            conn.commit()
        elif action == 'update_teacher_dev':
            cursor.execute('UPDATE teachers SET teacher_id=%s, name=%s, username=%s, password=%s, subject=%s WHERE id=%s',
                         (request.form.get('teacher_id', ''), request.form['name'], request.form['username'], request.form['password'], request.form.get('subject', ''), request.form['id']))
            conn.commit()
        elif action == 'update_student_dev':
            cursor.execute('UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, phone_number=%s, program=%s, part=%s WHERE id=%s',
                         (request.form['roll_no'], request.form['student_name'], request.form['father_name'], request.form.get('phone_number', ''), request.form['program'], request.form['part'], request.form['id']))
            conn.commit()
        if is_offline_sync_request():
            conn.close()
            return sync_json_response()
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
        
    college_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'><b>{c['id']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'><a href='/developer/dashboard?filter_college={c['id']}' style='color:#146c43;font-weight:bold;text-decoration:none;'>{c['college_name']} 🔍</a></td><td style='border:1px solid #a3cfbb;padding:12px;'>{c['username']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>🔑 {c['password']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{c['total_periods']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_c={c['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><form method='POST' action='/developer/delete/college/{c['id']}' onsubmit='return confirm(\"Delete Account Master?\")'><button type='submit' style='color:#dc3545;background:none;border:0;padding:0;font-weight:bold;font-size:12px;'>Delete ❌</button></form></div></td></tr>" for c in colleges])
    teacher_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'>{t['college_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{t['teacher_id']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'>{t['name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{t['username']}</td><td style='border:1px solid #a3cfbb;padding:12px;color:#198754;font-weight:bold;'>{t['password']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{t['subject']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_t={t['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><form method='POST' action='/developer/delete/teacher/{t['id']}' onsubmit='return confirm(\"Delete Teacher?\")'><button type='submit' style='color:#dc3545;background:none;border:0;padding:0;font-weight:bold;font-size:12px;'>Delete ❌</button></form></div></td></tr>" for t in all_teachers])
    student_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'>{s['college_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{s['roll_no']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['student_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['father_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['phone_number']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['program']} ({s['part']})</td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_s={s['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><form method='POST' action='/developer/delete/student/{s['id']}' onsubmit='return confirm(\"Delete Student?\")'><button type='submit' style='color:#dc3545;background:none;border:0;padding:0;font-weight:bold;font-size:12px;'>Delete ❌</button></form></div></td></tr>" for s in all_students])

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
            <link rel="manifest" href="/manifest.json">
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
        <body data-offline-actor="developer:Cukur" data-offline-queue-forms="true">
            <div class="header-bar">
                <h2>🛠️ Çukur Master Developer Panel Control Console</h2>
                <div style="font-weight: bold; font-size: 14px;">📲 Support/WhatsApp: 03426600749</div>
                <a href="/logout" style="color: white; font-weight: bold; text-decoration: none; background: rgba(0,0,0,0.2); padding: 8px 15px; border-radius: 5px;">Log Out ➡️</a>
            </div>
            """ + edit_box + """
            <div class="grid">
                <div class="card">
                    <h3>➕ Add College Account</h3>
                    <form method="POST" action="/developer/create_college">
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
            <script src="/static/offline-sync.js"></script>
            <script>
                if ('serviceWorker' in navigator) {
                    navigator.serviceWorker.register('/sw.js', {scope: '/'})
                        .catch(error => console.error('Service worker registration failed:', error));
                }
            </script>
        </body>
    </html>
    """
# Create college through a dedicated endpoint so Vercel routes the POST explicitly.
@app.route('/developer/create_college', methods=['POST'])
def developer_create_college():
    if 'role' not in session or session['role'] != 'developer':
        return sync_json_response('error', 401, message='Developer login is required.')
    if not offline_sync_actor_matches('developer', session.get('user')):
        return sync_json_response('error', 403, message='Queued action belongs to a different developer account.')

    college_name = request.form.get('college_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    total_periods = request.form.get('total_periods', '6')
    if not college_name or not username or not password:
        return sync_json_response('error', 400, message='College name, username, and password are required.')
    try:
        total_periods = int(total_periods)
    except (TypeError, ValueError):
        return sync_json_response('error', 400, message='Total periods must be a number.')
    if total_periods < 1:
        return sync_json_response('error', 400, message='Total periods must be positive.')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        already_processed = begin_sync_operation(cursor)
        if already_processed:
            conn.commit()
            return sync_json_response()
        cursor.execute(
            'INSERT INTO admins (college_name, username, password, total_periods) VALUES (%s, %s, %s, %s)',
            (college_name, username, password, total_periods)
        )
        conn.commit()
    except ValueError as error:
        conn.rollback()
        return sync_json_response('error', 400, message=str(error))
    except (sqlite3.IntegrityError, psycopg2.IntegrityError):
        conn.rollback()
        return sync_json_response('error', 409, message='That admin username already exists.')
    finally:
        conn.close()

    return sync_json_response()

# 5. DEVELOPER DELETION SYSTEM ENDPOINTS
@app.route('/developer/delete/college/<int:id>', methods=['POST'])
def developer_delete_college(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('developer', session.get('user')):
        return sync_json_response('error', 403, message='Queued action belongs to a different developer account.')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        already_processed = begin_sync_operation(cursor)
    except ValueError as error:
        conn.close()
        return sync_json_response('error', 400, message=str(error))
    if already_processed:
        conn.commit()
        conn.close()
        return sync_json_response()
    cursor.execute('DELETE FROM attendance WHERE college_id = %s', (id,))
    cursor.execute('DELETE FROM students WHERE college_id = %s', (id,))
    cursor.execute('DELETE FROM teachers WHERE college_id = %s', (id,))
    cursor.execute('DELETE FROM admins WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    if is_offline_sync_request():
        return sync_json_response()
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/delete/teacher/<int:id>', methods=['POST'])
def developer_delete_teacher(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('developer', session.get('user')):
        return sync_json_response('error', 403, message='Queued action belongs to a different developer account.')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        already_processed = begin_sync_operation(cursor)
    except ValueError as error:
        conn.close()
        return sync_json_response('error', 400, message=str(error))
    if already_processed:
        conn.commit()
        conn.close()
        return sync_json_response()
    cursor.execute('DELETE FROM teachers WHERE id = %s', (id,))
    conn.commit()
    conn.close()
    if is_offline_sync_request():
        return sync_json_response()
    return redirect(url_for('developer_dashboard'))

@app.route('/developer/delete/student/<int:id>', methods=['POST'])
def developer_delete_student(id):
    if 'role' not in session or session['role'] != 'developer': return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('developer', session.get('user')):
        return sync_json_response('error', 403, message='Queued action belongs to a different developer account.')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        already_processed = begin_sync_operation(cursor)
    except ValueError as error:
        conn.close()
        return sync_json_response('error', 400, message=str(error))
    if already_processed:
        conn.commit()
        conn.close()
        return sync_json_response()
    cursor.execute('SELECT college_id FROM students WHERE id = %s', (id,))
    student = cursor.fetchone()
    if student:
        delete_student_record(cursor, id, student['college_id'])
    conn.commit()
    conn.close()
    if is_offline_sync_request():
        return sync_json_response()
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
    cursor = conn.cursor()
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
    if 'role' not in session or session['role'] != 'teacher':
        return sync_json_response('error', 401, message='Unauthorized.')
    if not offline_sync_actor_matches('teacher', session.get('user_id')):
        return sync_json_response('error', 403, message='Queued action belongs to a different teacher account.')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return sync_json_response('error', 400, message='Expected a JSON attendance record.')
    roll = data.get('roll')
    status = data.get('status') 
    att_date = data.get('date')
    if not isinstance(roll, str) or not roll.strip():
        return sync_json_response('error', 400, message='A student roll number is required.')
    if status not in {'Present', 'Absent', 'Leave', 'Vacation'}:
        return sync_json_response('error', 400, message='Unsupported attendance status.')
    if not isinstance(att_date, str) or not att_date:
        return sync_json_response('error', 400, message='An attendance date is required.')
    try:
        period_no = int(data.get('period', 1))
    except (TypeError, ValueError):
        return sync_json_response('error', 400, message='Period must be a number.')
    if period_no < 1:
        return sync_json_response('error', 400, message='Period must be positive.')
    teacher_username = session.get('user')
    college_id = session.get('college_id')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        already_processed = begin_sync_operation(cursor)
    except ValueError as error:
        conn.close()
        return sync_json_response('error', 400, message=str(error))
    if already_processed:
        conn.commit()
        conn.close()
        return sync_json_response(current_status=status)
    cursor.execute(
        'SELECT id FROM students WHERE roll_no = %s AND college_id = %s',
        (roll.strip(), college_id)
    )
    if not cursor.fetchone():
        conn.rollback()
        conn.close()
        return sync_json_response('error', 404, message='Student not found in this college.')
    cursor.execute('SELECT id FROM attendance WHERE student_roll = %s AND attendance_date = %s AND period_no = %s AND college_id = %s', (roll, att_date, period_no, college_id))
    existing = cursor.fetchone()
    
    if existing: 
        cursor.execute('UPDATE attendance SET status = %s, marked_by = %s, created_at = CURRENT_TIMESTAMP WHERE id = %s', (status, teacher_username, existing['id']))
    else: 
        cursor.execute('INSERT INTO attendance (student_roll, attendance_date, period_no, status, marked_by, college_id) VALUES (%s, %s, %s, %s, %s, %s)', (roll, att_date, period_no, status, teacher_username, college_id))
        
    conn.commit()
    conn.close()
    return sync_json_response(current_status=status)

# 📥 FIXED REAL APP DOWNLOAD ROUTE LINK INTERFACE: Direct dynamic target redirection mapping to bypass asset errors
@app.route('/download/proposal-pdf')
def download_proposal_pdf():
    # Maps directly to the production dynamic package deployment bundle
    return redirect("https://github.com")

# 📄 CUSTOM STUDENT HISTORICAL REPORT SHEET TRANSCRIPT API
@app.route('/admin/download_student_report/<int:student_id>')
def download_student_report(student_id):
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('welcome'))
    college_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM students WHERE id = %s AND college_id = %s', (student_id, college_id))
    student = cursor.fetchone()
    if not student:
        conn.close()
        return "<h3>Student record not found!</h3>", 404
    roll = student['roll_no']
    cursor.execute('SELECT COUNT(*) as cnt FROM attendance WHERE student_roll = %s AND college_id = %s', (roll, college_id))
    total_days = cursor.fetchone()['cnt']
    cursor.execute('SELECT COUNT(*) as cnt FROM attendance WHERE student_roll = %s AND status = \'Present\' AND college_id = %s', (roll, college_id))
    present_days = cursor.fetchone()['cnt']
    percentage = round((present_days / total_days) * 100, 1) if total_days > 0 else 0.0
    cursor.execute('SELECT attendance_date, period_no, status, marked_by FROM attendance WHERE student_roll = %s AND college_id = %s ORDER BY attendance_date DESC, period_no ASC', (roll, college_id))
    records = cursor.fetchall()
    conn.close()
    
    rows_html = "".join([f"<tr><td style='border:1px solid #dee2e6;padding:10px;'>{r['attendance_date']}</td><td style='border:1px solid #dee2e6;padding:10px;text-align:center;'>Period {r['period_no']}</td><td style='border:1px solid #dee2e6;padding:10px;font-weight:bold;color:{'#28a745' if r['status']=='Present' else '#dc3545' if r['status']=='Absent' else '#ffc107' if r['status']=='Leave' else '#6f42c1'};'>{r['status']}</td><td style='border:1px solid #dee2e6;padding:10px;'>{r['marked_by']}</td></tr>" for r in records])
    if not records: rows_html = "<tr><td colspan='4' style='text-align:center;padding:20px;color:#6c757d;'>No attendance history logged yet.</td></tr>"
    
    return f"""<html><head><title>Report_{roll}</title><style>body {{ font-family: 'Segoe UI', Arial; padding: 30px; color: #333; }} .report-header {{ border-bottom: 3px solid #198754; padding-bottom: 15px; margin-bottom: 25px; }} .student-info {{ background: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 25px; display: flex; flex-wrap: wrap; gap: 20px; }} .info-item {{ flex: 1; min-width: 200px; font-size: 14px; }} table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }} th {{ background-color: #198754 !important; color: white !important; font-weight: bold; border: 1px solid #198754; padding: 12px; }} .badge-pct {{ background: #198754; color: white; padding: 4px 10px; border-radius: 20px; }} </style></head><body onload="window.print()"><div class="report-header"><h2 style="margin:0;color:#198754;">📊 ÇUKUR EDUCATIONAL MATRIX LOGS</h2></div><div class="student-info"><div class="info-item"><b>Name:</b> {student['student_name']}</div><div class="info-item"><b>Father:</b> {student['father_name']}</div><div class="info-item"><b>Roll No:</b> {roll}</div><div class="info-item"><b>Class:</b> {student['program']} ({student['part']})</div><div class="info-item"><b>Attendance:</b> <span class="badge-pct">{percentage}%</span></div></div><table><thead><tr><th>Date</th><th>Period</th><th>Status</th><th>Faculty</th></tr></thead><tbody>{rows_html}</tbody></table></body></html>"""

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

application = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
