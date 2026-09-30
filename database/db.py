"""
Database Module for Voice Attendance System
Handles SQLite connection, schema creation, seeding, queries, and constraints.
"""

import os
import sqlite3
from datetime import datetime, date

# Absolute path to database file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")


def get_db_connection(db_path=None):
    """Establishes a connection to the SQLite database with Row factory enabled."""
    target_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path=None):
    """Initializes tables and seed sample student records if table is empty."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Create students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            register_number TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            section TEXT NOT NULL,
            year TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Create attendance table with unique constraint on (student_id, date)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Present',
            recognized_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            UNIQUE (student_id, date)
        );
    """)

    # Indices for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_students_reg ON students(register_number);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id);")

    # Seed sample students if table is empty
    cursor.execute("SELECT COUNT(*) AS cnt FROM students;")
    count = cursor.fetchone()["cnt"]
    if count == 0:
        seed_students = [
            ("123", "Karthik Kumar", "CSE", "A", "III", "karthik.cse@college.edu"),
            ("124", "Arun Prakash", "CSE", "A", "III", "arun.cse@college.edu"),
            ("125", "Priya Sharma", "ECE", "B", "II", "priya.ece@college.edu"),
            ("101", "John Doe", "CSE", "A", "I", "john.doe@college.edu"),
            ("102", "Jane Smith", "CSE", "B", "I", "jane.smith@college.edu"),
            ("103", "Rahul Verma", "IT", "A", "IV", "rahul.it@college.edu"),
            ("104", "Ananya Reddy", "ECE", "A", "II", "ananya.ece@college.edu"),
            ("105", "Sanjay Kumar", "MECH", "A", "III", "sanjay.mech@college.edu"),
            ("106", "Sneha Patel", "IT", "B", "III", "sneha.it@college.edu"),
            ("107", "Vikram Singh", "CIVIL", "A", "IV", "vikram.civil@college.edu"),
            ("108", "Deepika Nair", "CSE", "C", "II", "deepika.cse@college.edu"),
            ("109", "Manoj Kumar", "ECE", "A", "III", "manoj.ece@college.edu"),
        ]
        cursor.executemany("""
            INSERT INTO students (register_number, name, department, section, year, email)
            VALUES (?, ?, ?, ?, ?, ?);
        """, seed_students)
        conn.commit()

    conn.commit()
    conn.close()


def get_all_students(db_path=None):
    """Returns all students sorted by register number."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students ORDER BY register_number ASC;")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_student_by_id(student_id, db_path=None):
    """Finds a student by primary key ID."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id = ?;", (student_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_register_number(register_number, db_path=None):
    """Finds a student by exact register number (case-insensitive and stripped)."""
    if not register_number:
        return None
    reg = str(register_number).strip().upper()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE UPPER(TRIM(register_number)) = ?;", (reg,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def find_students_by_name(name_query, db_path=None):
    """Finds students matching name by exact, substring, or token matching."""
    if not name_query or not name_query.strip():
        return []
    clean_query = name_query.strip().lower()
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    # 1. Exact match (case insensitive)
    cursor.execute("SELECT * FROM students WHERE LOWER(name) = ?;", (clean_query,))
    exact = [dict(r) for r in cursor.fetchall()]
    if exact:
        conn.close()
        return exact

    # 2. Substring match
    cursor.execute("SELECT * FROM students WHERE LOWER(name) LIKE ?;", (f"%{clean_query}%",))
    substring_matches = [dict(r) for r in cursor.fetchall()]
    if substring_matches:
        conn.close()
        return substring_matches

    # 3. Token-based matching (e.g. if spoken "Karthik" matches "Karthik Kumar")
    tokens = clean_query.split()
    matched_students = []
    cursor.execute("SELECT * FROM students;")
    all_students = [dict(r) for r in cursor.fetchall()]
    for s in all_students:
        s_tokens = s["name"].lower().split()
        # If any significant token matches
        if any(t in s_tokens for t in tokens if len(t) > 2):
            matched_students.append(s)

    conn.close()
    return matched_students


def add_student(register_number, name, department, section, year, email="", db_path=None):
    """Registers a new student. Raises sqlite3.IntegrityError if register_number exists."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO students (register_number, name, department, section, year, email)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (str(register_number).strip(), name.strip(), department.strip(), section.strip(), str(year).strip(), email.strip() if email else None))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_student(student_id, register_number, name, department, section, year, email="", db_path=None):
    """Updates an existing student's information."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE students
        SET register_number = ?, name = ?, department = ?, section = ?, year = ?, email = ?
        WHERE id = ?;
    """, (str(register_number).strip(), name.strip(), department.strip(), section.strip(), str(year).strip(), email.strip() if email else None, student_id))
    conn.commit()
    conn.close()


def delete_student(student_id, db_path=None):
    """Deletes a student and cascading attendance records."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id = ?;", (student_id,))
    conn.commit()
    conn.close()


