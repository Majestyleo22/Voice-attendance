"""
Text Normalizer for Voice Attendance System
Handles phonetic word-to-digit conversion, filler phrase stripping,
register number extraction, and resilient student matching.
"""

import re
from difflib import SequenceMatcher

# Number word mappings
DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "nil": "0",
    "one": "1", "won": "1",
    "two": "2", "to": "2", "too": "2",
    "three": "3", "tree": "3",
    "four": "4", "for": "4", "fore": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8", "ate": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
}

TENS_WORDS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fourty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

MULTIPLIERS = {
    "hundred": 100,
    "thousand": 1000,
}

PREFIX_PHRASES = [
    r"\bmy register number is\b",
    r"\bmy registration number is\b",
    r"\bmy roll number is\b",
    r"\bmy id number is\b",
    r"\bmy student id is\b",
    r"\bmy id is\b",
    r"\bmy reg no is\b",
    r"\bmy roll no is\b",
    r"\bregister number is\b",
    r"\broll number is\b",
    r"\bregister number\b",
    r"\bregistration number\b",
    r"\broll number\b",
    r"\bregister no\b",
    r"\breg no\b",
    r"\broll no\b",
    r"\bstudent id\b",
    r"\bid number\b",
    r"\bstudent number\b",
    r"\bmy name is\b",
    r"\bthis is\b",
    r"\bi am\b",
    r"\bmark my attendance\b",
    r"\bmark attendance\b",
    r"\bplease mark my attendance\b",
    r"\battendance for\b",
    r"\bpresent sir\b",
    r"\bpresent ma'am\b",
    r"\bpresent mam\b",
    r"\bpresent\b",
    r"\bhere sir\b",
    r"\bhere\b",
    r"\bgood morning\b",
    r"\bgood afternoon\b",
    r"\bhello\b",
    r"\bhi\b",
]


def expand_doubles_and_triples(text: str) -> str:
    """
    Expands phrases like 'double two' -> 'two two', 'triple five' -> 'five five five'.
    """
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        w = words[i].lower()
        if w == "double" and i + 1 < len(words):
            next_w = words[i + 1]
            out.extend([next_w, next_w])
            i += 2
        elif w == "triple" and i + 1 < len(words):
            next_w = words[i + 1]
            out.extend([next_w, next_w, next_w])
            i += 3
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def convert_words_to_number_string(text: str) -> str:
    """
    Converts spoken word numbers into digit strings.
    Handles:
    1. Sequential spoken digits: 'one two three' -> '123'
    2. Tens and compound: 'twenty four' -> '24', 'one hundred twenty three' -> '123'
    3. Mixed digits and words: 'reg 1 two 3' -> 'reg 123'
    """
    tokens = text.lower().split()
    result = []
    i = 0

    while i < len(tokens):
        word = re.sub(r"[^\w]", "", tokens[i])

        # Check if word is already all digits
        if word.isdigit():
            result.append(word)
            i += 1
            continue

        # Check single digit words ('one', 'two', 'three' etc.)
        if word in DIGIT_WORDS:
            # Check if this starts a sequence of single digit words
            # e.g., 'one two three' -> '123'
            # Or if it's 'one hundred ...'
            if i + 1 < len(tokens) and re.sub(r"[^\w]", "", tokens[i + 1]) == "hundred":
                # Handle 'one hundred twenty three'
                base = int(DIGIT_WORDS[word]) * 100
                i += 2
                if i < len(tokens):
                    w2 = re.sub(r"[^\w]", "", tokens[i])
                    if w2 in TENS_WORDS:
                        val = TENS_WORDS[w2]
                        i += 1
                        if i < len(tokens):
                            w3 = re.sub(r"[^\w]", "", tokens[i])
                            if w3 in DIGIT_WORDS:
                                val += int(DIGIT_WORDS[w3])
                                i += 1
                        base += val
                    elif w2 in DIGIT_WORDS:
                        base += int(DIGIT_WORDS[w2])
                        i += 1
                result.append(str(base))
                continue
            else:
                # Group contiguous single digit words together: 'one' 'two' 'three' -> '123'
                digit_seq = [DIGIT_WORDS[word]]
                j = i + 1
                while j < len(tokens):
                    nxt = re.sub(r"[^\w]", "", tokens[j])
                    if nxt in DIGIT_WORDS:
                        digit_seq.append(DIGIT_WORDS[nxt])
                        j += 1
                    else:
                        break
                result.append("".join(digit_seq))
                i = j
                continue

        # Check tens words ('twenty', 'thirty', etc.)
        if word in TENS_WORDS:
            val = TENS_WORDS[word]
            if i + 1 < len(tokens):
                nxt = re.sub(r"[^\w]", "", tokens[i + 1])
                if nxt in DIGIT_WORDS:
                    val += int(DIGIT_WORDS[nxt])
                    i += 1
            result.append(str(val))
            i += 1
            continue

        # Otherwise keep word as-is
        result.append(tokens[i])
        i += 1

    return " ".join(result)


