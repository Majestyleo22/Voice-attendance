/**
 * Voice Attendance System - Master Frontend Script
 * Handles Web Audio API recording, PCM WAV encoding, real-time waveform visualization,
 * ASR submission, student management, and dashboard analytics.
 */

// ============================================================================
// 1. Utilities & Audio Feedback
// ============================================================================

function updateLiveClock() {
  const clockEl = document.getElementById("liveClock");
  if (!clockEl) return;
  const now = new Date();
  const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const dateStr = now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  clockEl.innerHTML = `<span class="live-dot"></span> ${dateStr} • ${timeStr}`;
}
setInterval(updateLiveClock, 1000);
updateLiveClock();

// Pleasant Web Audio synthesizer chimes
function playChime(type) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === "success") {
      // Pleasant double chime: E5 -> G#5
      osc.frequency.setValueAtTime(659.25, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(830.61, ctx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc.start();
      osc.stop(ctx.currentTime + 0.4);
    } else if (type === "error" || type === "warning") {
      // Low dual boop
      osc.frequency.setValueAtTime(320, ctx.currentTime);
      osc.frequency.setValueAtTime(260, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } else if (type === "start") {
      // Quick blip
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
      osc.start();
      osc.stop(ctx.currentTime + 0.15);
    }
  } catch (e) {
    // AudioContext blocked or not supported
  }
}

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  let icon = "🔔";
  if (type === "success") icon = "✓";
  if (type === "danger") icon = "✕";
  if (type === "warning") icon = "⚠";
  toast.innerHTML = `<span style="font-size: 1.2rem;">${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.4s ease";
    setTimeout(() => toast.remove(), 400);
  }, 4000);
}


// ============================================================================
// 2. Pure Web Audio API 16kHz PCM WAV Recorder
// ============================================================================

class WavAudioRecorder {
  constructor() {
    this.audioCtx = null;
    this.stream = null;
    this.source = null;
    this.processor = null;
    this.analyser = null;
    this.audioBuffers = [];
    this.isRecording = false;
    this.sampleRate = 16000;
  }

  async start(onAudioData) {
    this.audioBuffers = [];
    this.audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: this.sampleRate });
    
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: this.sampleRate,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
    } catch (err) {
      throw err;
    }

    this.source = this.audioCtx.createMediaStreamSource(this.stream);
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this.source.connect(this.analyser);

    // ScriptProcessor to capture PCM 16-bit 16kHz samples
    this.processor = this.audioCtx.createScriptProcessor(4096, 1, 1);
    this.source.connect(this.processor);
    this.processor.connect(this.audioCtx.destination);

    this.processor.onaudioprocess = (e) => {
      if (!this.isRecording) return;
      const input = e.inputBuffer.getChannelData(0);
      this.audioBuffers.push(new Float32Array(input));
      if (onAudioData) onAudioData(input);
    };

    this.isRecording = true;
  }

  stop() {
    this.isRecording = false;
    if (this.processor) this.processor.disconnect();
    if (this.source) this.source.disconnect();
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
    }

    // Merge Float32 buffers
    let totalLength = 0;
    for (const buf of this.audioBuffers) {
      totalLength += buf.length;
    }
    const merged = new Float32Array(totalLength);
    let offset = 0;
    for (const buf of this.audioBuffers) {
      merged.set(buf, offset);
      offset += buf.length;
    }

    return this.encodeWAV(merged, this.sampleRate);
  }

  encodeWAV(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);

    const writeString = (view, offset, str) => {
      for (let i = 0; i < str.length; i++) {
        view.setUint8(offset + i, str.charCodeAt(i));
      }
    };

    /* RIFF identifier */
    writeString(view, 0, 'RIFF');
    /* file length */
    view.setUint32(4, 36 + samples.length * 2, true);
    /* RIFF type */
    writeString(view, 8, 'WAVE');
    /* format chunk identifier */
    writeString(view, 12, 'fmt ');
    /* format chunk length */
    view.setUint32(16, 16, true);
    /* sample format (raw PCM) */
    view.setUint16(20, 1, true);
    /* channel count: 1 */
    view.setUint16(22, 1, true);
    /* sample rate */
    view.setUint32(24, sampleRate, true);
    /* byte rate (sample rate * block align) */
    view.setUint32(28, sampleRate * 2, true);
    /* block align (channel count * bytes per sample) */
    view.setUint16(32, 2, true);
    /* bits per sample */
    view.setUint16(34, 16, true);
    /* data chunk identifier */
    writeString(view, 36, 'data');
    /* data chunk length */
    view.setUint32(40, samples.length * 2, true);

    // Write PCM 16-bit samples
    let index = 44;
    for (let i = 0; i < samples.length; i++) {
      let s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(index, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
      index += 2;
    }

    return new Blob([view], { type: 'audio/wav' });
  }
}


// ============================================================================
// 3. Voice Attendance Controller (Home Page)
// ============================================================================

let recorder = null;
let recordTimer = null;
let animFrameId = null;

function setupWaveformVisualizer(analyser) {
  const canvas = document.getElementById("waveCanvas");
  if (!canvas || !analyser) return;
  const ctx = canvas.getContext("2d");
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);

  function draw() {
    if (!recorder || !recorder.isRecording) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    animFrameId = requestAnimationFrame(draw);
    analyser.getByteFrequencyData(dataArray);

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const barWidth = (canvas.width / 32) - 2;
    let x = 0;

    for (let i = 0; i < 32; i++) {
      const idx = Math.floor(i * (bufferLength / 32));
      const val = dataArray[idx];
      const barHeight = Math.max(3, (val / 255) * canvas.height);

      const grad = ctx.createLinearGradient(0, canvas.height, 0, 0);
      grad.addColorStop(0, '#3b82f6');
      grad.addColorStop(1, '#60a5fa');

      ctx.fillStyle = grad;
      ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
      x += barWidth + 2;
    }
  }
  draw();
}

async function startVoiceAttendance() {
  const micBtn = document.getElementById("micBtn");
  const ringsWrap = document.querySelector(".mic-rings-wrapper");
  const promptBox = document.getElementById("voicePromptBox");
  const promptText = document.getElementById("promptText");
  const transText = document.getElementById("recognizedSpeechText");
  const resultBox = document.getElementById("resultBox");

  if (!micBtn) return;

  // Toggle stop if already recording
  if (recorder && recorder.isRecording) {
    stopVoiceAttendanceAndProcess();
    return;
  }

  // Reset UI
  if (resultBox) {
    resultBox.className = "result-box";
    resultBox.style.display = "none";
  }
  if (transText) transText.textContent = "Listening...";

  try {
    recorder = new WavAudioRecorder();
    await recorder.start();

    playChime("start");
    micBtn.classList.add("listening");
    micBtn.innerHTML = '<i class="fa-solid fa-stop"></i>';
    if (ringsWrap) ringsWrap.classList.add("is-listening");
    if (promptText) promptText.textContent = "🎤 Listening... Please speak your name or register number";

    setupWaveformVisualizer(recorder.analyser);

    // Auto stop after 4.5 seconds of speaking
    recordTimer = setTimeout(() => {
      if (recorder && recorder.isRecording) {
        stopVoiceAttendanceAndProcess();
      }
    }, 4500);

  } catch (err) {
    console.error("Microphone access error:", err);
    if (promptText) {
      promptText.innerHTML = "❌ <b>Microphone permission is required.</b> Please enable microphone access and try again.";
    }
    showToast("Microphone permission denied or not available.", "danger");
    playChime("error");
  }
}

async function stopVoiceAttendanceAndProcess() {
  const micBtn = document.getElementById("micBtn");
  const ringsWrap = document.querySelector(".mic-rings-wrapper");
  const promptText = document.getElementById("promptText");
  const transText = document.getElementById("recognizedSpeechText");

  if (recordTimer) clearTimeout(recordTimer);
  if (animFrameId) cancelAnimationFrame(animFrameId);

  if (!recorder || !recorder.isRecording) return;

  micBtn.classList.remove("listening");
  micBtn.classList.add("processing");
  micBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
  if (ringsWrap) ringsWrap.classList.remove("is-listening");
  if (promptText) promptText.textContent = "⏳ Processing speech with Faster-Whisper ASR...";

  const wavBlob = recorder.stop();
  recorder = null;

  // Send to backend
  const formData = new FormData();
  formData.append("audio", wavBlob, "voice_input.wav");

  try {
    const res = await fetch("/api/voice-attendance", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    handleAttendanceResponse(data);
  } catch (err) {
    console.error("API Error:", err);
    showToast("Network error communicating with ASR server.", "danger");
    if (promptText) promptText.textContent = "⚠ Failed to connect to attendance server.";
    playChime("error");
  } finally {
    micBtn.classList.remove("processing");
    micBtn.innerHTML = '<i class="fa-solid fa-microphone"></i>';
  }
}

// Simulated or direct text input (for testing & accessibility)
async function sendSimulatedText(text) {
  const promptText = document.getElementById("promptText");
  const transText = document.getElementById("recognizedSpeechText");
  const resultBox = document.getElementById("resultBox");

  if (resultBox) {
    resultBox.className = "result-box";
    resultBox.style.display = "none";
  }
  if (promptText) promptText.textContent = `Testing phrase: "${text}"...`;
  if (transText) transText.textContent = text;

  try {
    const res = await fetch("/api/voice-attendance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text })
    });
    const data = await res.json();
    handleAttendanceResponse(data);
  } catch (err) {
    console.error("Simulation error:", err);
    showToast("Failed to process simulated input.", "danger");
  }
}

function handleAttendanceResponse(data) {
  const promptText = document.getElementById("promptText");
  const transText = document.getElementById("recognizedSpeechText");
  const resultBox = document.getElementById("resultBox");

  // Display recognized text
  if (transText) {
    transText.textContent = data.recognized_text || "—";
  }

  if (!resultBox) return;

  // Make sure resultBox is visible
  resultBox.style.display = "block";

  if (data.success) {
    // 1. Success - Attendance Marked
    playChime("success");
    if (promptText) promptText.innerHTML = `✓ <b>Student Identified!</b> Attendance recorded.`;
    
    resultBox.className = "result-box success";
    resultBox.innerHTML = `
      <div class="result-header">
        <div class="result-badge-icon">✓</div>
        <div>
          <div class="result-title" style="color: #34d399;">Attendance Marked Successfully!</div>
          <div style="font-size: 0.9rem; color: #94a3b8;">${data.message || ''}</div>
        </div>
      </div>
      <div class="student-profile-strip">
        <div>
          <div class="profile-field-label">Student Name</div>
          <div class="profile-field-val">${data.student.name}</div>
        </div>
        <div>
          <div class="profile-field-label">Register Number</div>
          <div class="profile-field-val" style="color: #38bdf8;">${data.student.register_number}</div>
        </div>
        <div>
          <div class="profile-field-label">Department & Sec</div>
          <div class="profile-field-val">${data.student.department} - ${data.student.section} (Yr ${data.student.year})</div>
        </div>
        <div>
          <div class="profile-field-label">Time Recorded</div>
          <div class="profile-field-val">${data.attendance ? data.attendance.time : 'Now'}</div>
        </div>
      </div>
    `;
    showToast(`Attendance marked for ${data.student.name}`, "success");
    loadTodayLiveFeed(); // Refresh feed if visible
  } else if (data.is_duplicate) {
    // 2. Duplicate Attendance Alert
    playChime("warning");
    if (promptText) promptText.innerHTML = `⚠ <b>Duplicate Attempt:</b> Attendance already marked today.`;

    resultBox.className = "result-box warning";
    resultBox.innerHTML = `
      <div class="result-header">
        <div class="result-badge-icon">⚠</div>
        <div>
          <div class="result-title" style="color: #fbbf24;">Attendance Already Recorded</div>
          <div style="font-size: 0.9rem; color: #cbd5e1;">${data.message}</div>
        </div>
      </div>
      <div class="student-profile-strip">
        <div>
          <div class="profile-field-label">Student Name</div>
          <div class="profile-field-val">${data.student.name}</div>
        </div>
        <div>
          <div class="profile-field-label">Register Number</div>
          <div class="profile-field-val" style="color: #fbbf24;">${data.student.register_number}</div>
        </div>
        <div>
          <div class="profile-field-label">Department</div>
          <div class="profile-field-val">${data.student.department} - ${data.student.section}</div>
        </div>
        <div>
          <div class="profile-field-label">Status</div>
          <div class="profile-field-val" style="color: #34d399;">Present Today</div>
        </div>
      </div>
    `;
    showToast(`Duplicate: ${data.student.name} is already marked present.`, "warning");
  } else {
    // 3. Error (Unknown Student, Empty Speech, Poor Recognition)
    playChime("error");
    resultBox.className = "result-box danger";

    let errTitle = "Identification Failed";
    if (data.error_type === "EMPTY_SPEECH") errTitle = "No Speech Detected";
    if (data.error_type === "POOR_RECOGNITION") errTitle = "Speech Unclear";
    if (data.error_type === "STUDENT_NOT_FOUND") errTitle = "Student Not Found";

    if (promptText) promptText.innerHTML = `❌ <b>${errTitle}</b>`;

    resultBox.innerHTML = `
      <div class="result-header">
        <div class="result-badge-icon">✕</div>
        <div>
          <div class="result-title" style="color: #f87171;">${errTitle}</div>
          <div style="font-size: 0.92rem; color: #cbd5e1; margin-top: 0.2rem;">${data.message}</div>
        </div>
      </div>
      ${data.recognized_text ? `
        <div style="background: rgba(15, 23, 42, 0.65); padding: 0.85rem 1.1rem; border-radius: 8px; margin-top: 0.5rem; font-size: 0.88rem; color: #94a3b8;">
          Spoken input transcribed as: <span style="color: #fff; font-weight: 600;">"${data.recognized_text}"</span>
        </div>
      ` : ''}
    `;
    showToast(data.message || "Error identifying student", "danger");
  }
}

// Load today's live recent attendees on the index page
async function loadTodayLiveFeed() {
  const tableBody = document.getElementById("todayLiveTableBody");
  if (!tableBody) return;

  try {
    const res = await fetch("/api/dashboard-stats");
    const data = await res.json();
    
    if (!data.recent_today || data.recent_today.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--text-dim); padding: 2rem;">No attendance recorded yet today. Click the microphone to be the first!</td></tr>`;
      return;
    }

    tableBody.innerHTML = data.recent_today.map((r, i) => `
      <tr>
        <td style="color: var(--text-dim);">${i + 1}</td>
        <td style="font-weight: 700; color: #38bdf8;">${r.register_number}</td>
        <td style="font-weight: 600;">${r.name}</td>
        <td><span class="badge badge-dept">${r.department} - ${r.section}</span></td>
        <td><span style="color: var(--text-muted); font-size: 0.88rem;">${r.time}</span></td>
      </tr>
    `).join("");
  } catch (e) {
    console.warn("Could not load today live feed:", e);
  }
}