def check_attendance_exists(student_id, date_str=None, db_path=None):
    """Checks if an attendance record exists for the given student on a specific date."""
    target_date = date_str or date.today().strftime("%Y-%m-%d")
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, s.register_number, s.name, s.department, s.section
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.student_id = ? AND a.date = ?;
    """, (student_id, target_date))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def mark_attendance(student_id, recognized_text="", status="Present", date_str=None, time_str=None, db_path=None):
    """
    Records attendance for a student.
    Returns: (success: bool, record_or_error: dict/str, is_duplicate: bool)
    """
    now = datetime.now()
    target_date = date_str or now.strftime("%Y-%m-%d")
    target_time = time_str or now.strftime("%I:%M:%S %p")

    # Check duplicate first
    existing = check_attendance_exists(student_id, target_date, db_path)
    if existing:
        return False, existing, True

    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO attendance (student_id, date, time, status, recognized_text)
            VALUES (?, ?, ?, ?, ?);
        """, (student_id, target_date, target_time, status, recognized_text))
        new_id = cursor.lastrowid
        conn.commit()

        # Fetch recorded entry with student details
        cursor.execute("""
            SELECT a.*, s.register_number, s.name, s.department, s.section, s.year
            FROM attendance a
            JOIN students s ON a.student_id = s.id
            WHERE a.id = ?;
        """, (new_id,))
        record = dict(cursor.fetchone())
        conn.close()
        return True, record, False
    except sqlite3.IntegrityError:
        conn.close()
        existing = check_attendance_exists(student_id, target_date, db_path)
        return False, existing, True


def get_attendance_records(date_filter=None, student_query=None, department=None, section=None, db_path=None):
    """Retrieves filtered attendance records with student joins."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    query = """
        SELECT a.id, a.student_id, a.date, a.time, a.status, a.recognized_text, a.created_at,
               s.register_number, s.name, s.department, s.section, s.year, s.email
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE 1=1
    """
    params = []

    if date_filter and date_filter.strip():
        query += " AND a.date = ?"
        params.append(date_filter.strip())

    if student_query and student_query.strip():
        sq = f"%{student_query.strip().lower()}%"
        query += " AND (LOWER(s.register_number) LIKE ? OR LOWER(s.name) LIKE ?)"
        params.extend([sq, sq])

    if department and department.strip() and department.upper() != "ALL":
        query += " AND UPPER(s.department) = ?"
        params.append(department.strip().upper())

    if section and section.strip() and section.upper() != "ALL":
        query += " AND UPPER(s.section) = ?"
        params.append(section.strip().upper())

    query += " ORDER BY a.date DESC, a.time DESC, a.id DESC;"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_dashboard_stats(target_date=None, db_path=None):
    """
    Calculates summary metrics:
    - Total students
    - Present today
    - Absent today
    - Attendance percentage
    - Department-wise breakdown
    - Recent 10 attendance records
    - 7-day attendance trend
    """
    today_str = target_date or date.today().strftime("%Y-%m-%d")
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # 1. Total students
    cursor.execute("SELECT COUNT(*) AS total FROM students;")
    total_students = cursor.fetchone()["total"]

    # 2. Present today
    cursor.execute("SELECT COUNT(DISTINCT student_id) AS present FROM attendance WHERE date = ?;", (today_str,))
    present_today = cursor.fetchone()["present"]

    # 3. Absent today
    absent_today = max(0, total_students - present_today)

    # 4. Attendance percentage
    attendance_pct = round((present_today / total_students * 100), 1) if total_students > 0 else 0.0

    # 5. Recent records today
    cursor.execute("""
        SELECT a.id, a.student_id, a.date, a.time, a.status, a.recognized_text,
               s.register_number, s.name, s.department, s.section
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        WHERE a.date = ?
        ORDER BY a.id DESC
        LIMIT 10;
    """, (today_str,))
    recent_today = [dict(r) for r in cursor.fetchall()]

    # 6. Department-wise breakdown for today
    cursor.execute("""
        SELECT s.department,
               COUNT(DISTINCT s.id) AS total_in_dept,
               COUNT(DISTINCT a.student_id) AS present_in_dept
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id AND a.date = ?
        GROUP BY s.department
        ORDER BY s.department ASC;
    """, (today_str,))
    dept_stats = []
    for r in cursor.fetchall():
        t = r["total_in_dept"]
        p = r["present_in_dept"]
        pct = round((p / t * 100), 1) if t > 0 else 0
        dept_stats.append({
            "department": r["department"],
            "total": t,
            "present": p,
            "absent": max(0, t - p),
            "percentage": pct
        })

    # 7. Past 7 days attendance trend
    cursor.execute("""
        SELECT a.date, COUNT(DISTINCT a.student_id) AS count
        FROM attendance a
        GROUP BY a.date
        ORDER BY a.date DESC
        LIMIT 7;
    """)
    trend_rows = [dict(r) for r in cursor.fetchall()]
    trend_rows.reverse()

    conn.close()

    return {
        "date": today_str,
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_percentage": attendance_pct,
        "recent_today": recent_today,
        "department_stats": dept_stats,
        "weekly_trend": trend_rows
    }


def get_all_departments(db_path=None):
    """Returns list of distinct departments."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT department FROM students ORDER BY department ASC;")
    depts = [r["department"] for r in cursor.fetchall()]
    conn.close()
    return depts


def get_student_attendance_summary(db_path=None):
    """Returns per-student cumulative attendance statistics."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Total distinct attendance dates recorded in system
    cursor.execute("SELECT COUNT(DISTINCT date) AS total_days FROM attendance;")
    total_days = cursor.fetchone()["total_days"] or 1

    cursor.execute("""
        SELECT s.id, s.register_number, s.name, s.department, s.section, s.year,
               COUNT(a.id) AS days_present
        FROM students s
        LEFT JOIN attendance a ON s.id = a.student_id
        GROUP BY s.id
        ORDER BY s.register_number ASC;
    """)
    rows = []
    for r in cursor.fetchall():
        d = dict(r)
        d["total_days"] = total_days
        d["percentage"] = round((d["days_present"] / total_days * 100), 1) if total_days > 0 else 0.0
        rows.append(d)

    conn.close()
    return rows
