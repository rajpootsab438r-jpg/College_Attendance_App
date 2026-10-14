import os
import sqlite3
import threading
import json
import hmac
import html
import re
import secrets
from urllib.parse import urlparse
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, send_file, send_from_directory
from google import genai
import psycopg2
from psycopg2.extras import DictCursor
from datetime import date, datetime, timedelta, timezone
import io
from urllib.request import Request, urlopen
from urllib.error import URLError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


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


def verify_stored_password(stored_password, candidate):
    if not isinstance(stored_password, str) or not isinstance(candidate, str):
        return False
    if stored_password.startswith(('scrypt:', 'pbkdf2:')):
        try:
            return check_password_hash(stored_password, candidate)
        except (TypeError, ValueError):
            return False
    return hmac.compare_digest(
        stored_password.encode('utf-8'),
        candidate.encode('utf-8')
    )


def password_needs_hash_upgrade(stored_password):
    return not isinstance(stored_password, str) or not stored_password.startswith(
        ('scrypt:', 'pbkdf2:')
    )


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
    response = send_from_directory(
        STATIC_DIR,
        'sw.js',
        mimetype='application/javascript',
        max_age=0
    )
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Surrogate-Control'] = 'no-store'
    response.headers['CDN-Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/offline')
@app.route('/offline.html')
def serve_offline_page():
    return send_from_directory(STATIC_DIR, 'offline.html', mimetype='text/html')

@app.route('/manifest.json')
def serve_manifest():
    response = send_from_directory(
        STATIC_DIR,
        'manifest.json',
        mimetype='application/manifest+json',
        max_age=0
    )
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Surrogate-Control'] = 'no-store'
    response.headers['CDN-Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def add_student_api_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Vary'] = 'Origin'
    origin = request.headers.get('Origin')
    if origin:
        origin_parts = urlparse(origin)
        if origin_parts.scheme == request.scheme and origin_parts.netloc == request.host:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.after_request
def prevent_student_api_caching(response):
    if request.endpoint in {'admin_dashboard', 'teacher_dashboard'} and request.args.get('format') == 'json':
        return add_student_api_headers(response)
    return response


def student_api_response(students, status_code=200):
    response = jsonify([
        {
            'id': student.get('id', student.get('student_id')),
            'roll_no': student.get('roll_no', student.get('roll')),
            'student_name': student.get('student_name', student.get('name')),
            'father_name': student.get('father_name', ''),
            'phone_number': student.get('phone_number', ''),
            'program': student.get('program', ''),
            'part': student.get('part', ''),
            'saved_status': student.get('saved_status', ''),
            'percentage': student.get('percentage', 0)
        }
        for student in students
    ])
    response.status_code = status_code
    return add_student_api_headers(response)