def strip_filler_phrases(text: str) -> str:
    """Removes common conversational prefixes and filler phrases."""
    clean = text.lower()
    for pattern in PREFIX_PHRASES:
        clean = re.sub(pattern, " ", clean, flags=re.IGNORECASE)
    # Remove excessive punctuation
    clean = re.sub(r"[.,\/#!$%\^&\*;:{}=\-_`~()?'\"]", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def normalize_speech_text(raw_text: str) -> dict:
    """
    Main normalization pipeline.
    Takes raw ASR transcription and returns structured extraction:
    - raw_text: Original text
    - cleaned_text: Lowercased, stripped of fillers
    - normalized_text: With word numbers converted to digits
    - candidate_register_numbers: List of extracted digit/code strings
    - candidate_names: Clean text candidates for student name matching
    """
    if not raw_text or not raw_text.strip():
        return {
            "raw_text": "",
            "cleaned_text": "",
            "normalized_text": "",
            "candidate_register_numbers": [],
            "candidate_name": "",
        }

    # Step 1: Expand 'double two' -> 'two two'
    step1 = expand_doubles_and_triples(raw_text.strip())

    # Step 2: Strip conversational prefixes & fillers
    step2 = strip_filler_phrases(step1)

    # Step 3: Convert number words to digits
    step3 = convert_words_to_number_string(step2)

    # Step 4: Also try converting number words on the original text first then strip
    alt_step = convert_words_to_number_string(expand_doubles_and_triples(raw_text.strip()))
    alt_step = strip_filler_phrases(alt_step)

    # Step 5: Extract candidate register numbers (pure digits or alphanumeric like 2026CSE01)
    digit_matches = re.findall(r"\b\d+\b", step3) + re.findall(r"\b\d+\b", alt_step)
    # Also check for alphanumeric register patterns (e.g., 20CSE101 or CSE101)
    alphanumeric_matches = re.findall(r"\b[A-Za-z0-9]{2,15}\b", step3)
    
    candidate_numbers = []
    # Deduplicate while preserving order
    for match in digit_matches + alphanumeric_matches:
        cleaned_match = match.strip().upper()
        # If it contains at least one digit or is a reasonable student code
        if any(c.isdigit() for c in cleaned_match) and cleaned_match not in candidate_numbers:
            candidate_numbers.append(cleaned_match)

    # Candidate name: whatever text remains after removing numbers and punctuation
    candidate_name = re.sub(r"\b\d+\b", " ", step3)
    candidate_name = re.sub(r"\s+", " ", candidate_name).strip()

    return {
        "raw_text": raw_text.strip(),
        "cleaned_text": step2,
        "normalized_text": step3,
        "candidate_register_numbers": candidate_numbers,
        "candidate_name": candidate_name.title() if candidate_name else "",
    }


def string_similarity(a: str, b: str) -> float:
    """Returns a similarity ratio between 0.0 and 1.0."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def identify_student_from_text(raw_text: str, all_students: list) -> tuple:
    """
    Matches speech recognition text against the student database.
    Matching priority:
    1. Exact or extracted register number match
    2. Exact student name match
    3. First name / Last name token match
    4. Fuzzy string similarity match (threshold >= 0.70)

    Returns:
    (matched_student: dict or None, match_type: str, match_detail: str)
    """
    if not raw_text or not raw_text.strip():
        return None, "NO_INPUT", "Empty speech input"

    norm = normalize_speech_text(raw_text)

    # Strategy 1: Check candidate register numbers
    for candidate in norm["candidate_register_numbers"]:
        for student in all_students:
            reg = str(student["register_number"]).strip().upper()
            if reg == candidate:
                return student, "REGISTER_NUMBER_EXACT", f"Matched register number: {candidate}"

    # Also check if any student's register number appears as a substring in the normalized text
    norm_upper = norm["normalized_text"].upper()
    for student in all_students:
        reg = str(student["register_number"]).strip().upper()
        if re.search(rf"\b{re.escape(reg)}\b", norm_upper):
            return student, "REGISTER_NUMBER_TEXT", f"Found register number {reg} in speech"

    # Strategy 2: Check candidate student name
    candidate_name = norm["candidate_name"].lower().strip()
    if candidate_name and len(candidate_name) >= 3:
        # 2b. Exact full name match
        for student in all_students:
            s_name = student["name"].lower().strip()
            if s_name == candidate_name:
                return student, "NAME_EXACT", f"Exact name match: {student['name']}"

        # 2c. Rank all students by composite similarity (full string similarity + token overlap)
        best_student = None
        best_score = 0.0
        candidate_tokens = set(candidate_name.split())

        for student in all_students:
            s_name = student["name"].lower().strip()
            s_tokens = set(s_name.split())

            # Base string similarity (e.g. Levenshtein ratio)
            sim = string_similarity(candidate_name, s_name)

            # Check if candidate name is directly a substring or token of student name
            if candidate_name in s_tokens or any(candidate_name == t for t in s_tokens):
                # Strong match for spoken single names like "Priya" or "Karthik"
                sim = max(sim, 0.85)

            # Token overlap bonus
            common_tokens = candidate_tokens.intersection(s_tokens)
            if common_tokens:
                token_ratio = len(common_tokens) / max(len(candidate_tokens), len(s_tokens))
                sim = max(sim, 0.5 + 0.4 * token_ratio)

            if sim > best_score:
                best_score = sim
                best_student = student

        if best_student and best_score >= 0.70:
            match_type = "NAME_TOKEN" if best_score >= 0.85 else "NAME_FUZZY"
            return best_student, match_type, f"Matched {best_student['name']} ({round(best_score*100)}% match)"

    return None, "NOT_FOUND", f"No student matching '{raw_text}' found"

