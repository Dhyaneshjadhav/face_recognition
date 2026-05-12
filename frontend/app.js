/**
 * FaceROI — Frontend Application Logic
 *
 * Handles video upload, progress tracking, result display,
 * and communication with the backend API.
 */

// When served via nginx proxy: use same origin (nginx proxies /api/ to backend).
// When accessing frontend directly in dev: fall back to port 8000.
const API_BASE = window.location.port === "3000"
    ? ""  // same origin — nginx will proxy /api/* to backend:8000
    : "http://localhost:8000";

// ── DOM references ───────────────────────────────────────────────────
const dropZone       = document.getElementById("drop-zone");
const fileInput      = document.getElementById("file-input");
const progressWrap   = document.getElementById("progress-wrapper");
const progressLabel  = document.getElementById("progress-label");
const progressPct    = document.getElementById("progress-percent");
const progressFill   = document.getElementById("progress-fill");
const resultsSection = document.getElementById("results-section");
const videoPlayer    = document.getElementById("video-player");
const roiTbody       = document.getElementById("roi-tbody");
const historyList    = document.getElementById("history-list");

// Stat elements
const statFaces      = document.getElementById("stat-faces");
const statTotal      = document.getElementById("stat-total");
const statFps        = document.getElementById("stat-fps");
const statResolution = document.getElementById("stat-resolution");


// ── Drop zone interactions ───────────────────────────────────────────
dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (files.length > 0) handleUpload(files[0]);
});

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) handleUpload(fileInput.files[0]);
});


// ── Upload handler ───────────────────────────────────────────────────
async function handleUpload(file) {
    // Validate
    if (!file.type.startsWith("video/")) {
        showToast("Please select a valid video file", "error");
        return;
    }

    // Show progress
    progressWrap.classList.remove("hidden");
    setProgress(0, "Uploading video...");
    resultsSection.classList.add("hidden");

    const formData = new FormData();
    formData.append("file", file);

    try {
        // Simulate progress during upload + processing
        const progressInterval = simulateProgress();

        const response = await fetch(`${API_BASE}/api/upload`, {
            method: "POST",
            body: formData,
        });

        clearInterval(progressInterval);

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: "Upload failed" }));
            throw new Error(err.detail || "Upload failed");
        }

        const data = await response.json();
        setProgress(100, "Processing complete!");

        // Show results after a short delay for UX
        setTimeout(() => {
            displayResults(data);
            loadROIData(data.video_id);
            loadHistory();
        }, 600);

    } catch (err) {
        setProgress(0, `Error: ${err.message}`);
        progressFill.style.background = "var(--red)";
        console.error("Upload error:", err);
    }
}


// ── Display results ──────────────────────────────────────────────────
function displayResults(data) {
    resultsSection.classList.remove("hidden");

    // Stats
    statFaces.textContent      = data.frames_with_face ?? "—";
    statTotal.textContent      = data.total_frames ?? "—";
    statFps.textContent        = data.fps ? data.fps.toFixed(1) : "—";
    statResolution.textContent = data.resolution ?? "—";

    // Video source
    videoPlayer.src = `${API_BASE}/api/video/${data.video_id}`;
    videoPlayer.load();

    // Scroll into view
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}


// ── Load and display ROI data ────────────────────────────────────────
async function loadROIData(videoId) {
    try {
        const res  = await fetch(`${API_BASE}/api/roi/${videoId}`);
        const data = await res.json();

        roiTbody.innerHTML = "";

        for (const roi of data.roi_data) {
            const tr = document.createElement("tr");
            const bb = roi.bounding_box;

            tr.innerHTML = `
                <td>${roi.frame_number}</td>
                <td>${roi.face_detected
                    ? '<span class="badge-yes">YES</span>'
                    : '<span class="badge-no">NO</span>'}</td>
                <td>${bb ? bb.x_min : "—"}</td>
                <td>${bb ? bb.y_min : "—"}</td>
                <td>${bb ? bb.x_max : "—"}</td>
                <td>${bb ? bb.y_max : "—"}</td>
                <td>${roi.confidence != null ? (roi.confidence * 100).toFixed(1) + "%" : "—"}</td>
            `;
            roiTbody.appendChild(tr);
        }
    } catch (err) {
        console.error("Failed to load ROI data:", err);
    }
}


// ── Load upload history ──────────────────────────────────────────────
async function loadHistory() {
    try {
        const res  = await fetch(`${API_BASE}/api/videos`);
        const list = await res.json();

        if (list.length === 0) {
            historyList.innerHTML = '<p class="empty-state">No videos uploaded yet</p>';
            return;
        }

        historyList.innerHTML = list.map(v => `
            <div class="history-item" onclick="viewVideo(${v.video_id})" title="Click to view">
                <div class="history-item-info">
                    <span class="history-filename">${escapeHtml(v.original_filename)}</span>
                    <span class="history-meta">
                        ${v.total_frames ?? "?"} frames &bull; ${v.resolution ?? "?"} &bull;
                        ${v.created_at ? new Date(v.created_at).toLocaleString() : ""}
                    </span>
                </div>
                <span class="status-badge status-${v.status}">${v.status}</span>
            </div>
        `).join("");
    } catch (err) {
        console.error("Failed to load history:", err);
    }
}


// ── View a specific video from history ───────────────────────────────
async function viewVideo(videoId) {
    try {
        const res = await fetch(`${API_BASE}/api/roi/${videoId}`);
        const data = await res.json();

        displayResults({
            video_id: videoId,
            frames_with_face: data.roi_data.filter(r => r.face_detected).length,
            total_frames: data.total_frames,
            fps: data.fps,
            resolution: data.resolution,
        });

        loadROIData(videoId);
    } catch (err) {
        console.error("Failed to load video:", err);
    }
}


// ── Helpers ──────────────────────────────────────────────────────────
function setProgress(pct, label) {
    progressFill.style.width = `${pct}%`;
    progressPct.textContent  = `${Math.round(pct)}%`;
    if (label) progressLabel.textContent = label;
}

function simulateProgress() {
    let pct = 0;
    return setInterval(() => {
        // Asymptotic approach to 90%
        pct += (90 - pct) * 0.03;
        setProgress(pct, pct < 30 ? "Uploading video..." : "Processing frames...");
    }, 200);
}

function escapeHtml(text) {
    const el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
}

function showToast(message, type = "info") {
    // Simple toast (could be upgraded)
    console.log(`[${type}] ${message}`);
}


// ── Initial load ─────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", loadHistory);