// ============================================================================
// 4. Admin Dashboard Controller (dashboard.html)
// ============================================================================

let doughnutChartInstance = null;
let deptBarChartInstance = null;
let trendLineChartInstance = null;

async function loadDashboardStats(dateFilter = "") {
  try {
    const url = dateFilter ? `/api/dashboard-stats?date=${encodeURIComponent(dateFilter)}` : `/api/dashboard-stats`;
    const res = await fetch(url);
    const data = await res.json();

    // Update KPI numbers
    const totalEl = document.getElementById("statTotalStudents");
    const presentEl = document.getElementById("statPresentToday");
    const absentEl = document.getElementById("statAbsentToday");
    const pctEl = document.getElementById("statAttendancePct");

    if (totalEl) totalEl.textContent = data.total_students;
    if (presentEl) presentEl.textContent = data.present_today;
    if (absentEl) absentEl.textContent = data.absent_today;
    if (pctEl) pctEl.textContent = `${data.attendance_percentage}%`;

    // Render Charts
    renderDoughnutChart(data.present_today, data.absent_today);
    renderDeptBarChart(data.department_stats);
    renderTrendLineChart(data.weekly_trend);

    // Render Recent Table
    const tableBody = document.getElementById("dashboardRecentTableBody");
    if (tableBody) {
      if (!data.recent_today || data.recent_today.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--text-dim);">No attendance entries found for ${data.date}.</td></tr>`;
      } else {
        tableBody.innerHTML = data.recent_today.map((r, i) => `
          <tr>
            <td style="color: var(--text-dim);">${i + 1}</td>
            <td style="font-weight: 700; color: #38bdf8;">${r.register_number}</td>
            <td style="font-weight: 600;">${r.name}</td>
            <td><span class="badge badge-dept">${r.department} - ${r.section}</span></td>
            <td>${r.time}</td>
            <td><span class="badge badge-present">✓ Present</span></td>
          </tr>
        `).join("");
      }
    }
  } catch (err) {
    console.error("Dashboard stats error:", err);
  }
}

