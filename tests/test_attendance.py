"""
Comprehensive Test Suite for Voice Attendance System
Validates all 12 core scenarios:
1. Clear student name
2. Spoken register number
3. "My register number is 123"
4. "One two three"
5. Unknown register number
6. Duplicate attendance
7. No speech
8. Microphone permission denied / missing audio handling
9. Background noise / conversational fillers
10. Multiple students attendance marking
11. Different pronunciation / fuzzy matching
12. Attendance report generation (CSV, Excel, PDF)
"""

import os
import io
import unittest
import tempfile
import sqlite3
from datetime import date

# Import application components
from app import app
from database.db import (
    init_db,
    get_all_students,
    get_student_by_register_number,
    mark_attendance,
    check_attendance_exists,
    get_attendance_records
)
from utils.text_normalizer import (
    normalize_speech_text,
    identify_student_from_text,
    convert_words_to_number_string,
    strip_filler_phrases
)
from utils.export_helpers import (
    generate_csv,
    generate_excel,
    generate_pdf
)
from asr.speech_recognizer import transcribe_audio


class VoiceAttendanceTestCase(unittest.TestCase):

    def setUp(self):
        # Create an isolated temporary SQLite database for testing
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        init_db(self.temp_db_path)
        self.students = get_all_students(self.temp_db_path)

        # Configure Flask test client
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        os.close(self.temp_db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    # -------------------------------------------------------------------------
    # Test 1: Clear student name
    # -------------------------------------------------------------------------
    def test_01_clear_student_name(self):
        student, match_type, detail = identify_student_from_text("Karthik Kumar", self.students)
        self.assertIsNotNone(student, "Should match student by clear full name")
        self.assertEqual(student["register_number"], "123")
        self.assertIn("NAME", match_type)

    # -------------------------------------------------------------------------
    # Test 2: Spoken register number
    # -------------------------------------------------------------------------
    def test_02_spoken_register_number(self):
        student, match_type, detail = identify_student_from_text("124", self.students)
        self.assertIsNotNone(student, "Should match student by direct register number")
        self.assertEqual(student["register_number"], "124")
        self.assertEqual(student["name"], "Arun Prakash")

    # -------------------------------------------------------------------------
    # Test 3: "My register number is 123"
    # -------------------------------------------------------------------------
    def test_03_my_register_number_is_phrase(self):
        phrase = "My register number is 123"
        norm = normalize_speech_text(phrase)
        self.assertIn("123", norm["candidate_register_numbers"])

        student, match_type, detail = identify_student_from_text(phrase, self.students)
        self.assertIsNotNone(student)
        self.assertEqual(student["register_number"], "123")
        self.assertEqual(student["name"], "Karthik Kumar")

    # -------------------------------------------------------------------------
    # Test 4: "One two three"
    # -------------------------------------------------------------------------
    def test_04_word_numbers_one_two_three(self):
        phrase = "one two three"
        norm = normalize_speech_text(phrase)
        self.assertIn("123", norm["candidate_register_numbers"])

        student, match_type, detail = identify_student_from_text(phrase, self.students)
        self.assertIsNotNone(student)
        self.assertEqual(student["register_number"], "123")

    # -------------------------------------------------------------------------
    # Test 5: Unknown register number
    # -------------------------------------------------------------------------
    def test_05_unknown_register_number(self):
        phrase = "register number 99999"
        student, match_type, detail = identify_student_from_text(phrase, self.students)
        self.assertIsNone(student, "Unregistered number should not match any student")
        self.assertEqual(match_type, "NOT_FOUND")

        # Test through Flask API
        res = self.client.post("/api/voice-attendance", json={"text": "register number 99999"})
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "STUDENT_NOT_FOUND")

    # -------------------------------------------------------------------------
    # Test 6: Duplicate attendance prevention
    # -------------------------------------------------------------------------
    def test_06_duplicate_attendance_prevention(self):
        student = get_student_by_register_number("123", self.temp_db_path)
        today = date.today().strftime("%Y-%m-%d")

        # First attendance attempt -> SUCCESS
        success1, record1, is_dup1 = mark_attendance(
            student_id=student["id"],
            recognized_text="123",
            db_path=self.temp_db_path
        )
        self.assertTrue(success1, "First attempt should succeed")
        self.assertFalse(is_dup1)
        self.assertIsNotNone(record1)

        # Second attendance attempt on same day -> DUPLICATE REJECTED
        success2, record2, is_dup2 = mark_attendance(
            student_id=student["id"],
            recognized_text="123",
            db_path=self.temp_db_path
        )
        self.assertFalse(success2, "Second attempt on same day must fail")
        self.assertTrue(is_dup2, "Must flag duplicate attendance")

    # -------------------------------------------------------------------------
    # Test 7: No speech / empty audio
    # -------------------------------------------------------------------------
    def test_07_no_speech_detection(self):
        # Empty text
        res = self.client.post("/api/voice-attendance", json={"text": ""})
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "EMPTY_SPEECH")

        # Audio with silence
        text, status, details = transcribe_audio(b"")
        self.assertEqual(status, "EMPTY_SPEECH")

    # -------------------------------------------------------------------------
    # Test 8: Microphone permission denied / missing audio
    # -------------------------------------------------------------------------
    def test_08_mic_denied_or_missing_audio(self):
        # Missing audio payload
        res = self.client.post("/api/voice-attendance")
        data = res.get_json()
        self.assertEqual(res.status_code, 400)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_type"], "INVALID_REQUEST")

    # -------------------------------------------------------------------------
    # Test 9: Background noise & conversational fillers
    # -------------------------------------------------------------------------
    def test_09_background_noise_and_fillers(self):
        # Spoken with fillers: "uh good morning sir my roll number is 102 please mark attendance"
        phrase = "uh good morning sir my roll number is 102 please mark attendance"
        norm = normalize_speech_text(phrase)
        self.assertIn("102", norm["candidate_register_numbers"])

        student, match_type, detail = identify_student_from_text(phrase, self.students)
        self.assertIsNotNone(student)
        self.assertEqual(student["register_number"], "102")
        self.assertEqual(student["name"], "Jane Smith")

    # -------------------------------------------------------------------------
    # Test 10: Multiple students attendance marking
    # -------------------------------------------------------------------------
    def test_10_multiple_students_marking(self):
        test_regs = ["101", "102", "103", "104"]
        marked_ids = []

        for reg in test_regs:
            student = get_student_by_register_number(reg, self.temp_db_path)
            success, rec, is_dup = mark_attendance(student["id"], recognized_text=reg, db_path=self.temp_db_path)
            self.assertTrue(success)
            marked_ids.append(rec["id"])

        records = get_attendance_records(db_path=self.temp_db_path)
        self.assertEqual(len(records), 4, "Should have exactly 4 attendance records recorded")

    # -------------------------------------------------------------------------
    # Test 11: Different pronunciation / fuzzy matching
    # -------------------------------------------------------------------------
    def test_11_different_pronunciation_fuzzy_matching(self):
        # "Priya" spoken without last name
        student1, mtype1, _ = identify_student_from_text("Priya", self.students)
        self.assertIsNotNone(student1)
        self.assertEqual(student1["name"], "Priya Sharma")

        # "Kartik Kumar" (slight misspelling/phonetic variation of "Karthik Kumar")
        student2, mtype2, _ = identify_student_from_text("Kartik Kumar", self.students)
        self.assertIsNotNone(student2)
        self.assertEqual(student2["name"], "Karthik Kumar")

    # -------------------------------------------------------------------------
    # Test 12: Attendance report generation (CSV, Excel, PDF)
    # -------------------------------------------------------------------------
    def test_12_attendance_report_generation(self):
        # Seed 2 attendance records
        s1 = self.students[0]
        s2 = self.students[1]
        mark_attendance(s1["id"], "123", db_path=self.temp_db_path)
        mark_attendance(s2["id"], "124", db_path=self.temp_db_path)

        records = get_attendance_records(db_path=self.temp_db_path)
        self.assertGreaterEqual(len(records), 2)

        # 1. Test CSV Generation
        csv_buf = generate_csv(records)
        csv_content = csv_buf.getvalue().decode("utf-8-sig")
        self.assertIn("Register Number", csv_content)
        self.assertIn(s1["register_number"], csv_content)

        # 2. Test Excel Generation
        excel_buf = generate_excel(records)
        self.assertGreater(len(excel_buf.getvalue()), 1000)

        # 3. Test PDF Generation
        pdf_buf = generate_pdf(records)
        pdf_bytes = pdf_buf.getvalue()
        self.assertTrue(pdf_bytes.startswith(b"%PDF"), "Must produce a valid PDF file header")
        self.assertGreater(len(pdf_bytes), 1000)


if __name__ == "__main__":
    unittest.main()
