"""
Voice Attendance System - Main Flask Application
Author: Antigravity ASR Project
Objective: ASR-powered Voice Attendance with Faster-Whisper, SQLite, and Web Audio API
"""

import os
import io
import logging
from datetime import datetime, date
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    redirect,
    url_for,
    flash
)

from database.db import (
    init_db,
    get_all_students,
    get_student_by_id,
    get_student_by_register_number,
    add_student,
    update_student,
    delete_student,
    mark_attendance,
    check_attendance_exists,
    get_attendance_records,
    get_dashboard_stats,
    get_all_departments,
    get_student_attendance_summary
)
from asr.speech_recognizer import transcribe_audio
from utils.text_normalizer import (
    normalize_speech_text,
    identify_student_from_text
)
from utils.export_helpers import (
    generate_csv,
    generate_excel,
    generate_pdf
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Application setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "voice-attendance-secret-key-2026")
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max audio upload

# Initialize database on startup
init_db()


# -----------------------------------------------------------------------------
# Frontend Page Routes
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    """Main Voice Attendance Interface."""
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    """Admin Dashboard with Analytics and Attendance Overview."""
    return render_template("dashboard.html")


@app.route("/students")
def students():
    """Student Registration and Management."""
    return render_template("students.html")


@app.route("/attendance")
def attendance():
    """Attendance History, Filtering, and Exporting."""
    return render_template("attendance.html")


# -----------------------------------------------------------------------------
# Voice Attendance Core API
# -----------------------------------------------------------------------------

@app.route("/api/voice-attendance", methods=["POST"])
def voice_attendance():
    """
    Core Voice Attendance Processing Endpoint.
    1. Receives audio stream (or text for fallback testing).
    2. Transcribes with Faster-Whisper ASR.
    3. Normalizes spoken numbers and removes filler phrases.
    4. Searches student database for match.
    5. Checks duplicate entry for current date.
    6. Records attendance with timestamp and recognized utterance.
    7. Returns detailed JSON status.
    """
    raw_text = ""
    asr_status = "SUCCESS"
    asr_details = {}

    # Check if direct text was supplied (for automated testing or accessibility)
    if request.is_json and "text" in request.get_json():
        raw_text = request.get_json().get("text", "").strip()
        asr_details = {"source": "direct_text_input"}
    elif "audio" in request.files:
        audio_file = request.files["audio"]
        if not audio_file.filename:
            return jsonify({
                "success": False,
                "error_type": "NO_AUDIO_FILE",
                "message": "⚠ No audio file uploaded. Please try again."
            }), 400

        audio_bytes = audio_file.read()
        if len(audio_bytes) < 200:
            return jsonify({
                "success": False,
                "error_type": "EMPTY_SPEECH",
                "message": "⚠ No speech detected. Please speak clearly into your microphone."
            }), 400

        # Transcribe with ASR
        raw_text, asr_status, asr_details = transcribe_audio(audio_bytes, audio_file.filename)
    else:
        return jsonify({
            "success": False,
            "error_type": "INVALID_REQUEST",
            "message": "⚠ Invalid request. Audio payload is required."
        }), 400

    # 1. Handle Empty Speech / Silence
    if asr_status == "EMPTY_SPEECH" or not raw_text or not raw_text.strip():
        return jsonify({
            "success": False,
            "error_type": "EMPTY_SPEECH",
            "recognized_text": "",
            "message": "⚠ No speech detected. Please speak clearly."
        }), 200

    # 2. Handle Poor / Unintelligible Recognition
    if asr_status == "POOR_RECOGNITION":
        return jsonify({
            "success": False,
            "error_type": "POOR_RECOGNITION",
            "recognized_text": raw_text,
            "message": "⚠ Speech could not be recognized clearly. Please try again."
        }), 200

    # 3. Student Identification Pipeline
    all_students = get_all_students()
    matched_student, match_type, match_detail = identify_student_from_text(raw_text, all_students)

    # 4. Handle Unknown Student
    if not matched_student:
        return jsonify({
            "success": False,
            "error_type": "STUDENT_NOT_FOUND",
            "recognized_text": raw_text,
            "match_detail": match_detail,
            "message": "❌ Student not found. Please speak your registered name or register number again."
        }), 200

    # 5. Check Duplicate Attendance for Today
    today_str = date.today().strftime("%Y-%m-%d")
    existing_attendance = check_attendance_exists(matched_student["id"], today_str)

    if existing_attendance:
        return jsonify({
            "success": False,
            "error_type": "DUPLICATE_ATTENDANCE",
            "is_duplicate": True,
            "student": matched_student,
            "existing_attendance": existing_attendance,
            "recognized_text": raw_text,
            "message": f"⚠ Attendance already recorded for today for {matched_student['name']} ({matched_student['register_number']})."
        }), 200

    # 6. Record New Attendance Entry
    success, record_or_err, is_dup = mark_attendance(
        student_id=matched_student["id"],
        recognized_text=raw_text,
        status="Present"
    )

    if not success:
        return jsonify({
            "success": False,
            "error_type": "DUPLICATE_ATTENDANCE",
            "is_duplicate": True,
            "student": matched_student,
            "message": "⚠ Attendance already recorded for today."
        }), 200

    logger.info(f"Attendance recorded for {matched_student['name']} (Reg: {matched_student['register_number']}) via '{raw_text}'")

    return jsonify({
        "success": True,
        "is_duplicate": False,
        "student": matched_student,
        "attendance": record_or_err,
        "recognized_text": raw_text,
        "match_type": match_type,
        "match_detail": match_detail,
        "asr_details": asr_details,
        "message": f"✓ Student identified! Attendance marked successfully for {matched_student['name']}."
    }), 200