function renderDoughnutChart(present, absent) {
  const canvas = document.getElementById("attendanceDoughnut");
  if (!canvas) return;

  if (doughnutChartInstance) doughnutChartInstance.destroy();

  doughnutChartInstance = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Present', 'Absent'],
      datasets: [{
        data: [present, absent],
        backgroundColor: ['#10b981', '#ef4444'],
        borderWidth: 2,
        borderColor: '#111827'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: '#94a3b8', font: { family: 'Outfit', size: 12 } }
        }
      },
      cutout: '72%'
    }
  });
}

function renderDeptBarChart(deptStats) {
  const canvas = document.getElementById("deptBarChart");
  if (!canvas || !deptStats) return;

  if (deptBarChartInstance) deptBarChartInstance.destroy();

  const labels = deptStats.map(d => d.department);
  const presentData = deptStats.map(d => d.present);
  const totalData = deptStats.map(d => d.total);

  deptBarChartInstance = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Present',
          data: presentData,
          backgroundColor: '#3b82f6',
          borderRadius: 6
        },
        {
          label: 'Total Enrolled',
          data: totalData,
          backgroundColor: '#334155',
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
        y: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94a3b8', precision: 0 } }
      },
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { family: 'Outfit' } } }
      }
    }
  });
}

function renderTrendLineChart(trendData) {
  const canvas = document.getElementById("trendLineChart");
  if (!canvas || !trendData) return;

  if (trendLineChartInstance) trendLineChartInstance.destroy();

  const labels = trendData.map(t => t.date);
  const counts = trendData.map(t => t.count);

  trendLineChartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Attendees',
        data: counts,
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        tension: 0.35,
        fill: true,
        pointBackgroundColor: '#10b981',
        pointRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#94a3b8' } },
        y: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#94a3b8', precision: 0 } }
      },
      plugins: {
        legend: { display: false }
      }
    }
  });
}