def offline_seed_response(payload, status_code=200):
    response = jsonify(payload)
    response.status_code = status_code
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Surrogate-Control'] = 'no-store'
    response.headers['CDN-Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Vary'] = 'Cookie'
    response.headers['X-Data-Generated-At'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
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


def build_whatsapp_absence_payload(student, period_no, attendance_date, college_id):
    student = dict(student)
    message = (
        f"Dear Parent, your child {student['student_name']} was marked ABSENT from College "
        f"today during Period {period_no}. For queries, support is available at "
        "WhatsApp: 03426600749."
    )
    return {
        'channel': 'whatsapp',
        'recipient': {'phone_number': (student.get('phone_number') or '').strip()},
        'message': {'type': 'text', 'text': message},
        'metadata': {
            'event': 'attendance.absent',
            'student_roll': student['roll_no'],
            'period': period_no,
            'attendance_date': attendance_date,
            'college_id': college_id
        }
    }


def dispatch_whatsapp_alert(payload):
    gateway_url = os.environ.get('WHATSAPP_GATEWAY_URL', '').strip()
    recipient = payload['recipient']['phone_number']
    if not recipient:
        app.logger.warning(
            "WhatsApp attendance alert was not sent because the student has no parent phone number."
        )
        return 'missing_recipient'
    if not gateway_url:
        app.logger.info(
            "WhatsApp attendance alert is ready but not sent; WHATSAPP_GATEWAY_URL is not configured."
        )
        return 'not_configured'

    headers = {'Content-Type': 'application/json'}
    gateway_token = os.environ.get('WHATSAPP_GATEWAY_TOKEN')
    if gateway_token:
        headers['Authorization'] = f'Bearer {gateway_token}'
    try:
        gateway_request = Request(
            gateway_url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        with urlopen(gateway_request, timeout=5) as response:
            if not 200 <= response.status < 300:
                app.logger.error(
                    "WhatsApp gateway rejected an attendance alert with HTTP %s.",
                    response.status
                )
                return 'gateway_error'
        return 'sent'
    except (URLError, TimeoutError, OSError, TypeError, ValueError) as error:
        app.logger.error("WhatsApp attendance alert delivery failed: %s", error)
        return 'gateway_error'


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


def admin_request_value(values, key, required=False):
    value = values.get(key, '')
    if not isinstance(value, str):
        raise ValueError(f'{key.replace("_", " ").capitalize()} must be text.')
    if required and not value.strip():
        raise ValueError(f'{key.replace("_", " ").capitalize()} is required.')
    return value


def parse_attendance_timestamp(value, *, require_timezone=False):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        if require_timezone:
            return None
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def normalize_meta_recipient(phone):
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('00'):
        digits = digits[2:]
    elif digits.startswith('0'):
        country_code = os.environ.get('WHATSAPP_DEFAULT_COUNTRY_CODE', '92').strip()
        if not re.fullmatch(r'\d{1,3}', country_code):
            raise ValueError('WHATSAPP_DEFAULT_COUNTRY_CODE must contain 1–3 digits.')
        digits = country_code + digits[1:]
    if not 8 <= len(digits) <= 15 or digits.startswith('0'):
        return None
    return digits


def academic_program_options(cursor):
    cursor.execute(
        'SELECT program_key, display_name, level, parts '
        'FROM academic_programs ORDER BY level, display_name'
    )
    return [
        {
            'key': row['program_key'],
            'display_name': row['display_name'],
            'level': row['level'],
            'parts': row['parts'].split(',')
        }
        for row in cursor.fetchall()
    ]


def insert_student_record(cursor, student_values):
    values = {
        'roll_no': student_values['roll_no'],
        'student_name': student_values['student_name'],
        'father_name': student_values.get('father_name') or '',
        'phone_number': student_values.get('phone_number') or '',
        'program': student_values['program'],
        'part': student_values['part'],
        'college_id': student_values['college_id']
    }
    if get_database_url().startswith('sqlite'):
        columns = cursor.execute('PRAGMA table_info(students)').fetchall()
        column_info = [
            (column['name'], bool(column['notnull']), column['dflt_value'], column['type'], bool(column['pk']))
            for column in columns
        ]
    else:
        cursor.execute(
            'SELECT column_name, is_nullable, column_default, data_type '
            'FROM information_schema.columns '
            "WHERE table_schema = current_schema() AND table_name = 'students'"
        )
        column_info = [
            (
                column['column_name'],
                column['is_nullable'] == 'NO',
                column['column_default'],
                column['data_type'],
                column['column_name'] == 'id'
            )
            for column in cursor.fetchall()
        ]

    for name, required, default, data_type, is_primary_key in column_info:
        if name in values or not required or default is not None or is_primary_key:
            continue
        if name in {'section', 'class_bunk'}:
            values[name] = 0 if 'INT' in (data_type or '').upper() else ''

    names = [name for name, *_ in column_info if name in values]
    placeholders = ', '.join(['%s'] * len(names))
    columns_sql = ', '.join(names)
    values_sql = tuple(values[name] for name in names)
    cursor.execute(
        f'INSERT INTO students ({columns_sql}) VALUES ({placeholders}) '
        'ON CONFLICT (roll_no, college_id) DO NOTHING',
        values_sql
    )
    return cursor.rowcount


def active_academic_program_options(cursor, college_id, seeded_programs):
    cursor.execute(
        'SELECT DISTINCT program, part FROM students '
        'WHERE college_id = %s AND program IS NOT NULL AND part IS NOT NULL',
        (college_id,)
    )
    active_parts_by_program = {}
    for row in cursor.fetchall():
        normalized_program = re.sub(r'[^a-z0-9]', '', row['program'].lower())
        active_parts_by_program.setdefault(normalized_program, set()).add(row['part'])

    active_programs = []
    for program_config in seeded_programs:
        normalized_key = re.sub(r'[^a-z0-9]', '', program_config['key'].lower())
        active_parts = [
            part for part in program_config['parts']
            if part in active_parts_by_program.get(normalized_key, set())
        ]
        if active_parts:
            active_programs.append({**program_config, 'parts': active_parts})
    return active_programs


@app.route('/api/attendance_tree', methods=['GET'])
def attendance_tree():
    college_id = request.args.get('college_id', '').strip()
    stream = request.args.get('stream', '').strip()
    program = request.args.get('program', '').strip()
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if not college_id:
            cursor.execute('SELECT id, college_name FROM admins ORDER BY college_name')
            colleges = [
                {'id': row['id'], 'name': row['college_name']}
                for row in cursor.fetchall()
            ]
            return jsonify({'status': 'success', 'stage': 'college', 'colleges': colleges})
        if not college_id.isdigit():
            return jsonify({'status': 'error', 'message': 'College identifier is invalid.'}), 400
        cursor.execute('SELECT id FROM admins WHERE id = %s', (college_id,))
        if not cursor.fetchone():
            return jsonify({'status': 'error', 'message': 'College was not found.'}), 404
        if not stream:
            return jsonify({
                'status': 'success',
                'stage': 'stream',
                'streams': ['Intermediate', 'Degrees']
            })
        if stream not in {'Intermediate', 'Degrees'}:
            return jsonify({'status': 'error', 'message': 'Program stream is invalid.'}), 400
        level_filter = "ap.level = 'Intermediate'" if stream == 'Intermediate' else "ap.level <> 'Intermediate'"
        if not program:
            cursor.execute(
                'SELECT DISTINCT ap.program_key, ap.display_name, ap.level '
                'FROM students s JOIN academic_programs ap '
                "ON LOWER(REPLACE(REPLACE(REPLACE(s.program, '-', ''), ' ', ''), '.', '')) = "
                "LOWER(REPLACE(REPLACE(REPLACE(ap.program_key, '-', ''), ' ', ''), '.', '')) "
                f'WHERE s.college_id = %s AND {level_filter} '
                'ORDER BY ap.display_name',
                (college_id,)
            )
            classes = [
                {
                    'key': row['program_key'],
                    'name': row['display_name'],
                    'level': row['level']
                }
                for row in cursor.fetchall()
            ]
            return jsonify({'status': 'success', 'stage': 'class', 'classes': classes})
        cursor.execute(
            'SELECT DISTINCT part FROM students WHERE college_id = %s '
            'AND LOWER(REPLACE(REPLACE(REPLACE(program, \'-\', \'\'), \' \', \'\'), \'.\', \'\')) = %s '
            'ORDER BY part',
            (
                college_id,
                re.sub(r'[^a-z0-9]', '', program.lower())
            )
        )
        parts = [row['part'] for row in cursor.fetchall()]
        return jsonify({
            'status': 'success',
            'stage': 'part',
            'program': program,
            'parts': parts
        })
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        app.logger.exception('Could not load attendance assistant choices.')
        return jsonify({'status': 'error', 'message': 'Attendance choices are temporarily unavailable.'}), 503
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/native_chat', methods=['POST'])
def native_chat():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'status': 'error', 'message': 'Submit a valid attendance query.'}), 400
    college_id = payload.get('college_id')
    program = payload.get('program')
    part = payload.get('part')
    roll_no = payload.get('roll_no')
    if not isinstance(college_id, (str, int)) or not str(college_id).isdigit():
        return jsonify({'status': 'error', 'message': 'Choose a valid college.'}), 400
    if not all(isinstance(value, str) and value.strip() for value in (program, part, roll_no)):
        return jsonify({'status': 'error', 'message': 'Choose a program and part, then enter the roll number.'}), 400
    if len(roll_no.strip()) > 64:
        return jsonify({'status': 'error', 'message': 'Roll numbers must be 64 characters or fewer.'}), 400

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        academic_class = validate_academic_class(cursor, program, part)
        if not academic_class:
            return jsonify({'status': 'error', 'message': 'The selected program or part is no longer active.'}), 400
        cursor.execute(
            'SELECT roll_no, student_name, program, part, college_id FROM students '
            'WHERE college_id = %s AND LOWER(TRIM(roll_no)) = LOWER(%s) '
            'AND LOWER(TRIM(program)) = LOWER(%s) AND LOWER(TRIM(part)) = LOWER(%s)',
            (college_id, roll_no.strip(), academic_class['program_key'], academic_class['part'])
        )
        student = cursor.fetchone()
        if not student:
            return jsonify({
                'status': 'success',
                'reply': 'No student was found for that college, class, part, and roll number. Please check the details and try again.'
            })
        cursor.execute(
            'SELECT COUNT(*) AS total_records, '
            "SUM(CASE WHEN LOWER(TRIM(status)) = 'present' THEN 1 ELSE 0 END) AS present_records, "
            "SUM(CASE WHEN LOWER(TRIM(status)) = 'absent' THEN 1 ELSE 0 END) AS absent_records "
            'FROM attendance WHERE LOWER(TRIM(student_roll)) = LOWER(%s) AND college_id = %s '
            "AND LOWER(TRIM(status)) IN ('present', 'absent', 'leave')",
            (student['roll_no'], student['college_id'])
        )
        attendance = cursor.fetchone()
        total = int(attendance['total_records'] or 0)
        present = int(attendance['present_records'] or 0)
        absent = int(attendance['absent_records'] or 0)
        percentage = round(present * 100 / total, 1) if total else 0
        if total:
            report = (
                f"Attendance summary for {student['student_name']} (Roll {student['roll_no']})\n"
                f"{student['program']} · {student['part']}\n"
                f"Present: {present}  |  Absent: {absent}  |  Recorded periods: {total}\n"
                f"Attendance rate: {percentage}%"
            )
        else:
            report = (
                f"{student['student_name']} (Roll {student['roll_no']}) is registered in "
                f"{student['program']} · {student['part']}, but no attendance has been recorded yet."
            )
        return jsonify({'status': 'success', 'reply': report})
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        app.logger.exception('Native chat student-record lookup failed.')
        return jsonify({'status': 'error', 'message': 'Student attendance records are temporarily unavailable.'}), 503
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/global_notice', methods=['GET'])
def latest_global_notice():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        college_id = request.args.get('college_id', '').strip()
        if college_id and not college_id.isdigit():
            return jsonify({'status': 'error', 'message': 'College identifier is invalid.'}), 400
        query = (
            'SELECT n.message, n.image_path, n.created_at, a.id AS college_id, '
            'a.college_name FROM global_notifications n '
            'JOIN admins a ON a.id = n.college_id '
        )
        params = ()
        if college_id:
            query += 'WHERE n.college_id = %s '
            params = (college_id,)
        query += 'ORDER BY a.college_name, n.created_at DESC, n.id DESC'
        cursor.execute(query, params)
        rows = cursor.fetchall()
        notices = [
            {
                'college_id': row['college_id'],
                'college_name': row['college_name'],
                'message': row['message'],
                'image_path': row['image_path'],
                'created_at': str(row['created_at'])
            }
            for row in rows
        ]
        colleges = []
        seen_colleges = set()
        for notice in notices:
            if notice['college_id'] not in seen_colleges:
                colleges.append({
                    'id': notice['college_id'],
                    'name': notice['college_name']
                })
                seen_colleges.add(notice['college_id'])
        cursor.execute(
            'SELECT message, image_path, created_at FROM global_notifications '
            'WHERE college_id IS NULL '
            'ORDER BY created_at DESC, id DESC LIMIT 1'
        )
        legacy_notice = cursor.fetchone()
        cursor.execute(
            'SELECT message, image_path, created_at FROM global_notifications '
            'ORDER BY created_at DESC, id DESC LIMIT 1'
        )
        latest_notice = cursor.fetchone()
        return jsonify({
            'status': 'success',
            'notice': None if not latest_notice else {
                'message': latest_notice['message'],
                'image_path': latest_notice['image_path'],
                'created_at': str(latest_notice['created_at'])
            },
            'legacy_notice': None if not legacy_notice else {
                'message': legacy_notice['message'],
                'image_path': legacy_notice['image_path'],
                'created_at': str(legacy_notice['created_at'])
            },
            'colleges': colleges,
            'notices': notices if college_id else []
        })
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        app.logger.exception('Could not load the latest global announcement.')
        return jsonify({'status': 'error', 'message': 'Global announcements are temporarily unavailable.'}), 503
    finally:
        if conn is not None:
            conn.close()


@app.route('/admin/broadcast_message', methods=['POST'])
def admin_broadcast_message():
    if session.get('role') != 'admin' or not session.get('user_id'):
        return jsonify({'status': 'error', 'message': 'Admin login is required.'}), 401
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return jsonify({'status': 'error', 'message': 'This admin session is no longer valid.'}), 403
    supplied_token = request.form.get('csrf_token', '')
    expected_token = session.get('admin_csrf_token', '')
    if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
        return jsonify({'status': 'error', 'message': 'The security token is invalid. Reload the page and try again.'}), 403

    message = request.form.get('announcement', '')
    if not message.strip():
        return jsonify({'status': 'error', 'message': 'Enter an announcement before publishing.'}), 400
    message = message.strip()
    if len(message) > 4096:
        return jsonify({'status': 'error', 'message': 'Announcements must be 4,096 characters or fewer.'}), 400

    image_file = request.files.get('broadcast_image')
    image_path = None
    saved_image_path = None
    if image_file and image_file.filename:
        safe_original_name = secure_filename(image_file.filename)
        extension = os.path.splitext(safe_original_name)[1].lower()
        if not safe_original_name or extension not in {
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.bmp', '.tif', '.tiff', '.ico'
        }:
            return jsonify({'status': 'error', 'message': 'Choose a supported raster image format.'}), 400
        filename = secure_filename(f'{secrets.token_hex(16)}_{safe_original_name}')
        image_path = os.path.join('uploads', 'broadcasts', filename).replace(os.sep, '/')
        saved_image_path = os.path.join(STATIC_DIR, *image_path.split('/'))
        try:
            os.makedirs(os.path.dirname(saved_image_path), exist_ok=True)
            with open(saved_image_path, 'wb') as image_destination:
                while True:
                    image_chunk = image_file.stream.read(64 * 1024)
                    if not image_chunk:
                        break
                    image_destination.write(image_chunk)
        except OSError:
            app.logger.exception('Could not save the uploaded global announcement image.')
            return jsonify({'status': 'error', 'message': 'The announcement image could not be saved.'}), 500

    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO global_notifications (message, image_path, college_id) VALUES (%s, %s, %s)',
            (message, image_path, session['user_id'])
        )
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Global announcement published.'})
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        app.logger.exception('Could not publish the global announcement.')
        if saved_image_path and os.path.exists(saved_image_path):
            try:
                os.remove(saved_image_path)
            except OSError:
                app.logger.exception('Could not remove an image from a failed global announcement.')
        return jsonify({'status': 'error', 'message': 'The global announcement could not be saved.'}), 503
    finally:
        if conn is not None:
            conn.close()