# -----------------------------------------------------------------------------
# Admin Analytics & Dashboard API
# -----------------------------------------------------------------------------

@app.route("/api/dashboard-stats", methods=["GET"])
def api_dashboard_stats():
    """Returns real-time dashboard KPIs, recent attendance, and department stats."""
    target_date = request.args.get("date", date.today().strftime("%Y-%m-%d"))
    stats = get_dashboard_stats(target_date)
    return jsonify(stats)


@app.route("/api/departments", methods=["GET"])
def api_departments():
    """Returns list of all available departments."""
    depts = get_all_departments()
    return jsonify(depts)


# -----------------------------------------------------------------------------
# Student Management APIs
# -----------------------------------------------------------------------------

@app.route("/api/students", methods=["GET"])
def api_get_students():
    """Lists all registered students."""
    students_list = get_all_students()
    return jsonify(students_list)


@app.route("/api/students", methods=["POST"])
def api_add_student():
    """Registers a new student."""
    data = request.get_json() or request.form
    reg_no = data.get("register_number", "").strip()
    name = data.get("name", "").strip()
    dept = data.get("department", "").strip()
    sec = data.get("section", "").strip()
    year = data.get("year", "").strip()
    email = data.get("email", "").strip()

    if not reg_no or not name or not dept or not sec or not year:
        return jsonify({"success": False, "message": "All fields except email are required."}), 400

    # Check if register number exists
    existing = get_student_by_register_number(reg_no)
    if existing:
        return jsonify({
            "success": False,
            "message": f"Register number '{reg_no}' is already registered to {existing['name']}."
        }), 400

    try:
        new_id = add_student(reg_no, name, dept, sec, year, email)
        new_student = get_student_by_id(new_id)
        return jsonify({
            "success": True,
            "student": new_student,
            "message": f"Student '{name}' registered successfully!"
        }), 201
    except Exception as ex:
        return jsonify({"success": False, "message": str(ex)}), 500


