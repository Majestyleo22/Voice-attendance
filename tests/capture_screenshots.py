"""
Automated Playwright Screenshot Capturing Script
Captures visual documentation screenshots of all pages and interactive states
for the Voice Attendance System.
"""

import os
import time
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "static", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def capture_all_screenshots():
    print(f"Saving screenshots to: {SCREENSHOTS_DIR}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 840})
        page = context.new_page()

        # 1. Home Page - Initial State
        print("Capturing 1: Home Page...")
        page.goto("http://127.0.0.1:5000/")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "01_home_voice_attendance.png"))

        # 2. Home Page - Simulated Voice Verification
        print("Capturing 2: Voice Attendance Marked...")
        # Click simulator accordion
        page.click(".sim-toggle")
        time.sleep(0.5)
        # Type "Sanjay Kumar" (unmarked today) into simulated custom input and click Test Input
        page.fill("#simCustomInput", "Sanjay Kumar")
        page.click("button:has-text('Test Input')")
        # Wait for result box success
        page.wait_for_selector("#resultBox.success", timeout=8000)
        time.sleep(1.5)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "02_voice_attendance_marked.png"))

        # 3. Duplicate Attendance Alert
        print("Capturing 3: Duplicate Attendance Alert...")
        # Click Test Input again with "Sanjay Kumar" to trigger duplicate warning
        page.click("button:has-text('Test Input')")
        page.wait_for_selector("#resultBox.warning", timeout=8000)
        time.sleep(1.5)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "03_duplicate_prevention_alert.png"))

        # 4. Admin Dashboard
        print("Capturing 4: Admin Dashboard...")
        page.goto("http://127.0.0.1:5000/dashboard")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)  # Allow Chart.js animations to finish
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "04_admin_dashboard_analytics.png"))

        # 5. Students Management & Modal
        print("Capturing 5: Student Management...")
        page.goto("http://127.0.0.1:5000/students")
        page.wait_for_load_state("networkidle")
        time.sleep(0.8)
        # Open student modal
        page.click("button:has-text('Register New Student')")
        time.sleep(0.6)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "05_student_registration_modal.png"))

        # 6. Attendance History & Export
        print("Capturing 6: Attendance History & Reports...")
        page.goto("http://127.0.0.1:5000/attendance")
        page.wait_for_load_state("networkidle")
        time.sleep(0.8)
        page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "06_attendance_history_export.png"))

        browser.close()
        print("All 6 screenshots captured successfully!")


if __name__ == "__main__":
    capture_all_screenshots()