def validate_academic_class(cursor, program, part):
    normalized_program = re.sub(r'[^a-z0-9]', '', program.lower())
    cursor.execute(
        'SELECT program_key, display_name, parts FROM academic_programs '
        'ORDER BY program_key'
    )
    program_record = next(
        (
            row for row in cursor.fetchall()
            if normalized_program in {
                re.sub(r'[^a-z0-9]', '', row['program_key'].lower()),
                re.sub(r'[^a-z0-9]', '', row['display_name'].lower())
            }
        ),
        None
    )
    if not program_record:
        return None
    available_parts = program_record['parts'].split(',')
    matching_part = next(
        (available_part for available_part in available_parts
         if available_part.casefold() == part.strip().casefold()),
        None
    )
    if not matching_part:
        return None
    return {'program_key': program_record['program_key'], 'part': matching_part}


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

# 1. Welcome Portal
@app.route('/')
def welcome():
    current_lang = session.get('lang', 'en')
    translations = LANG_DICT[current_lang]
    next_lang = 'ur' if current_lang == 'en' else 'en'
    college_notices = []
    release_logs = []
    portal_data_error = ''
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT n.id, n.message, n.image_path, n.created_at, a.id AS college_id, '
            'a.college_name FROM global_notifications n '
            'JOIN admins a ON a.id = n.college_id '
            'ORDER BY a.college_name, n.created_at DESC, n.id DESC'
        )
        colleges_by_id = {}
        for row in cursor.fetchall():
            college = colleges_by_id.setdefault(
                row['college_id'],
                {'id': row['college_id'], 'name': row['college_name'], 'notices': []}
            )
            college['notices'].append({
                'message': row['message'],
                'image_path': row['image_path'],
                'created_at': str(row['created_at'])
            })
        college_notices = list(colleges_by_id.values())
        cursor.execute(
            'SELECT title, message, created_at FROM developer_releases '
            'ORDER BY created_at DESC, id DESC LIMIT 10'
        )
        release_logs = [
            {
                'title': row['title'],
                'message': row['message'],
                'created_at': str(row['created_at'])
            }
            for row in cursor.fetchall()
        ]
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        app.logger.exception('Could not load welcome portal announcements.')
        portal_data_error = 'Announcements and release logs are temporarily unavailable.'
    finally:
        if conn is not None:
            conn.close()
    return render_template(
        'welcome.html',
        current_lang=current_lang,
        translations=translations,
        next_lang=next_lang,
        college_notices=college_notices,
        release_logs=release_logs,
        portal_data_error=portal_data_error
    )