// ============================================================================
// 5. Students Management Controller (students.html)
// ============================================================================

async function loadStudentsList() {
  const tableBody = document.getElementById("studentsTableBody");
  if (!tableBody) return;

  try {
    const res = await fetch("/api/students");
    const students = await res.json();

    const searchInput = document.getElementById("studentSearchInput");
    const query = searchInput ? searchInput.value.toLowerCase().trim() : "";

    const filtered = students.filter(s => {
      if (!query) return true;
      return s.name.toLowerCase().includes(query) ||
             s.register_number.toLowerCase().includes(query) ||
             s.department.toLowerCase().includes(query);
    });

    if (filtered.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2.5rem; color: var(--text-dim);">No students found matching your criteria.</td></tr>`;
      return;
    }

    tableBody.innerHTML = filtered.map((s, idx) => `
      <tr>
        <td style="color: var(--text-dim);">${idx + 1}</td>
        <td style="font-weight: 700; color: #38bdf8;">${s.register_number}</td>
        <td style="font-weight: 600;">${s.name}</td>
        <td><span class="badge badge-dept">${s.department}</span></td>
        <td>${s.section}</td>
        <td>Year ${s.year}</td>
        <td>
          <button class="btn btn-outline btn-sm" onclick='editStudentModal(${JSON.stringify(s)})' title="Edit Student">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
          <button class="btn btn-danger btn-sm" onclick="deleteStudent(${s.id}, '${s.name}')" title="Delete Student" style="margin-left: 0.35rem;">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load students:", err);
  }
}

function openAddStudentModal() {
  document.getElementById("studentModalTitle").textContent = "Register New Student";
  document.getElementById("studentForm").reset();
  document.getElementById("studentIdInput").value = "";
  document.getElementById("studentModal").classList.add("open");
}

function closeStudentModal() {
  document.getElementById("studentModal").classList.remove("open");
}

function editStudentModal(student) {
  document.getElementById("studentModalTitle").textContent = "Edit Student";
  document.getElementById("studentIdInput").value = student.id;
  document.getElementById("studentRegNo").value = student.register_number;
  document.getElementById("studentName").value = student.name;
  document.getElementById("studentDept").value = student.department;
  document.getElementById("studentSection").value = student.section;
  document.getElementById("studentYear").value = student.year;
  document.getElementById("studentEmail").value = student.email || "";
  document.getElementById("studentModal").classList.add("open");
}

async function saveStudent(e) {
  e.preventDefault();
  const studentId = document.getElementById("studentIdInput").value;
  const payload = {
    register_number: document.getElementById("studentRegNo").value.trim(),
    name: document.getElementById("studentName").value.trim(),
    department: document.getElementById("studentDept").value.trim(),
    section: document.getElementById("studentSection").value.trim(),
    year: document.getElementById("studentYear").value.trim(),
    email: document.getElementById("studentEmail").value.trim(),
  };

  const url = studentId ? `/api/students/${studentId}` : `/api/students`;
  const method = studentId ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || "Student saved successfully!", "success");
      closeStudentModal();
      loadStudentsList();
    } else {
      showToast(data.message || "Failed to save student.", "danger");
    }
  } catch (err) {
    showToast("Network error saving student.", "danger");
  }
}

async function deleteStudent(studentId, name) {
  if (!confirm(`Are you sure you want to delete student "${name}"? All associated attendance records will be removed.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/students/${studentId}`, { method: "DELETE" });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || "Student deleted.", "success");
      loadStudentsList();
    } else {
      showToast(data.message || "Failed to delete student.", "danger");
    }
  } catch (err) {
    showToast("Error deleting student.", "danger");
  }
}


// ============================================================================
// 6. Attendance History & Export Controller (attendance.html)
// ============================================================================

async function loadAttendanceHistory() {
  const tableBody = document.getElementById("attendanceTableBody");
  if (!tableBody) return;

  const dateFilter = document.getElementById("filterDate") ? document.getElementById("filterDate").value : "";
  const queryFilter = document.getElementById("filterQuery") ? document.getElementById("filterQuery").value : "";
  const deptFilter = document.getElementById("filterDept") ? document.getElementById("filterDept").value : "";
  const secFilter = document.getElementById("filterSec") ? document.getElementById("filterSec").value : "";

  const params = new URLSearchParams();
  if (dateFilter) params.append("date", dateFilter);
  if (queryFilter) params.append("query", queryFilter);
  if (deptFilter && deptFilter !== "ALL") params.append("department", deptFilter);
  if (secFilter && secFilter !== "ALL") params.append("section", secFilter);

  try {
    const res = await fetch(`/api/attendance?${params.toString()}`);
    const records = await res.json();

    const countEl = document.getElementById("recordsCountBadge");
    if (countEl) countEl.textContent = `${records.length} Records Found`;

    if (records.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 2.5rem; color: var(--text-dim);">No attendance records found matching filters.</td></tr>`;
      return;
    }

    tableBody.innerHTML = records.map((r, i) => `
      <tr>
        <td style="color: var(--text-dim);">${i + 1}</td>
        <td style="font-weight: 700; color: #38bdf8;">${r.register_number}</td>
        <td style="font-weight: 600;">${r.name}</td>
        <td><span class="badge badge-dept">${r.department} - ${r.section}</span></td>
        <td>${r.date}</td>
        <td>${r.time}</td>
        <td><span class="badge badge-present">✓ ${r.status}</span></td>
        <td style="font-size: 0.85rem; color: #94a3b8; font-style: italic;">
          ${r.recognized_text ? `"${r.recognized_text}"` : '—'}
        </td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Attendance query failed:", err);
  }
}

function triggerExport(format) {
  const dateFilter = document.getElementById("filterDate") ? document.getElementById("filterDate").value : "";
  const queryFilter = document.getElementById("filterQuery") ? document.getElementById("filterQuery").value : "";
  const deptFilter = document.getElementById("filterDept") ? document.getElementById("filterDept").value : "";
  const secFilter = document.getElementById("filterSec") ? document.getElementById("filterSec").value : "";

  const params = new URLSearchParams();
  if (dateFilter) params.append("date", dateFilter);
  if (queryFilter) params.append("query", queryFilter);
  if (deptFilter && deptFilter !== "ALL") params.append("department", deptFilter);
  if (secFilter && secFilter !== "ALL") params.append("section", secFilter);

  window.location.href = `/api/export/${format}?${params.toString()}`;
}


// ============================================================================
// 7. Initialization & Event Listeners
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Index page
  const micBtn = document.getElementById("micBtn");
  if (micBtn) {
    micBtn.addEventListener("click", startVoiceAttendance);
    loadTodayLiveFeed();
  }

  // Dashboard page
  const dashboardCard = document.getElementById("dashboardOverviewCard");
  if (dashboardCard) {
    const todayInput = document.getElementById("dashboardDatePicker");
    if (todayInput) {
      todayInput.value = new Date().toISOString().split('T')[0];
      todayInput.addEventListener("change", (e) => loadDashboardStats(e.target.value));
    }
    loadDashboardStats();
  }

  // Students page
  const studentsTable = document.getElementById("studentsTableBody");
  if (studentsTable) {
    loadStudentsList();
    const searchInput = document.getElementById("studentSearchInput");
    if (searchInput) searchInput.addEventListener("input", loadStudentsList);

    const studentForm = document.getElementById("studentForm");
    if (studentForm) studentForm.addEventListener("submit", saveStudent);
  }

  // Attendance history page
  const attendanceTable = document.getElementById("attendanceTableBody");
  if (attendanceTable) {
    loadAttendanceHistory();
    ['filterDate', 'filterQuery', 'filterDept', 'filterSec'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("input", loadAttendanceHistory);
      if (el) el.addEventListener("change", loadAttendanceHistory);
    });
  }
});