@app.route("/api/students/<int:student_id>", methods=["PUT"])
def api_update_student(student_id):
    """Updates an existing student."""
    data = request.get_json() or request.form
    reg_no = data.get("register_number", "").strip()
    name = data.get("name", "").strip()
    dept = data.get("department", "").strip()
    sec = data.get("section", "").strip()
    year = data.get("year", "").strip()
    email = data.get("email", "").strip()

    student = get_student_by_id(student_id)
    if not student:
        return jsonify({"success": False, "message": "Student not found."}), 404

    # Check unique register number if changed
    if reg_no.upper() != student["register_number"].upper():
        existing = get_student_by_register_number(reg_no)
        if existing:
            return jsonify({"success": False, "message": f"Register number '{reg_no}' already exists."}), 400

    try:
        update_student(student_id, reg_no, name, dept, sec, year, email)
        updated = get_student_by_id(student_id)
        return jsonify({"success": True, "student": updated, "message": "Student updated successfully."})
    except Exception as ex:
        return jsonify({"success": False, "message": str(ex)}), 500


@app.route("/api/students/<int:student_id>", methods=["DELETE"])
def api_delete_student(student_id):
    """Deletes a student and their attendance records."""
    student = get_student_by_id(student_id)
    if not student:
        return jsonify({"success": False, "message": "Student not found."}), 404

    try:
        delete_student(student_id)
        return jsonify({"success": True, "message": f"Student '{student['name']}' deleted successfully."})
    except Exception as ex:
        return jsonify({"success": False, "message": str(ex)}), 500


# -----------------------------------------------------------------------------
# Attendance Records & Reports APIs
# -----------------------------------------------------------------------------

@app.route("/api/attendance", methods=["GET"])
def api_get_attendance():
    """Lists attendance records with dynamic filtering."""
    date_filter = request.args.get("date", "").strip()
    student_query = request.args.get("query", "").strip()
    department = request.args.get("department", "").strip()
    section = request.args.get("section", "").strip()

    records = get_attendance_records(
        date_filter=date_filter,
        student_query=student_query,
        department=department,
        section=section
    )
    return jsonify(records)


@app.route("/api/attendance/summary", methods=["GET"])
def api_get_attendance_summary():
    """Returns cumulative per-student attendance summary with percentages."""
    summary = get_student_attendance_summary()
    return jsonify(summary)


# -----------------------------------------------------------------------------
# Export Endpoints (CSV, Excel, PDF)
# -----------------------------------------------------------------------------

@app.route("/api/export/csv", methods=["GET"])
def export_csv_route():
    """Exports attendance records to CSV."""
    date_filter = request.args.get("date", "").strip()
    student_query = request.args.get("query", "").strip()
    department = request.args.get("department", "").strip()
    section = request.args.get("section", "").strip()

    records = get_attendance_records(date_filter, student_query, department, section)
    buf = generate_csv(records)

    filename = f"attendance_{date_filter or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return send_file(
        buf,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )


@app.route("/api/export/excel", methods=["GET"])
def export_excel_route():
    """Exports attendance records to formatted Excel (.xlsx)."""
    date_filter = request.args.get("date", "").strip()
    student_query = request.args.get("query", "").strip()
    department = request.args.get("department", "").strip()
    section = request.args.get("section", "").strip()

    records = get_attendance_records(date_filter, student_query, department, section)
    filter_summary = f"(Filtered: Date={date_filter or 'All'}, Dept={department or 'All'})"
    buf = generate_excel(records, filter_summary)

    filename = f"attendance_{date_filter or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@app.route("/api/export/pdf", methods=["GET"])
def export_pdf_route():
    """Exports attendance records to formatted PDF."""
    date_filter = request.args.get("date", "").strip()
    student_query = request.args.get("query", "").strip()
    department = request.args.get("department", "").strip()
    section = request.args.get("section", "").strip()

    records = get_attendance_records(date_filter, student_query, department, section)
    filter_summary = f"(Date: {date_filter or 'All'} | Dept: {department or 'All'})"
    buf = generate_pdf(records, filter_summary)

    filename = f"attendance_{date_filter or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


# -----------------------------------------------------------------------------
# Main Application Launcher
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"Starting Voice Attendance System on http://{host}:{port}")
    app.run(host=host, port=port, debug=True)