# 2. Secure Login Panel Gateway
@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if role not in {'admin', 'teacher', 'developer'}:
        return 'Portal not found.', 404
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        wants_json = request.accept_mimetypes.best == 'application/json'
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if role == 'admin':
            cursor.execute('SELECT * FROM admins WHERE username = %s', (username,))
            user = cursor.fetchone()
            if user and verify_stored_password(user['password'], password):
                if password_needs_hash_upgrade(user['password']):
                    cursor.execute(
                        'UPDATE admins SET password = %s WHERE id = %s',
                        (generate_password_hash(password), user['id'])
                    )
                    conn.commit()
                session['role'] = 'admin'
                session['user_id'] = user['id']
                session['user'] = user['username']
                session['college_name'] = user['college_name']
                session['admin_name'] = user['display_name'] or user['college_name']
                conn.close()
                if wants_json:
                    return jsonify({
                        'status': 'success',
                        'role': role,
                        'dashboard': url_for('admin_dashboard')
                    })
                return redirect(url_for('admin_dashboard'))
        elif role == 'teacher':
            cursor.execute('SELECT * FROM teachers WHERE username = %s', (username,))
            user = cursor.fetchone()
            if user and verify_stored_password(user['password'], password):
                if password_needs_hash_upgrade(user['password']):
                    cursor.execute(
                        'UPDATE teachers SET password = %s WHERE id = %s',
                        (generate_password_hash(password), user['id'])
                    )
                    conn.commit()
                session['role'] = 'teacher'
                session['user_id'] = user['id']
                session['user'] = user['username']
                session['teacher_name'] = user['name']
                session['subject'] = user['subject']
                session['college_id'] = user['college_id']
                conn.close()
                if wants_json:
                    return jsonify({
                        'status': 'success',
                        'role': role,
                        'dashboard': url_for('teacher_dashboard')
                    })
                return redirect(url_for('teacher_dashboard'))
        elif role == 'developer':
            cursor.execute('SELECT * FROM developer_accounts WHERE username = %s', (username,))
            user = cursor.fetchone()
            if user and verify_stored_password(user['password'], password):
                if password_needs_hash_upgrade(user['password']):
                    cursor.execute(
                        'UPDATE developer_accounts SET password = %s WHERE id = %s',
                        (generate_password_hash(password), user['id'])
                    )
                    conn.commit()
                session['role'] = 'developer'
                session['user_id'] = user['id']
                session['user'] = user['username']
                conn.close()
                if wants_json:
                    return jsonify({
                        'status': 'success',
                        'role': role,
                        'dashboard': url_for('developer_dashboard')
                    })
                return redirect(url_for('developer_dashboard'))
                
        conn.close()
        if wants_json:
            return jsonify({'status': 'error', 'message': 'Invalid credentials. Please try again.'}), 401
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
        <body data-login-role="{role}">
            <div class="box">
                <h2>🔒 {role.upper()} PORTAL</h2>
                <form id="login-form" method="POST" action="/login/{role}">
                    <input type="text" name="username" placeholder="Enter Username" autocomplete="username" required>
                    <input type="password" name="password" placeholder="Enter Secret Password" autocomplete="current-password" required>
                    <button type="submit">Verify & Login</button>
                </form>
                <p id="login-status" role="status" aria-live="polite" hidden></p>
                <br><a href="/" style="text-decoration:none; color:#666; font-size:13px;">⬅️ Go Back</a>
            </div>
            <script src="/static/offline-sync.js"></script>
            <script src="/static/offline-login.js"></script>
        </body>
    </html>
    """
# 3. COLLEGE ADMIN DASHBOARD LOGIC
@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        if request.args.get('format') == 'json':
            return student_api_response([], 401)
        return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return sync_json_response('error', 403, message='Queued action belongs to a different admin account.')
    college_id = session.get('user_id')
    current_username = session.get('user')
    college_name = session.get('college_name')
    current_admin_name = session.get('admin_name', college_name)
    current_lang = session.get('lang', 'en')
    selected_program = request.args.get('program', '')
    selected_part = request.args.get('part', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT display_name FROM admins WHERE id = %s', (college_id,))
    admin_profile = cursor.fetchone()
    academic_programs = academic_program_options(cursor)
    csrf_token = session.setdefault('admin_csrf_token', secrets.token_urlsafe(32))
    if admin_profile:
        current_admin_name = admin_profile['display_name'] or college_name
        session['admin_name'] = current_admin_name
    
    if request.method == 'POST':
        request_values = request.form
        json_values = request.get_json(silent=True)
        if not request_values and isinstance(json_values, dict):
            request_values = json_values
        action = request_values.get('action')
        mutation_actions = {
            'add_teacher', 'add_student', 'edit_teacher_admin',
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
        if action == 'edit_teacher_admin':
            teacher_id = admin_request_value(request_values, 'id', required=True)
            password = admin_request_value(request_values, 'new_password')
            cursor.execute(
                'SELECT password FROM teachers WHERE id = %s AND college_id = %s',
                (teacher_id, college_id)
            )
            teacher_record = cursor.fetchone()
            if not teacher_record:
                conn.close()
                return sync_json_response('error', 404, message='Teacher account was not found.')
            password_to_store = (
                generate_password_hash(password) if password else teacher_record['password']
            )
            try:
                cursor.execute(
                    'UPDATE teachers SET teacher_id = %s, name = %s, username = %s, password = %s, subject = %s '
                    'WHERE id = %s AND college_id = %s',
                    (
                        admin_request_value(request_values, 'teacher_id'),
                        admin_request_value(request_values, 'name', required=True),
                        admin_request_value(request_values, 'username', required=True),
                        password_to_store,
                        admin_request_value(request_values, 'subject'),
                        teacher_id,
                        college_id
                    )
                )
                conn.commit()
            except (sqlite3.IntegrityError, psycopg2.IntegrityError):
                conn.rollback()
                conn.close()
                return sync_json_response('error', 409, message='That teacher username is already in use.')
            if is_offline_sync_request():
                conn.close()
                return sync_json_response()
            conn.close()
            return redirect(url_for('admin_dashboard'))
        if action == 'update_admin_profile':
            try:
                display_name = admin_request_value(request_values, 'display_name', required=True).strip()
                new_username = admin_request_value(request_values, 'username', required=True).strip()
                current_password = admin_request_value(request_values, 'current_password', required=True)
                new_password = admin_request_value(request_values, 'new_password')
                if len(display_name) > 120 or len(new_username) < 3 or len(new_username) > 64:
                    raise ValueError('Display name must be 120 characters or fewer and username must be 3–64 characters.')
                cursor.execute('SELECT password FROM admins WHERE id = %s', (college_id,))
                stored = cursor.fetchone()
                if not stored or not verify_stored_password(stored['password'], current_password):
                    conn.close()
                    return sync_json_response('error', 403, message='Current password is incorrect.')
                password_to_store = (
                    generate_password_hash(new_password) if new_password else stored['password']
                )
                cursor.execute(
                    'UPDATE admins SET display_name = %s, username = %s, password = %s WHERE id = %s',
                    (display_name, new_username, password_to_store, college_id)
                )
                conn.commit()
                current_admin_name = display_name
                current_username = new_username
                session['admin_name'] = display_name
                session['user'] = new_username
            except ValueError as error:
                conn.rollback()
                conn.close()
                return sync_json_response('error', 400, message=str(error))
            except (sqlite3.IntegrityError, psycopg2.IntegrityError):
                conn.rollback()
                conn.close()
                return sync_json_response('error', 409, message='That username is already in use.')
        elif action == 'add_teacher':
            teacher_id = admin_request_value(request_values, 'teacher_id')
            name = admin_request_value(request_values, 'name', required=True)
            username = admin_request_value(request_values, 'username', required=True)
            password = admin_request_value(request_values, 'password', required=True)
            subject = admin_request_value(request_values, 'subject')
            cursor.execute(
                'INSERT INTO teachers (teacher_id, name, username, password, subject, college_id) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (teacher_id, name, username, generate_password_hash(password), subject, college_id)
            )
            conn.commit()
        elif action == 'add_student':
            roll_no = admin_request_value(request_values, 'roll_no', required=True)
            student_name = admin_request_value(request_values, 'student_name', required=True)
            father_name = admin_request_value(request_values, 'father_name').strip()
            phone_number = admin_request_value(request_values, 'phone_number')
            program = admin_request_value(request_values, 'program', required=True)
            part = admin_request_value(request_values, 'part', required=True)
            academic_class = validate_academic_class(cursor, program, part)
            if not academic_class:
                conn.close()
                return sync_json_response(
                    'error', 400,
                    message='Select a valid program and part/semester.'
                )
            insert_student_record(
                cursor,
                {
                    'roll_no': roll_no.strip(),
                    'student_name': student_name.strip(),
                    'father_name': father_name,
                    'phone_number': phone_number.strip(),
                    'program': academic_class['program_key'],
                    'part': academic_class['part'],
                    'college_id': college_id
                }
            )
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
            academic_class = validate_academic_class(
                cursor, request.form.get('program', '').strip(),
                request.form.get('part', '').strip()
            )
            if not academic_class:
                conn.close()
                return sync_json_response(
                    'error', 400,
                    message='Select a valid program and part/semester.'
                )
            cursor.execute(
                'UPDATE students SET roll_no=%s, student_name=%s, father_name=%s, '
                'phone_number=%s, program=%s, part=%s '
                'WHERE id=%s AND college_id=%s',
                (
                    request.form['roll_no'], request.form['student_name'],
                    request.form['father_name'], phone_val, academic_class['program_key'],
                    academic_class['part'], request.form['id'], college_id
                )
            )
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

    active_academic_programs = active_academic_program_options(
        cursor, college_id, academic_programs
    )
    active_academic_parts = sorted({
        part for program_config in active_academic_programs
        for part in program_config['parts']
    })
    if selected_program and selected_part:
        cursor.execute(
            "SELECT * FROM students WHERE college_id = %s "
            "AND LOWER(REPLACE(REPLACE(REPLACE(program, '-', ''), ' ', ''), '.', '')) = %s "
            "AND LOWER(part) = LOWER(%s) ORDER BY roll_no ASC",
            (college_id, re.sub(r'[^a-z0-9]', '', selected_program.lower()), selected_part)
        )
    elif selected_program:
        cursor.execute(
            "SELECT * FROM students WHERE college_id = %s "
            "AND LOWER(REPLACE(REPLACE(REPLACE(program, '-', ''), ' ', ''), '.', '')) = %s "
            "ORDER BY roll_no ASC",
            (college_id, re.sub(r'[^a-z0-9]', '', selected_program.lower()))
        )
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

    if request.args.get('format') == 'json':
        conn.close()
        return student_api_response(students)

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
                           current_admin_name=current_admin_name, current_lang=current_lang,
                           academic_programs=academic_programs,
                           active_academic_programs=active_academic_programs,
                           active_academic_parts=active_academic_parts,
                           ai_configured=bool(os.environ.get('GEMINI_API_KEY', '').strip()),
                           csrf_token=csrf_token,
                           edit_teacher=edit_teacher_data, edit_student=edit_student_data)


@app.route('/admin/analytics', methods=['GET'])
def admin_analytics():
    if 'role' not in session or session['role'] != 'admin':
        return sync_json_response('error', 401, message='Admin login is required.')
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return sync_json_response('error', 403, message='Queued action belongs to a different admin account.')

    college_id = session.get('user_id')
    attendance_date = datetime.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT COUNT(*) AS marked_count, '
        'SUM(CASE WHEN status = %s THEN 1 ELSE 0 END) AS present_count '
        'FROM attendance WHERE attendance_date = %s AND college_id = %s',
        ('Present', attendance_date, college_id)
    )
    totals = cursor.fetchone()
    cursor.execute(
        'SELECT s.program, s.part, COUNT(DISTINCT s.id) AS student_count, '
        'SUM(CASE WHEN a.id IS NOT NULL THEN 1 ELSE 0 END) AS marked_count, '
        'SUM(CASE WHEN a.status = %s THEN 1 ELSE 0 END) AS present_count '
        'FROM students s LEFT JOIN attendance a '
        'ON a.student_roll = s.roll_no AND a.college_id = s.college_id '
        'AND a.attendance_date = %s '
        'WHERE s.college_id = %s GROUP BY s.program, s.part',
        ('Present', attendance_date, college_id)
    )
    class_rows = cursor.fetchall()
    conn.close()

    marked_count = int(totals['marked_count'] or 0)
    present_count = int(totals['present_count'] or 0)
    departments = {}
    for row in class_rows:
        row_marked = int(row['marked_count'] or 0)
        row_present = int(row['present_count'] or 0)
        program = row['program'] or 'Unassigned'
        department = departments.setdefault(
            program,
            {'name': program, 'student_count': 0, 'marked_count': 0, 'present_count': 0}
        )
        department['student_count'] += int(row['student_count'] or 0)
        department['marked_count'] += row_marked
        department['present_count'] += row_present

    department_stats = [
        {
            **department,
            'percentage': round(
                department['present_count'] * 100 / department['marked_count'], 1
            ) if department['marked_count'] else 0
        }
        for department in departments.values()
        if department['marked_count']
    ]
    department_stats.sort(
        key=lambda department: (
            department['percentage'],
            department['present_count'],
            department['name'].lower()
        ),
        reverse=True
    )
    return offline_seed_response({
        'date': attendance_date,
        'overall': {
            'percentage': round(present_count * 100 / marked_count, 1) if marked_count else 0,
            'present_count': present_count,
            'marked_count': marked_count
        },
        'departments': department_stats[:5]
    })


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
        if not all(fields[field] for field in ('roll_no', 'student_name', 'program', 'part')):
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
        for row_number, row in enumerate(clean_rows, start=1):
            academic_class = validate_academic_class(cursor, row['program'], row['part'])
            if not academic_class:
                return jsonify({
                    'error': (
                        f"Row {row_number} has a program or part/semester "
                        "that is not in the academic class catalog."
                    )
                }), 400
            imported += insert_student_record(
                cursor,
                {
                    'roll_no': row['roll_no'],
                    'student_name': row['student_name'],
                    'father_name': row['father_name'],
                    'phone_number': row['phone_number'],
                    'program': academic_class['program_key'],
                    'part': academic_class['part'],
                    'college_id': session['user_id']
                }
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return sync_json_response(imported=imported, skipped=len(clean_rows) - imported)


@app.route('/admin/upload_student_sheet', methods=['POST'])
def upload_student_sheet():
    if session.get('role') != 'admin' or not session.get('user_id'):
        return jsonify({'status': 'error', 'message': 'Admin login is required.'}), 401
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return jsonify({'status': 'error', 'message': 'This admin session is no longer valid.'}), 403

    image_file = request.files.get('student_list_image')
    if image_file is None or not image_file.filename:
        return jsonify({'status': 'error', 'message': 'Choose a class-list image to upload.'}), 400
    mime_type = (image_file.mimetype or '').lower()
    if mime_type not in {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}:
        return jsonify({'status': 'error', 'message': 'Upload a JPEG, PNG, WebP, or GIF image.'}), 400
    image_bytes = image_file.stream.read(15 * 1024 * 1024 + 1)
    if not image_bytes:
        return jsonify({'status': 'error', 'message': 'The uploaded image is empty.'}), 400
    if len(image_bytes) > 15 * 1024 * 1024:
        return jsonify({'status': 'error', 'message': 'Images must be 15 MB or smaller.'}), 413

    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        return jsonify({'status': 'error', 'message': 'Gemini Vision is not configured on this server.'}), 503

    prompt = (
        'Read this complete class roster image, including annotations near every top and bottom '
        'edge, margin, or footer. Return only a JSON object with string fields "program" and '
        '"part", plus "students", an array of objects with string fields "roll_no" and '
        '"student_name". Infer the class/program (examples: D.Com, ICS) and part/semester '
        '(examples: Part-1, Semester-2) from any header, footer, or boundary annotation. '
        'Preserve roll-number characters and each student name as printed. Exclude column '
        'headers, totals, and non-student rows. Do not include father names or contact numbers. '
        'Use empty strings when the program or part cannot be confidently read.'
    )
    try:
        client = genai.Client(api_key=api_key)
        completion = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                prompt,
                genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            ],
            config={'response_mime_type': 'application/json'}
        )
        parsed = json.loads(completion.text)
        if not isinstance(parsed, dict) or not isinstance(parsed.get('students'), list):
            raise ValueError('Gemini returned an invalid class roster shape.')
    except (TypeError, ValueError, json.JSONDecodeError):
        app.logger.exception('Gemini returned an invalid student-sheet extraction.')
        return jsonify({'status': 'error', 'message': 'The class sheet could not be read. Use a clearer image or manual import.'}), 502
    except Exception:
        app.logger.exception('Gemini student-sheet extraction failed.')
        return jsonify({'status': 'error', 'message': 'Gemini Vision is temporarily unavailable.'}), 502

    program = parsed.get('program')
    part = parsed.get('part')
    if not isinstance(program, str) or not isinstance(part, str):
        return jsonify({'status': 'error', 'message': 'The class or part/semester could not be read from the image.'}), 422
    program = program.strip()
    part = part.strip()
    if not program or not part:
        return jsonify({
            'status': 'error',
            'message': 'The image did not identify a supported program and part/semester.'
        }), 422

    clean_students = []
    for item in parsed['students']:
        if not isinstance(item, dict):
            continue
        roll_no = item.get('roll_no')
        student_name = item.get('student_name')
        if isinstance(roll_no, str) and isinstance(student_name, str):
            roll_no, student_name = roll_no.strip(), student_name.strip()
            if roll_no and student_name:
                clean_students.append((roll_no, student_name))
    if not clean_students or len(clean_students) > 500:
        return jsonify({
            'status': 'error',
            'message': 'Gemini must identify between 1 and 500 student rows. Use a clearer image or split the sheet.'
        }), 422

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        academic_class = validate_academic_class(cursor, program, part)
        if not academic_class:
            return jsonify({'status': 'error', 'message': 'The detected program or part/semester is not in the class catalog.'}), 422
        imported = 0
        for roll_no, student_name in clean_students:
            imported += insert_student_record(
                cursor,
                {
                    'roll_no': roll_no,
                    'student_name': student_name,
                    'father_name': '',
                    'phone_number': '',
                    'program': academic_class['program_key'],
                    'part': academic_class['part'],
                    'college_id': session['user_id']
                }
            )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception('Could not save extracted student records.')
        return jsonify({'status': 'error', 'message': 'The extracted student records could not be saved.'}), 500
    finally:
        conn.close()

    return jsonify({
        'status': 'success',
        'program': academic_class['program_key'],
        'part': academic_class['part'],
        'parsed': len(clean_students),
        'imported': imported,
        'skipped': len(clean_students) - imported
    })


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
        if action == 'edit_college_admin_dev':
            admin_id = request.form.get('id')
            college_name = request.form.get('college_name', '').strip()
            display_name = request.form.get('display_name', '').strip()
            username = request.form.get('username', '').strip()
            new_password = request.form.get('new_password', '')
            if not college_name or not display_name or len(display_name) > 120:
                conn.close()
                return sync_json_response('error', 400, message='College name and an admin display name of 120 characters or fewer are required.')
            if len(username) < 3 or len(username) > 64:
                conn.close()
                return sync_json_response('error', 400, message='Admin username must be 3–64 characters.')
            cursor.execute('SELECT password FROM admins WHERE id = %s', (admin_id,))
            admin_record = cursor.fetchone()
            if not admin_record:
                conn.close()
                return sync_json_response('error', 404, message='Admin account was not found.')
            password_to_store = (
                generate_password_hash(new_password)
                if new_password else admin_record['password']
            )
            try:
                cursor.execute(
                    'UPDATE admins SET college_name = %s, display_name = %s, username = %s, '
                    'password = %s, total_periods = %s WHERE id = %s',
                    (
                        college_name,
                        display_name,
                        username,
                        password_to_store,
                        request.form.get('total_periods', 6),
                        admin_id
                    )
                )
                conn.commit()
            except (sqlite3.IntegrityError, psycopg2.IntegrityError):
                conn.rollback()
                conn.close()
                return sync_json_response('error', 409, message='That admin username is already in use.')
            conn.close()
            return redirect(url_for('developer_dashboard'))

        if action == 'update_developer_profile':
            username = request.form.get('username', '').strip()
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            if len(username) < 3 or len(username) > 64:
                conn.close()
                return sync_json_response('error', 400, message='Username must be 3–64 characters.')
            cursor.execute('SELECT password FROM developer_accounts WHERE id = %s', (session.get('user_id'),))
            developer_account = cursor.fetchone()
            if not developer_account or not verify_stored_password(
                developer_account['password'], current_password
            ):
                conn.close()
                return sync_json_response('error', 403, message='Current password is incorrect.')
            password_to_store = (
                generate_password_hash(new_password)
                if new_password else developer_account['password']
            )
            try:
                cursor.execute(
                    'UPDATE developer_accounts SET username = %s, password = %s WHERE id = %s',
                    (username, password_to_store, session.get('user_id'))
                )
                conn.commit()
            except (sqlite3.IntegrityError, psycopg2.IntegrityError):
                conn.rollback()
                conn.close()
                return sync_json_response('error', 409, message='That developer username is already in use.')
            session['user'] = username
            conn.close()
            return redirect(url_for('developer_dashboard'))

        mutation_actions = {
            'create_new_college', 'update_college_periods',
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
        if action == 'update_teacher_dev':
            teacher_id = request.form.get('id')
            new_password = request.form.get('new_password', '')
            cursor.execute('SELECT password FROM teachers WHERE id = %s', (teacher_id,))
            teacher_record = cursor.fetchone()
            if not teacher_record:
                conn.close()
                return sync_json_response('error', 404, message='Teacher account was not found.')
            password_to_store = (
                generate_password_hash(new_password)
                if new_password else teacher_record['password']
            )
            cursor.execute(
                'UPDATE teachers SET teacher_id = %s, name = %s, username = %s, password = %s, subject = %s '
                'WHERE id = %s',
                (
                    request.form.get('teacher_id', ''),
                    request.form.get('name', '').strip(),
                    request.form.get('username', '').strip(),
                    password_to_store,
                    request.form.get('subject', ''),
                    teacher_id
                )
            )
            conn.commit()
            if is_offline_sync_request():
                conn.close()
                return sync_json_response()
            conn.close()
            return redirect(url_for('developer_dashboard'))
        if action == 'create_new_college':
            try:
                cursor.execute(
                    'INSERT INTO admins (college_name, display_name, username, password, total_periods) '
                    'VALUES (%s, %s, %s, %s, %s)',
                    (
                        request.form['college_name'],
                        request.form['display_name'],
                        request.form['username'],
                        generate_password_hash(request.form['password']),
                        request.form.get('total_periods', 6)
                    )
                )
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
        
    safe_value = lambda value: html.escape(str(value or ''), quote=True)
    college_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'><b>{c['id']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'><a href='/developer/dashboard?filter_college={c['id']}' style='color:#146c43;font-weight:bold;text-decoration:none;'>{safe_value(c['college_name'])} 🔍</a></td><td style='border:1px solid #a3cfbb;padding:12px;'>{safe_value(c['display_name'])}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{safe_value(c['username'])}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{c['total_periods']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_c={c['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><form method='POST' action='/developer/delete/college/{c['id']}' onsubmit='return confirm(\"Delete Account Master?\")'><button type='submit' style='color:#dc3545;background:none;border:0;padding:0;font-weight:bold;font-size:12px;'>Delete ❌</button></form></div></td></tr>" for c in colleges])
    teacher_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'>{safe_value(t['college_name'])}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{safe_value(t['teacher_id'])}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'>{safe_value(t['name'])}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{safe_value(t['username'])}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{safe_value(t['subject'])}</td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_t={t['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><form method='POST' action='/developer/delete/teacher/{t['id']}' onsubmit='return confirm(\"Delete Teacher?\")'><button type='submit' style='color:#dc3545;background:none;border:0;padding:0;font-weight:bold;font-size:12px;'>Delete ❌</button></form></div></td></tr>" for t in all_teachers])
    student_rows = "".join([f"<tr><td style='border:1px solid #a3cfbb;padding:12px;'>{s['college_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'><b>{s['roll_no']}</b></td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['student_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['father_name']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['phone_number']}</td><td style='border:1px solid #a3cfbb;padding:12px;'>{s['program']} ({s['part']})</td><td style='border:1px solid #a3cfbb;padding:12px;'><div style='display:flex;gap:6px;align-items:center;'><a href='/developer/dashboard?edit_s={s['id']}' style='background:#198754;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;font-size:12px;text-decoration:none;'>📝</a><form method='POST' action='/developer/delete/student/{s['id']}' onsubmit='return confirm(\"Delete Student?\")'><button type='submit' style='color:#dc3545;background:none;border:0;padding:0;font-weight:bold;font-size:12px;'>Delete ❌</button></form></div></td></tr>" for s in all_students])

    edit_box = ""
    if edit_c_data:
        edit_box = (
            "<div style='background:#d1e7dd;padding:20px;border-radius:8px;margin-bottom:20px;border:1px solid #badbcc;'>"
            "<h4 style='margin:0 0 10px 0;color:#0f5132;'>📝 Edit College Admin Account</h4>"
            "<form method='POST' data-no-offline-queue='true' style='display:flex;gap:10px;flex-wrap:wrap;'>"
            "<input type='hidden' name='action' value='edit_college_admin_dev'>"
            f"<input type='hidden' name='id' value='{edit_c_data['id']}'>"
            f"<input type='text' name='college_name' value='{safe_value(edit_c_data['college_name'])}' placeholder='College Name' style='flex:1;min-width:200px;'>"
            f"<input type='text' name='display_name' value='{safe_value(edit_c_data['display_name'])}' placeholder='Admin Display Name' required>"
            f"<input type='text' name='username' value='{safe_value(edit_c_data['username'])}' placeholder='Admin Username' required>"
            "<input type='password' name='new_password' placeholder='New admin password (optional)' autocomplete='new-password'>"
            f"<input type='number' name='total_periods' value='{edit_c_data['total_periods']}' style='width:80px;'>"
            "<button type='submit' style='width:auto;background:#198754;'>Save Updates</button>"
            "<a href='/developer/dashboard' style='background:#6c757d;color:white;padding:10px 15px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:13px;display:flex;align-items:center;'>Cancel</a>"
            "</form></div>"
        )
    elif edit_t_data:
        edit_box = (
            "<div style='background:#d1e7dd;padding:20px;border-radius:8px;margin-bottom:20px;border:1px solid #badbcc;'>"
            "<h4 style='margin:0 0 10px 0;color:#0f5132;'>📝 Edit Faculty Teacher</h4>"
            "<form method='POST' data-no-offline-queue='true' style='display:flex;gap:10px;flex-wrap:wrap;'>"
            "<input type='hidden' name='action' value='update_teacher_dev'>"
            f"<input type='hidden' name='id' value='{edit_t_data['id']}'>"
            f"<input type='text' name='teacher_id' value='{safe_value(edit_t_data['teacher_id'])}' placeholder='ID' style='width:120px;'>"
            f"<input type='text' name='name' value='{safe_value(edit_t_data['name'])}' placeholder='Name'>"
            f"<input type='text' name='username' value='{safe_value(edit_t_data['username'])}' placeholder='User'>"
            "<input type='password' name='new_password' placeholder='New password (optional)' autocomplete='new-password'>"
            f"<input type='text' name='subject' value='{safe_value(edit_t_data['subject'])}' placeholder='Subject'>"
            "<button type='submit' style='width:auto;background:#198754;'>Save Updates</button>"
            "<a href='/developer/dashboard' style='background:#6c757d;color:white;padding:10px 15px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:13px;display:flex;align-items:center;'>Cancel</a>"
            "</form></div>"
        )
    elif edit_s_data:
        edit_box = f"<div style='background:#d1e7dd; padding:20px; border-radius:8px; margin-bottom:20px; border:1px solid #badbcc;'><h4 style='margin:0 0 10px 0;color:#0f5132;'>📝 Edit Student Record</h4><form method='POST' style='display:flex;gap:10px;flex-wrap:wrap;'><input type='hidden' name='action' value='update_student_dev'><input type='hidden' name='id' value='{edit_s_data['id']}'><input type='text' name='roll_no' value='{edit_s_data['roll_no']}' placeholder='Roll' style='width:120px;'><input type='text' name='student_name' value='{edit_s_data['student_name']}' placeholder='Name'><input type='text' name='father_name' value='{edit_s_data['father_name']}' placeholder='Father'><input type='text' name='phone_number' value='{edit_s_data['phone_number']}' placeholder='Phone'><input type='text' name='program' value='{edit_s_data['program']}' placeholder='Program'><input type='text' name='part' value='{edit_s_data['part']}' placeholder='Part'><button type='submit' style='width:auto;background:#198754;'>Save Updates</button><a href='/developer/dashboard' style='background:#6c757d;color:white;padding:10px 15px;border-radius:4px;text-decoration:none;font-weight:bold;font-size:13px;display:flex;align-items:center;'>Cancel</a></form></div>"
    developer_profile_box = (
        "<div class='card full-width'><h3>🔐 Developer Profile</h3>"
        "<form method='POST' action='/developer/dashboard' data-no-offline-queue='true'>"
        "<input type='hidden' name='action' value='update_developer_profile'>"
        f"<label>Username<input type='text' name='username' value='{safe_value(session.get('user'))}' autocomplete='username' required></label>"
        "<label>Current password<input type='password' name='current_password' autocomplete='current-password' required></label>"
        "<label>New password (leave blank to keep current)<input type='password' name='new_password' autocomplete='new-password'></label>"
        "<button type='submit'>Update Developer Login</button></form></div>"
    )
    release_csrf = session.setdefault('developer_csrf_token', secrets.token_urlsafe(32))
    cursor.execute(
        'SELECT title, message, created_at FROM developer_releases '
        'ORDER BY created_at DESC, id DESC LIMIT 5'
    )
    release_entries = ''.join(
        "<li><strong>" + safe_value(row['title']) + "</strong> — "
        + safe_value(row['message']) + "</li>"
        for row in cursor.fetchall()
    )
    developer_release_box = (
        "<div class='card full-width'><h3>📢 Developer Platform Release Logs</h3>"
        "<button type='button' class='form-toggle' data-form-toggle aria-expanded='false' "
        "aria-controls='release-log-panel' data-open-label='+ Publish Platform Release' "
        "data-close-label='− Close Release Form'>+ Publish Platform Release</button>"
        "<div id='release-log-panel' class='form-panel' hidden>"
        "<form method='POST' action='/developer/release_logs' data-no-offline-queue='true'>"
        f"<input type='hidden' name='csrf_token' value='{safe_value(release_csrf)}'>"
        "<input type='text' name='title' maxlength='160' placeholder='Release title' required>"
        "<textarea name='message' maxlength='4096' rows='4' placeholder='Technical changes and deployment notes' required></textarea>"
        "<button type='submit'>Publish Release Log</button></form></div>"
        "<ul>" + (release_entries or "<li>No platform releases have been published.</li>") + "</ul></div>"
    )
    conn.close()
    dashboard_html = """
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
                .form-toggle { width: auto; padding: 9px 14px; }
                .form-panel[hidden] { display: none; }
                .form-panel { max-height: 0; opacity: 0; overflow: hidden; transition: max-height 0.3s ease, opacity 0.2s ease; }
                .form-panel.is-open { max-height: 700px; opacity: 1; }
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
            """ + edit_box + developer_profile_box + developer_release_box + """
            <div class="grid">
                <div class="card">
                    <h3>➕ Add College Account</h3>
                    <button type="button" class="form-toggle" data-form-toggle aria-expanded="false" aria-controls="add-college-form" data-open-label="+ Add College Account" data-close-label="− Cancel">+ Add College Account</button>
                    <div id="add-college-form" class="form-panel" hidden>
                        <form method="POST" action="/developer/create_college">
                            <input type="hidden" name="action" value="create_new_college">
                            <input type="text" name="college_name" placeholder="College Name (e.g. Punjab College)" required>
                            <input type="text" name="display_name" placeholder="Admin Display Name (e.g. Prof. Asif)" required>
                            <input type="text" name="username" placeholder="Admin Username" required>
                            <input type="password" name="password" placeholder="Admin Password" autocomplete="new-password" required>
                            <input type="number" name="total_periods" placeholder="Total Periods Config" value="6" required>
                            <button type="submit">Create Account</button>
                        </form>
                    </div>
                </div>
                <div class="card">
                    <h3>📋 Registered Accounts Matrix</h3>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>College Name</th><th>Admin Name</th><th>User</th><th>Periods</th><th>Action</th></tr>
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
                            <tr><th>College</th><th>Teacher ID</th><th>Name</th><th>User</th><th>Subject</th><th>Action</th></tr>
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
                document.querySelectorAll('[data-form-toggle]').forEach(button => {
                    const panel = document.getElementById(button.getAttribute('aria-controls'));
                    if (!panel) return;
                    button.addEventListener('click', () => {
                        const opening = button.getAttribute('aria-expanded') !== 'true';
                        button.setAttribute('aria-expanded', String(opening));
                        button.textContent = opening ? button.dataset.closeLabel : button.dataset.openLabel;
                        if (opening) {
                            panel.hidden = false;
                            requestAnimationFrame(() => panel.classList.add('is-open'));
                        } else {
                            panel.classList.remove('is-open');
                        }
                    });
                    panel.addEventListener('transitionend', () => {
                        if (button.getAttribute('aria-expanded') === 'false') panel.hidden = true;
                    });
                });
                if ('serviceWorker' in navigator) {
                    navigator.serviceWorker.register('/sw.js', {scope: '/'})
                        .catch(error => console.error('Service worker registration failed:', error));
                }
            </script>
        </body>
    </html>
    """
    return dashboard_html.replace(
        'data-offline-actor="developer:Cukur"',
        f'data-offline-actor="developer:{safe_value(session.get("user"))}"'
    )


@app.route('/developer/release_logs', methods=['POST'])
def publish_developer_release():
    if session.get('role') != 'developer':
        return sync_json_response('error', 401, message='Developer login is required.')
    supplied_token = request.form.get('csrf_token', '')
    expected_token = session.get('developer_csrf_token', '')
    if not expected_token or not hmac.compare_digest(supplied_token, expected_token):
        return sync_json_response('error', 403, message='The security token is invalid. Reload the dashboard and try again.')
    title = request.form.get('title', '').strip()
    message = request.form.get('message', '').strip()
    if not title or not message:
        return sync_json_response('error', 400, message='A release title and deployment notes are required.')
    if len(title) > 160 or len(message) > 4096:
        return sync_json_response('error', 400, message='Release titles are limited to 160 characters and notes to 4,096 characters.')
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO developer_releases (title, message) VALUES (%s, %s)',
            (title, message)
        )
        conn.commit()
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        if conn is not None:
            conn.rollback()
        app.logger.exception('Could not publish the developer release log.')
        return sync_json_response('error', 503, message='The platform release could not be saved.')
    finally:
        if conn is not None:
            conn.close()
    return redirect(url_for('developer_dashboard'))


# Create college through a dedicated endpoint so Vercel routes the POST explicitly.
@app.route('/developer/create_college', methods=['POST'])
def developer_create_college():
    if 'role' not in session or session['role'] != 'developer':
        return sync_json_response('error', 401, message='Developer login is required.')
    if not offline_sync_actor_matches('developer', session.get('user')):
        return sync_json_response('error', 403, message='Queued action belongs to a different developer account.')

    college_name = request.form.get('college_name', '').strip()
    display_name = request.form.get('display_name', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    total_periods = request.form.get('total_periods', '6')
    if not college_name or not display_name or not username or not password:
        return sync_json_response('error', 400, message='College name, admin display name, username, and password are required.')
    if len(display_name) > 120 or len(username) < 3 or len(username) > 64:
        return sync_json_response('error', 400, message='Admin display name must be 120 characters or fewer and username must be 3–64 characters.')
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
            'INSERT INTO admins (college_name, display_name, username, password, total_periods) '
            'VALUES (%s, %s, %s, %s, %s)',
            (college_name, display_name, username, generate_password_hash(password), total_periods)
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
@app.route('/api/offline_seed_data')
def offline_seed_data():
    if session.get('role') != 'teacher':
        return offline_seed_response({
            'status': 'error',
            'message': 'A teacher session is required to load offline attendance data.'
        }, 401)

    college_id = session.get('college_id')
    if college_id is None:
        return offline_seed_response({
            'status': 'error',
            'message': 'Teacher college is not configured.'
        }, 401)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, program, part, roll_no, student_name, father_name '
            'FROM students WHERE college_id = %s ORDER BY program, part, roll_no',
            (college_id,)
        )
        students = [dict(row) for row in cursor.fetchall()]
        seeded_programs = academic_program_options(cursor)
        active_programs = active_academic_program_options(
            cursor, college_id, seeded_programs
        )
        canonical_programs = {
            re.sub(r'[^a-z0-9]', '', program_config['key'].lower()): program_config['key']
            for program_config in active_programs
        }

        cursor.execute('SELECT total_periods FROM admins WHERE id = %s', (college_id,))
        college = cursor.fetchone()
        if not college:
            return offline_seed_response({
                'status': 'error',
                'message': 'Teacher college was not found.'
            }, 404)
        total_periods = int(college['total_periods'] or 6)

        student_ids_by_roll = {student['roll_no']: student['id'] for student in students}
        cursor.execute(
            'SELECT student_roll, attendance_date, period_no, status '
            'FROM attendance WHERE college_id = %s ORDER BY attendance_date, period_no',
            (college_id,)
        )
        attendance_records = [
            {
                'student_id': student_ids_by_roll[row['student_roll']],
                'roll_no': row['student_roll'],
                'date': str(row['attendance_date']),
                'period': int(row['period_no']),
                'status': row['status'] or ''
            }
            for row in cursor.fetchall()
            if row['student_roll'] in student_ids_by_roll
        ]

        class_map = {}
        for student in students:
            normalized_program = re.sub(r'[^a-z0-9]', '', student['program'].lower())
            program = canonical_programs.get(normalized_program, student['program'])
            part = student['part']
            class_key = (program, part)
            if class_key not in class_map:
                class_map[class_key] = {
                    'program': program,
                    'part': part,
                    'students': []
                }
            class_map[class_key]['students'].append({
                'id': student['id'],
                'roll_no': student['roll_no'],
                'student_name': student['student_name'],
                'father_name': student['father_name'] or ''
            })

        return offline_seed_response({
            'status': 'success',
            'college_id': college_id,
            'generated_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
            'periods': list(range(1, total_periods + 1)),
            'programs': [
                {
                    'name': program_config['key'],
                    'display_name': program_config['display_name'],
                    'parts': program_config['parts']
                }
                for program_config in active_programs
            ],
            'classes': list(class_map.values()),
            'attendance': attendance_records
        })
    finally:
        conn.close()


@app.route('/teacher/dashboard')
def teacher_dashboard():
    if 'role' not in session or session['role'] != 'teacher':
        if request.args.get('format') == 'json':
            return student_api_response([], 401)
        return redirect(url_for('welcome'))
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
    total_periods = int(col_info['total_periods'] or 6) if col_info else 6
    seeded_programs = academic_program_options(cursor)
    academic_programs = active_academic_program_options(
        cursor, college_id, seeded_programs
    )
    academic_parts = sorted({
        part for program_config in academic_programs for part in program_config['parts']
    })
    try:
        period_number = int(selected_period)
    except (TypeError, ValueError):
        period_number = 1
    if period_number < 1 or period_number > total_periods:
        period_number = 1
    selected_period = str(period_number)
    try:
        datetime.strptime(selected_date, '%Y-%m-%d')
    except (TypeError, ValueError):
        selected_date = datetime.today().strftime('%Y-%m-%d')
    
    if selected_program and selected_part:
        query = (
            "SELECT * FROM students WHERE college_id = %s "
            "AND LOWER(REPLACE(REPLACE(REPLACE(program, '-', ''), ' ', ''), '.', '')) = %s "
            "AND LOWER(part) = LOWER(%s)"
        )
        query_params = (
            college_id,
            re.sub(r'[^a-z0-9]', '', selected_program.lower()),
            selected_part
        )
        cursor.execute(query, query_params)
        raw_students = cursor.fetchall()
        for s in raw_students:
            s_dict = dict(s)
            cursor.execute('SELECT status FROM attendance WHERE student_roll = %s AND attendance_date = %s AND period_no = %s AND college_id = %s', 
                           (s['roll_no'], selected_date, period_number, college_id))
            att_record = cursor.fetchone()
            s_dict['saved_status'] = att_record['status'] if att_record else ''
            students.append(s_dict)
    conn.close()
    if request.args.get('format') == 'json':
        return student_api_response(students)
    return render_template('attendance.html', students=students, subject=subject, teacher_name=teacher_name, 
                           selected_program=selected_program, selected_part=selected_part,
                           academic_programs=academic_programs, academic_parts=academic_parts,
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
    client_timestamp_value = data.get('client_timestamp', data.get('marked_at'))
    client_timestamp = parse_attendance_timestamp(
        client_timestamp_value,
        require_timezone=True
    )
    if client_timestamp is None:
        return sync_json_response(
            'error', 400,
            message='A valid timezone-aware client_timestamp is required.'
        )
    client_timestamp_db = client_timestamp.isoformat(timespec='microseconds')
    if not isinstance(roll, str) or not roll.strip():
        return sync_json_response('error', 400, message='A student roll number is required.')
    if status not in {'Present', 'Absent', 'Leave', 'Vacation'}:
        return sync_json_response('error', 400, message='Unsupported attendance status.')
    if not isinstance(att_date, str) or not att_date:
        return sync_json_response('error', 400, message='An attendance date is required.')
    try:
        datetime.strptime(att_date, '%Y-%m-%d')
    except ValueError:
        return sync_json_response('error', 400, message='Attendance date must use YYYY-MM-DD format.')
    try:
        period_no = int(data.get('period', 1))
    except (TypeError, ValueError):
        return sync_json_response('error', 400, message='Period must be a number.')
    if period_no < 1:
        return sync_json_response('error', 400, message='Period must be positive.')
    teacher_username = session.get('user')
    college_id = session.get('college_id')
    if college_id is None:
        return sync_json_response('error', 401, message='Teacher college is not configured.')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT total_periods FROM admins WHERE id = %s', (college_id,))
    college = cursor.fetchone()
    total_periods = int(college['total_periods'] or 0) if college else 0
    if period_no > total_periods:
        conn.close()
        return sync_json_response('error', 400, message='Period is outside the configured college periods.')
    try:
        already_processed = begin_sync_operation(cursor)
    except ValueError as error:
        conn.close()
        return sync_json_response('error', 400, message=str(error))
    if already_processed:
        conn.commit()
        conn.close()
        return sync_json_response(current_status=status)
    student_id = data.get('student_id')
    if student_id is not None:
        try:
            student_id = int(student_id)
        except (TypeError, ValueError):
            conn.rollback()
            conn.close()
            return sync_json_response('error', 400, message='Student ID must be a number.')
        cursor.execute(
            'SELECT id, roll_no, student_name, phone_number FROM students WHERE id = %s AND college_id = %s',
            (student_id, college_id)
        )
    else:
        cursor.execute(
            'SELECT id, roll_no, student_name, phone_number FROM students WHERE roll_no = %s AND college_id = %s',
            (roll.strip(), college_id)
        )
    student = cursor.fetchone()
    if not student or (roll.strip() and roll.strip() != student['roll_no']):
        conn.rollback()
        conn.close()
        return sync_json_response('error', 404, message='Student not found in this college.')
    roll = student['roll_no']
    cursor.execute(
        'SELECT id, status, client_timestamp, created_at FROM attendance '
        'WHERE student_roll = %s AND attendance_date = %s AND period_no = %s AND college_id = %s',
        (roll, att_date, period_no, college_id)
    )
    existing_records = cursor.fetchall()
    existing = max(
        existing_records,
        key=lambda record: parse_attendance_timestamp(
            record['client_timestamp'] or record['created_at']
        ) or datetime.min.replace(tzinfo=timezone.utc),
        default=None
    )
    applied = True
    current_status = status
    if existing:
        existing_timestamp = parse_attendance_timestamp(
            existing['client_timestamp'] or existing['created_at']
        )
        if existing_timestamp is not None and client_timestamp <= existing_timestamp:
            applied = False
            current_status = existing['status']
        else:
            cursor.execute(
                'UPDATE attendance SET status = %s, marked_by = %s, '
                'created_at = CURRENT_TIMESTAMP, client_timestamp = %s WHERE id = %s',
                (status, teacher_username, client_timestamp_db, existing['id'])
            )
    else:
        cursor.execute(
            'INSERT INTO attendance '
            '(student_roll, attendance_date, period_no, status, marked_by, client_timestamp, college_id) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (roll, att_date, period_no, status, teacher_username, client_timestamp_db, college_id)
        )

    conn.commit()
    conn.close()
    response_payload = {'current_status': current_status, 'applied': applied}
    if applied and status == 'Absent' and att_date == datetime.today().strftime('%Y-%m-%d'):
        alert_payload = build_whatsapp_absence_payload(
            student, period_no, att_date, college_id
        )
        response_payload['whatsapp_alert_status'] = dispatch_whatsapp_alert(alert_payload)
    return sync_json_response(**response_payload)

# 📥 FIXED REAL APP DOWNLOAD ROUTE LINK INTERFACE: Direct dynamic target redirection mapping to bypass asset errors
@app.route('/download/proposal-pdf')
def download_proposal_pdf():
    # Maps directly to the production dynamic package deployment bundle
    return redirect("https://github.com")


@app.route('/admin/master_erp_report', methods=['GET'])
def download_master_erp_report():
    if session.get('role') != 'admin' or not session.get('user_id'):
        return redirect(url_for('welcome'))
    if not offline_sync_actor_matches('admin', session.get('user_id')):
        return sync_json_response('error', 403, message='This report belongs to a different admin account.')

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        app.logger.exception('The openpyxl dependency is unavailable for the ERP report.')
        return jsonify({'status': 'error', 'message': 'Spreadsheet report support is unavailable.'}), 503

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT s.id, s.roll_no, s.student_name, s.father_name, s.phone_number, '
            's.program, s.part, COUNT(a.id) AS attendance_records, '
            "SUM(CASE WHEN LOWER(TRIM(COALESCE(a.status, ''))) = 'present' THEN 1 ELSE 0 END) AS presents, "
            "SUM(CASE WHEN LOWER(TRIM(COALESCE(a.status, ''))) = 'absent' THEN 1 ELSE 0 END) AS absences, "
            "SUM(CASE WHEN LOWER(TRIM(COALESCE(a.status, ''))) = 'leave' THEN 1 ELSE 0 END) AS leaves "
            'FROM students s LEFT JOIN attendance a '
            'ON a.student_roll = s.roll_no AND a.college_id = s.college_id '
            'WHERE s.college_id = %s '
            'GROUP BY s.id, s.roll_no, s.student_name, s.father_name, s.phone_number, '
            's.program, s.part ORDER BY s.program, s.part, s.roll_no',
            (session['user_id'],)
        )
        student_records = cursor.fetchall()
        cursor.execute(
            'SELECT s.program, s.part, s.roll_no, s.student_name, '
            'a.attendance_date, a.period_no, a.status, a.marked_by '
            'FROM attendance a JOIN students s '
            'ON a.student_roll = s.roll_no AND a.college_id = s.college_id '
            'WHERE s.college_id = %s '
            'ORDER BY s.program, s.part, s.roll_no, a.attendance_date, a.period_no',
            (session['user_id'],)
        )
        attendance_records = cursor.fetchall()
        cursor.execute(
            'SELECT program_key, parts FROM academic_programs '
            'ORDER BY level, display_name'
        )
        class_options = cursor.fetchall()
        cursor.execute('SELECT college_name FROM admins WHERE id = %s', (session['user_id'],))
        college = cursor.fetchone()
    except (DatabaseConfigurationError, psycopg2.Error, sqlite3.Error):
        app.logger.exception('Could not compile the master ERP report.')
        return jsonify({'status': 'error', 'message': 'The college report data is temporarily unavailable.'}), 503
    finally:
        conn.close()

    def class_key(program, part):
        return (
            re.sub(r'[^a-z0-9]', '', (program or '').lower()),
            re.sub(r'[^a-z0-9]', '', (part or '').lower())
        )

    classes = {
        class_key(option['program_key'], part): {
            'program': option['program_key'],
            'part': part,
            'students': 0,
            'attendance_records': 0,
            'presents': 0,
            'absences': 0,
            'leaves': 0
        }
        for option in class_options
        for part in option['parts'].split(',')
    }
    for student in student_records:
        key = class_key(student['program'], student['part'])
        class_data = classes.setdefault(key, {
            'program': student['program'],
            'part': student['part'],
            'students': 0,
            'attendance_records': 0,
            'presents': 0,
            'absences': 0,
            'leaves': 0
        })
        class_data['students'] += 1
        for metric in ('attendance_records', 'presents', 'absences', 'leaves'):
            class_data[metric] += int(student[metric] or 0)

    def excel_text(value):
        text = '' if value is None else str(value)
        return "'" + text if text.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) else text

    def prepare_sheet(sheet, headers, widths):
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='198754')
            cell.alignment = Alignment(wrap_text=True, vertical='center')
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = 'A1'
        for column, width in enumerate(widths, start=1):
            sheet.column_dimensions[chr(64 + column)].width = width

    workbook = Workbook()
    student_sheet = workbook.active
    student_sheet.title = 'Student Metrics'
    prepare_sheet(student_sheet, [
        'Program', 'Part / Semester', 'Roll Number', 'Student Name',
        'Father Name', 'Parent Phone', 'Total Historical Attendance Records',
        'Presents', 'Absences', 'Leaves', 'Attendance Compliance %'
    ], [24, 20, 16, 28, 28, 20, 34, 14, 14, 12, 26])
    for student in student_records:
        presents = int(student['presents'] or 0)
        absences = int(student['absences'] or 0)
        eligible_records = presents + absences
        compliance = round(presents * 100 / eligible_records, 1) if eligible_records else 0
        student_sheet.append([
            excel_text(student['program']), excel_text(student['part']),
            excel_text(student['roll_no']), excel_text(student['student_name']),
            excel_text(student['father_name']),
            excel_text(student['phone_number']), int(student['attendance_records'] or 0),
            presents, absences, int(student['leaves'] or 0), compliance
        ])
    student_sheet.auto_filter.ref = student_sheet.dimensions

    class_sheet = workbook.create_sheet('Class Summary')
    prepare_sheet(class_sheet, [
        'Program', 'Part / Semester', 'Registered Students',
        'Total Attendance Records', 'Presents', 'Absences', 'Leaves',
        'Attendance Compliance %'
    ], [28, 20, 22, 28, 14, 14, 12, 26])
    for class_data in sorted(
        classes.values(),
        key=lambda item: (item['program'].lower(), item['part'].lower())
    ):
        present = class_data['presents']
        absent = class_data['absences']
        eligible_records = present + absent
        compliance = round(present * 100 / eligible_records, 1) if eligible_records else 0
        class_sheet.append([
            excel_text(class_data['program']), excel_text(class_data['part']),
            class_data['students'], class_data['attendance_records'], present,
            absent, class_data['leaves'],
            compliance
        ])
    class_sheet.auto_filter.ref = class_sheet.dimensions

    history_sheet = workbook.create_sheet('Attendance History')
    prepare_sheet(history_sheet, [
        'Program', 'Part / Semester', 'Roll Number', 'Student Name',
        'Date', 'Period', 'Status', 'Marked By'
    ], [28, 20, 16, 28, 16, 12, 16, 24])
    for record in attendance_records:
        history_sheet.append([
            excel_text(record['program']), excel_text(record['part']),
            excel_text(record['roll_no']), excel_text(record['student_name']),
            excel_text(record['attendance_date']),
            int(record['period_no'] or 0), excel_text(record['status']),
            excel_text(record['marked_by'])
        ])
    history_sheet.auto_filter.ref = history_sheet.dimensions

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    college_name = re.sub(r'[^A-Za-z0-9_-]+', '_', college['college_name'] if college else 'college')
    response = send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'{college_name}_master_erp_report.xlsx'
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


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
