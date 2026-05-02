// ClaimIQ v2 Frontend Logic

const API_BASE = (window.CLAIMIQ_API_BASE || `${window.location.origin}/api`).replace(/\/$/, "");
let currentView = "dashboard";
let currentLang = "en";
let charts = {};
let currentClaimContext = null;

// Initialization

let authToken = localStorage.getItem('claimiq_token');
let currentUser = JSON.parse(localStorage.getItem('claimiq_user') || 'null');
const ROLE_HOME = {
    CLINIC_USER: "gpportal",
    TPA_PROCESSOR: "claims",
    TPA_FRAUD_ANALYST: "fraud",
    SYSTEM_ADMIN: "dashboard",
};
const ROLE_ALLOWED_VIEWS = {
    CLINIC_USER: ["gpportal", "submit"],
    TPA_PROCESSOR: ["claims", "denials", "analytics"],
    TPA_FRAUD_ANALYST: ["fraud", "claims", "analytics"],
    SYSTEM_ADMIN: ["dashboard", "claims", "denials", "fraud", "analytics", "gpportal", "submit"],
};

async function apiFetch(endpoint, options = {}) {
    if (!options.headers) options.headers = {};
    if (authToken) {
        options.headers['Authorization'] = `Bearer ${authToken}`;
    }
    const res = await fetch(`${API_BASE}${endpoint}`, options);
    if (res.status === 401 && !endpoint.includes('/auth/login') && !endpoint.includes('/auth/logout')) {
        doLogout();
        throw new Error('Unauthorized');
    }
    return res;
}

async function parseApiBody(res) {
    const contentType = (res.headers.get("content-type") || "").toLowerCase();
    const raw = await res.text();
    if (!raw) return null;
    if (contentType.includes("application/json")) {
        try {
            return JSON.parse(raw);
        } catch (_) {
            return { detail: raw };
        }
    }
    try {
        return JSON.parse(raw);
    } catch (_) {
        return { detail: raw };
    }
}

async function doLogin() {
    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;
    const errorEl = document.getElementById("loginError");
    errorEl.style.display = "none";

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, password: password })
        });

        if (!res.ok) {
            const data = await parseApiBody(res);
            const detail = typeof data.detail === 'object' ? JSON.stringify(data.detail) : data.detail;
            throw new Error(detail || "Login failed");
        }

        const data = await parseApiBody(res);
        authToken = data.access_token || data.token;
        currentUser = data.user;
        if (!authToken || !currentUser || !currentUser.role) {
            throw new Error("Login response is invalid. Please try again.");
        }
        localStorage.setItem("claimiq_token", authToken);
        localStorage.setItem("claimiq_user", JSON.stringify(currentUser));
        
        document.getElementById("btnLogout").style.display = "inline-flex";
        
        const homeView = ROLE_HOME[currentUser.role] || "dashboard";
        window.location.hash = `#/portal/${homeView}`;
    } catch (e) {
        errorEl.textContent = e.message || "Login failed. Please check your network and try again.";
        errorEl.style.display = "block";
    }
}

async function doLogout() {
    if (authToken) {
        try {
            await apiFetch("/auth/logout", { method: "POST" });
        } catch (_) {
            // Continue local logout even if server logout fails.
        }
    }
    authToken = null;
    currentUser = null;
    localStorage.removeItem("claimiq_token");
    localStorage.removeItem("claimiq_user");
    document.getElementById("btnLogout").style.display = "none";
    window.location.hash = "#/portal/login";
}

function normalizeViewFromHash(hash) {
    if (!hash || hash === "#/portal/login") return "login";
    const view = hash.replace("#/portal/", "");
    return view === "clinic" ? "gpportal" : (view === "tpa" ? "claims" : (view === "admin" ? "dashboard" : view));
}

function canAccessView(viewId) {
    if (viewId === "login") return true;
    if (!currentUser || !currentUser.role) return false;
    return (ROLE_ALLOWED_VIEWS[currentUser.role] || []).includes(viewId);
}

function applyRoleNav() {
    const topNav = document.getElementById("topNav");
    const onLogin = normalizeViewFromHash(window.location.hash) === "login";
    topNav.style.display = onLogin ? "none" : "flex";
    if (onLogin || !currentUser) return;

    const allowed = new Set(ROLE_ALLOWED_VIEWS[currentUser.role] || []);
    document.querySelectorAll(".nav-link").forEach((el) => {
        const view = el.dataset.view;
        el.style.display = allowed.has(view) ? "inline-flex" : "none";
    });
    document.getElementById("btnSeedDemo").style.display = currentUser.role === "SYSTEM_ADMIN" ? "inline-flex" : "none";
}

function handleHash() {
    const hash = window.location.hash;
    
    if (!authToken && hash !== "#/portal/login") {
        window.location.hash = "#/portal/login";
        return;
    }
    
    document.getElementById("btnLogout").style.display = authToken ? "inline-flex" : "none";

    let view = normalizeViewFromHash(hash);
    if (view !== "login" && !canAccessView(view)) {
        view = ROLE_HOME[currentUser?.role] || "dashboard";
        window.location.hash = `#/portal/${view}`;
        applyRoleNav();
        return;
    }
    applyRoleNav();
    switchViewUI(view);
}

function switchViewUI(viewId) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    
    const viewEl = document.getElementById(`view${viewId.charAt(0).toUpperCase() + viewId.slice(1)}`);
    if (viewEl) viewEl.classList.add("active");
    
    const navLink = document.querySelector(`.nav-link[data-view="${viewId}"]`);
    if (navLink) navLink.classList.add("active");

    currentView = viewId;

    if (viewId === "dashboard") loadDashboard();
    else if (viewId === "claims") loadClaims();
    else if (viewId === "denials") loadDenials();
    else if (viewId === "fraud") loadFraud();
    else if (viewId === "analytics") loadAnalytics();
    else if (viewId === "gpportal") loadGPPortal();
}


document.addEventListener("DOMContentLoaded", () => {
    // Hide nav immediately before handleHash() runs so the initial
    // applyRoleNav() is the ONLY thing that sets visibility.
    document.getElementById("topNav").style.display = "none";

    window.addEventListener("hashchange", handleHash);
    handleHash();

    // Navigation Setup
    document.querySelectorAll(".nav-link").forEach(link => {
        link.addEventListener("click", (e) => {
            const view = e.currentTarget.dataset.view;
            if (view) switchView(view);
        });
    });

    // Global Search
    const searchInput = document.getElementById("globalSearch");
    if (searchInput) {
        searchInput.addEventListener("keyup", (e) => {
            if (e.key === "Enter") {
                switchView("claims");
                document.getElementById("filterClinic").value = e.target.value;
                loadClaims();
            }
        });
    }

    // Seed Demo Setup
    document.getElementById("btnSeedDemo").addEventListener("click", seedDemo);
    document.getElementById("notifBtn").addEventListener("click", toggleNotif);
});

// View Routing
function switchView(viewId) {
    window.location.hash = `#/portal/${viewId}`;
}

function _oldSwitchView(viewId) {
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    document.querySelectorAll(".nav-link").forEach(l => l.classList.remove("active"));
    
    document.getElementById(`view${viewId.charAt(0).toUpperCase() + viewId.slice(1)}`).classList.add("active");
    
    const navLink = document.querySelector(`.nav-link[data-view="${viewId}"]`);
    if (navLink) navLink.classList.add("active");

    currentView = viewId;

    // Load data based on view
    if (viewId === "dashboard") loadDashboard();
    else if (viewId === "claims") loadClaims();
    else if (viewId === "denials") loadDenials();
    else if (viewId === "fraud") loadFraud();
    else if (viewId === "analytics") loadAnalytics();
    else if (viewId === "gpportal") loadGPPortal();
}

// Formatters
const fmtMYR = (val) => `RM ${Number(val).toFixed(2)}`;
const fmtDate = (str) => {
    if (!str) return "N/A";
    const d = new Date(str);
    return isNaN(d) ? str : d.toLocaleDateString();
};
function mapDrgFromIcd(icd) {
    const table = {"J06.9":"DRG 371","J18.9":"DRG 193","A90":"DRG 867","E11":"DRG 637","I10":"DRG 305"};
    return table[icd] || "Not mapped";
}
function safeArray(v) { return Array.isArray(v) ? v : []; }
function safeObj(v) { return v && typeof v === "object" ? v : {}; }
function isClaimCompleted(status) {
    return ["APPROVED", "DENIED", "APPEAL_APPROVED", "APPEAL_DENIED", "REFERRED", "FRAUD_FLAG"].includes(status);
}

// --- DASHBOARD ---
async function loadDashboard() {
    try {
        const [summary, claims] = await Promise.all([
            apiFetch(`/analytics/summary`).then(r => r.json()),
            apiFetch(`/claims/?limit=10`).then(r => r.json())
        ]);
        const metrics = await apiFetch(`/metrics`).then(r => r.json());

        // KPIs
        const kpis = summary.kpis || {};
        document.getElementById("kpiCleanRate").textContent = `${kpis.clean_claim_rate || 0}%`;
        document.getElementById("kpiDenialRate").textContent = `${kpis.denial_rate || 0}%`;
        document.getElementById("kpiArDays").textContent = `${kpis.avg_ar_days || 0}`;
        document.getElementById("kpiAutoAdj").textContent = `${kpis.auto_adjudication_rate || 0}%`;

        // Stats
        document.getElementById("statTotal").textContent = summary.total_claims;
        document.getElementById("statApproved").textContent = (summary.by_status?.APPROVED || 0) + (summary.by_status?.APPEAL_APPROVED || 0);
        document.getElementById("statDenied").textContent = summary.by_status?.DENIED || 0;
        
        let fraudCount = 0;
        if(summary.fraud_by_risk_level) {
            fraudCount = (summary.fraud_by_risk_level.HIGH || 0) + (summary.fraud_by_risk_level.CRITICAL || 0);
        }
        document.getElementById("statFraud").textContent = fraudCount;
        document.getElementById("statAvg").textContent = (summary.avg_claim_amount_myr || 0).toFixed(2);
        const approvedAmt = summary.total_approved_myr || 0;
        document.getElementById("statApprovedAmt").textContent = approvedAmt < 1000 ? approvedAmt.toFixed(2) : (approvedAmt/1000).toFixed(1) + "k";
        document.getElementById("statTokens").textContent = (metrics.total_tokens || 0).toLocaleString();
        document.getElementById("statAiCostTotal").textContent = Number(metrics.total_cost_myr || 0).toFixed(6);
        document.getElementById("statAiCostPerClaim").textContent = Number(metrics.avg_cost_per_claim_myr || 0).toFixed(8);

        renderRecentClaims(claims.claims);
        renderCharts(summary);
    } catch (e) {
        console.error("Dashboard error:", e);
    }
}

function renderRecentClaims(claims) {
    const wrap = document.getElementById("recentClaimsTable");
    if (!claims || claims.length === 0) {
        wrap.innerHTML = `<p class="empty-state">No claims found.</p>`;
        return;
    }

    let html = `<table><thead><tr>
        <th>ID</th><th>Date</th><th>Patient</th><th>Clinic</th><th>Diagnosis</th><th>Amount</th><th>Status</th>
    </tr></thead><tbody>`;

    claims.forEach(c => {
        html += `<tr class="tr-clickable" onclick="openClaim(${c.id})">
            <td class="td-mono">#${c.id}</td>
            <td>${fmtDate(c.visit_date)}</td>
            <td>${c.patient_name || 'Unknown'}</td>
            <td>${c.clinic_name || 'Unknown'}</td>
            <td>${c.diagnosis || 'Unknown'}</td>
            <td class="td-mono">${fmtMYR(c.total_amount_myr || 0)}</td>
            <td><span class="badge badge-${c.status}">${c.status}</span></td>
        </tr>`;
    });
    html += `</tbody></table>`;
    wrap.innerHTML = html;
}

// --- CHARTS ---
async function renderCharts(summary) {
    const statusCtx = document.getElementById('statusChart');
    if(charts.status) charts.status.destroy();
    
    const statuses = summary.by_status || {};
    charts.status = new Chart(statusCtx, {
        type: 'doughnut',
        data: {
            labels: Object.keys(statuses),
            datasets: [{
                data: Object.values(statuses),
                backgroundColor: ['#10B981', '#EF4444', '#F59E0B', '#3B82F6', '#8B5CF6'],
                borderWidth: 0
            }]
        },
        options: { plugins: { legend: { position: 'right', labels: {color: '#94A3B8'} } }, cutout: '70%' }
    });

    const denials = await apiFetch(`/analytics/denials`).then(r => r.json());
    const denialCtx = document.getElementById('denialChart');
    if(charts.denial) charts.denial.destroy();
    
    if (denials.breakdown && denials.breakdown.length > 0) {
        charts.denial = new Chart(denialCtx, {
            type: 'bar',
            data: {
                labels: denials.breakdown.map(d => d.denial_reason_code || 'Unknown'),
                datasets: [{
                    label: 'Count',
                    data: denials.breakdown.map(d => d.count),
                    backgroundColor: '#EF4444'
                }]
            },
            options: {
                plugins: { legend: { display: false } },
                scales: { 
                    y: { beginAtZero: true, grid: {color: 'rgba(255,255,255,0.05)'}, ticks: {color: '#94A3B8'} },
                    x: { grid: {display: false}, ticks: {color: '#94A3B8'} }
                }
            }
        });
    }
}

// --- WEEKLY REPORT ---
async function loadWeeklyReport() {
    const el = document.getElementById("weeklyReportContent");
    el.innerHTML = `<p class="empty-state">GLM is analysing data and drafting report...</p>`;
    try {
        const report = await apiFetch(`/analytics/weekly-report`).then(r => r.json());
        let html = `<div class="report-content">`;
        html += `<p style="font-size:1.1rem;margin-bottom:12px;">${report.executive_summary || 'Report generated.'}</p>`;
        
        if (report.key_highlights) {
            html += `<h3>Key Highlights</h3><ul>`;
            report.key_highlights.forEach(h => {
                html += `<li><strong>${h.metric}:</strong> ${h.value} (${h.insight})</li>`;
            });
            html += `</ul>`;
        }
        
        if (report.fraud_alerts && report.fraud_alerts.length > 0) {
            html += `<h3>Fraud Alerts</h3><ul>`;
            report.fraud_alerts.forEach(a => html += `<li><span style="color:var(--accent-red)">[!]</span> ${a}</li>`);
            html += `</ul>`;
        }
        
        html += `</div>`;
        el.innerHTML = html;
    } catch (e) {
        el.innerHTML = `<p class="empty-state" style="color:var(--accent-red)">Failed to generate report.</p>`;
    }
}

// --- CLAIMS QUEUE ---
async function loadClaims() {
    const clinic = document.getElementById("filterClinic").value;
    const status = document.getElementById("claimStatusFilter").value;
    let url = `${API_BASE}/claims/?limit=200`;
    if (clinic) url += `&clinic=${encodeURIComponent(clinic)}`;
    if (status) url += `&status=${status}`;

    try {
        const res = await apiFetch(`/claims/?limit=200${clinic ? '&clinic=' + encodeURIComponent(clinic) : ''}${status ? '&status=' + status : ''}`).then(r => r.json());
        const wrap = document.getElementById("claimsTable");
        if (!res.claims || res.claims.length === 0) {
            wrap.innerHTML = `<p class="empty-state">No claims match filters.</p>`;
            return;
        }

        let html = `<table><thead><tr>
            <th>ID</th><th>Submitted</th><th>Clinic</th><th>Patient</th><th>Diagnosis</th><th>Amount</th><th>Status</th>
        </tr></thead><tbody>`;

        res.claims.forEach(c => {
            const usageLine = isClaimCompleted(c.status) && (Number(c.ai_total_tokens || 0) > 0)
                ? `<br><span style="font-size:0.75rem;color:var(--text-secondary)">AI: ${Number(c.ai_total_tokens || 0).toLocaleString()} tok | RM ${(Number(c.ai_total_cost_myr || 0)).toFixed(6)}</span>`
                : "";
            html += `<tr class="tr-clickable" onclick="openClaim(${c.id})">
                <td class="td-mono">#${c.id}</td>
                <td>${fmtDate(c.created_at)}</td>
                <td>${c.clinic_name || 'N/A'}</td>
                <td>${c.patient_name || 'N/A'}<br><span style="font-size:0.75rem;color:var(--text-secondary)">${c.patient_ic || ''}</span></td>
                <td>${c.diagnosis || 'N/A'}<br><span style="font-size:0.75rem;color:var(--text-secondary)">${c.icd10_code || ''}</span></td>
                <td class="td-mono">${fmtMYR(c.total_amount_myr || 0)}${usageLine}</td>
                <td>
                    <span class="badge badge-${c.status || 'UNKNOWN'}">${c.status || 'UNKNOWN'}</span>
                    <div class="lifecycle-bar">
                        <div class="lifecycle-fill lc-${(c.status || 'unknown').toLowerCase()}"></div>
                    </div>
                </td>
            </tr>`;
        });
        html += `</tbody></table>`;
        wrap.innerHTML = html;
    } catch (e) {
        console.error("Claims error:", e);
    }
}

// --- DENIALS VIEW ---
async function loadDenials() {
    try {
        const [denials, deniedClaims, pendingDenials] = await Promise.all([
            apiFetch(`/analytics/denials`).then(r => r.json()),
            apiFetch(`/claims/?status=DENIED&limit=50`).then(r => r.json()),
            apiFetch(`/claims/?status=PENDING_DENIAL&limit=50`).then(r => r.json())
        ]);
        const claims = { claims: [...(deniedClaims.claims || []), ...(pendingDenials.claims || [])] };

        // Codes
        let codesHtml = ``;
        if (denials.breakdown && denials.breakdown.length > 0) {
            denials.breakdown.forEach(d => {
                codesHtml += `<div class="detail-card" style="margin-bottom:8px;">
                    <div class="detail-row" style="border:none;margin:0;padding:0;">
                        <div>
                            <span style="font-family:var(--font-mono);color:var(--accent-red);font-weight:bold;">CARC ${d.denial_reason_code}</span>
                            <div style="font-size:0.85rem;color:var(--text-secondary);">${d.denial_reason_description}</div>
                        </div>
                        <div style="font-size:1.5rem;font-weight:bold;font-family:var(--font-mono);">${d.count}</div>
                    </div>
                </div>`;
            });
        } else {
            codesHtml = `<p class="empty-state">No denials recorded.</p>`;
        }
        document.getElementById("denialCodesList").innerHTML = codesHtml;

        // List
        let listHtml = ``;
        if (claims.claims && claims.claims.length > 0) {
            claims.claims.forEach(c => {
                listHtml += `<div class="detail-card" style="margin-bottom:8px;cursor:pointer;" onclick="openClaim(${c.id})">
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <span style="font-weight:bold;">Claim #${c.id} - ${c.clinic_name}</span>
                        <span class="td-mono">${fmtMYR(c.total_amount_myr)}</span>
                    </div>
                    <div style="font-size:0.85rem;color:var(--text-secondary);">${c.patient_name} | ${c.diagnosis}</div>
                    <div style="margin-top:8px;"><button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();showAppealModal(${c.id})">Appeal with GLM</button></div>
                </div>`;
            });
        } else {
            listHtml = `<p class="empty-state">No denied claims found.</p>`;
        }
        document.getElementById("deniedClaimsList").innerHTML = listHtml;

    } catch (e) {
        console.error("Denials error:", e);
    }
}

// --- FRAUD VIEW ---
async function loadFraud() {
    try {
        const hm = await apiFetch(`/analytics/fraud-heatmap`).then(r => r.json());
        const data = hm.heatmap_data || [];
        
        let counts = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
        data.forEach(d => counts[d.risk_level]++);
        const total = data.length || 1;

        // Bars
        let barsHtml = ``;
        ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].forEach(level => {
            const pct = (counts[level] / total) * 100;
            const color = level === 'LOW' ? 'var(--accent-green)' : (level === 'MEDIUM' ? 'var(--accent-yellow)' : 'var(--accent-red)');
            barsHtml += `<div class="risk-bar-row">
                <div class="risk-bar-label">${level}</div>
                <div class="risk-bar-track"><div class="risk-bar-fill" style="width:${pct}%;background:${color};"></div></div>
                <div class="risk-bar-val">${counts[level]}</div>
            </div>`;
        });
        document.getElementById("fraudRiskBars").innerHTML = barsHtml;

        // Flagged List
        const flagged = data.filter(d => d.risk_level === 'HIGH' || d.risk_level === 'CRITICAL');
        let listHtml = ``;
        if (flagged.length > 0) {
            flagged.forEach(f => {
                listHtml += `<div class="detail-card" style="margin-bottom:8px;cursor:pointer;" onclick="openClaim(${f.claim_id})">
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <span style="font-weight:bold;">${f.clinic_name} - ${f.diagnosis}</span>
                        <span class="badge badge-DENIED">${f.risk_level}</span>
                    </div>
                    <div style="font-size:0.85rem;color:var(--text-secondary);">Risk Score: ${(f.risk_score || 0).toFixed(2)} | Amount: ${fmtMYR(f.total_amount_myr || 0)}</div>
                </div>`;
            });
        } else {
            listHtml = `<p class="empty-state">No high risk claims found.</p>`;
        }
        document.getElementById("flaggedClaims").innerHTML = listHtml;
    } catch (e) {
        console.error("Fraud error:", e);
    }
}

// --- ANALYTICS VIEW ---
async function loadAnalytics() {
    try {
        const [data, mc] = await Promise.all([
            apiFetch(`/analytics/clinics`).then(r => r.json()),
            apiFetch(`/analytics/mc-patterns`).then(r => r.json())
        ]);
        const wrap = document.getElementById("clinicTable");
        if (!data.clinics || data.clinics.length === 0) {
            wrap.innerHTML = `<p class="empty-state">No data.</p>`;
            return;
        }

        let html = `<table><thead><tr>
            <th>Clinic</th><th>Total Claims</th><th>Denial Rate</th><th>Fraud Flags</th><th>Avg Amount</th><th>Avg Approved</th>
        </tr></thead><tbody>`;

        data.clinics.forEach(c => {
            html += `<tr>
                <td style="font-weight:600;">${c.clinic_name}</td>
                <td class="td-mono">${c.total_claims}</td>
                <td class="td-mono" style="color:${c.denial_rate > 10 ? 'var(--accent-red)' : 'var(--text-secondary)'}">${c.denial_rate}%</td>
                <td class="td-mono">${c.fraud_flagged}</td>
                <td class="td-mono">${fmtMYR(c.avg_amount)}</td>
                <td class="td-mono" style="color:var(--accent-green)">${fmtMYR(c.avg_approved || 0)}</td>
            </tr>`;
        });
        html += `</tbody></table>`;
        wrap.innerHTML = html;

        const mcCtx = document.getElementById('mcPatternChart');
        if (charts.mc) charts.mc.destroy();
        const dist = mc.weekday_distribution || {};
        const labels = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
        charts.mc = new Chart(mcCtx, {
            type: 'bar',
            data: { labels, datasets: [{ data: labels.map(k => dist[k] || 0), backgroundColor: '#3B82F6' }] },
            options: { plugins: { legend: { display: false } } }
        });
    } catch (e) {
        console.error("Analytics error:", e);
    }
}

// --- GP PORTAL ---
function setLang(lang) {
    currentLang = lang;
    document.getElementById("langEN").classList.toggle("active", lang === "en");
    document.getElementById("langBM").classList.toggle("active", lang === "bm");
    
    // Update data attributes
    document.querySelectorAll('[data-en]').forEach(el => {
        el.textContent = el.getAttribute(`data-${lang}`);
    });
    
    loadGPPortal(); // Reload data with language
}

async function loadGPPortal() {
    try {
        const claims = await apiFetch(`/claims/?limit=20`).then(r => r.json());
        const data = claims.claims || [];
        
        let total = data.length;
        let approved = data.filter(c => c.status === 'APPROVED' || c.status === 'APPEAL_APPROVED').length;
        let denied = data.filter(c => c.status === 'DENIED').length;
        let pending = data.filter(c => c.status === 'PENDING' || c.status === 'PROCESSING').length;

        // Stats
        document.getElementById("gpSummaryStats").innerHTML = `
            <div class="kpi-grid" style="grid-template-columns: 1fr 1fr; gap: 16px;">
                <div class="kpi-card kpi-blue"><div class="kpi-val">${total}</div><div class="kpi-label">${currentLang === 'en' ? 'Total Submitted' : 'Jumlah Dihantar'}</div></div>
                <div class="kpi-card kpi-green"><div class="kpi-val">${approved}</div><div class="kpi-label">${currentLang === 'en' ? 'Approved' : 'Diluluskan'}</div></div>
                <div class="kpi-card kpi-red"><div class="kpi-val">${denied}</div><div class="kpi-label">${currentLang === 'en' ? 'Denied' : 'Ditolak'}</div></div>
                <div class="kpi-card kpi-yellow"><div class="kpi-val">${pending}</div><div class="kpi-label">${currentLang === 'en' ? 'Pending' : 'Dalam Proses'}</div></div>
            </div>
        `;

        // Table
        let html = `<table><thead><tr>
            <th>ID</th><th>${currentLang==='en'?'Patient':'Pesakit'}</th><th>${currentLang==='en'?'Date':'Tarikh'}</th><th>Amount (RM)</th><th>Status</th><th>Action</th>
        </tr></thead><tbody>`;

        data.forEach(c => {
            const usageLine = isClaimCompleted(c.status) && (Number(c.ai_total_tokens || 0) > 0)
                ? `<br><span style="font-size:0.75rem;color:var(--text-secondary)">${Number(c.ai_total_tokens || 0).toLocaleString()} tok | RM ${(Number(c.ai_total_cost_myr || 0)).toFixed(6)}</span>`
                : "";
            html += `<tr class="tr-clickable" onclick="openClaim(${c.id})">
                <td class="td-mono">#${c.id}</td>
                <td>${c.patient_name || 'N/A'}</td>
                <td>${fmtDate(c.visit_date)}</td>
                <td class="td-mono">${(c.total_amount_myr||0).toFixed(2)}${usageLine}</td>
                <td><span class="badge badge-${c.status}">${c.status}</span></td>
                <td>${c.status === 'DENIED' ? `<button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();showAppealModal(${c.id})">${currentLang==='en'?'Appeal':'Rayuan'}</button>` : ''}</td>
            </tr>`;
        });
        html += `</tbody></table>`;
        document.getElementById("gpClaimsTable").innerHTML = html;
    } catch (e) {
        console.error("GP error:", e);
    }
}

// File Handlers
function handleFileSelect(inputId, displayId) {
    const input = document.getElementById(inputId);
    const displayElement = document.getElementById(displayId);
    if (input.files && input.files[0]) {
        const file = input.files[0];
        displayElement.innerHTML = `<div>Attached: <b>${file.name}</b></div>`;
        
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function(e) {
                displayElement.innerHTML += `<img src="${e.target.result}" style="max-height: 120px; border-radius: 4px; margin-top: 10px; border: 1px solid rgba(255,255,255,0.2);">`;
            }
            reader.readAsDataURL(file);
        }
    }
}

async function uploadSupportingFile(file) {
    const maxUploadBytes = 1.8 * 1024 * 1024; // keep well under serverless body ceilings
    let uploadFile = file;

    if (file.type.startsWith("image/")) {
        uploadFile = await optimizeImageForUpload(file, maxUploadBytes);
    }
    if (uploadFile.size > maxUploadBytes) {
        throw new Error(`File "${file.name}" is too large to upload. Please use a smaller image.`);
    }

    const formData = new FormData();
    formData.append("file", uploadFile, uploadFile.name || file.name);
    const res = await apiFetch("/uploads", {
        method: "POST",
        body: formData
    });
    const data = await parseApiBody(res);
    if (!res.ok) {
        const detail = data && data.detail ? data.detail : "Failed to upload file.";
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return data.upload_id;
}

async function optimizeImageForUpload(file, targetBytes) {
    const originalDataUrl = await new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = e => resolve(e.target.result);
        reader.readAsDataURL(file);
    });
    const img = await new Promise((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = reject;
        el.src = originalDataUrl;
    });

    let maxDim = 1600;
    let quality = 0.82;
    for (let i = 0; i < 7; i++) {
        const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);

        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
        if (blob && blob.size <= targetBytes) {
            return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
        }
        maxDim = Math.max(700, Math.round(maxDim * 0.82));
        quality = Math.max(0.5, quality - 0.06);
    }

    // Best-effort fallback
    const fallbackCanvas = document.createElement("canvas");
    const scale = Math.min(1, 900 / Math.max(img.width, img.height));
    fallbackCanvas.width = Math.max(1, Math.round(img.width * scale));
    fallbackCanvas.height = Math.max(1, Math.round(img.height * scale));
    fallbackCanvas.getContext("2d").drawImage(img, 0, 0, fallbackCanvas.width, fallbackCanvas.height);
    const fallbackBlob = await new Promise((resolve) => fallbackCanvas.toBlob(resolve, "image/jpeg", 0.5));
    return new File([fallbackBlob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
}

// --- CLAIM SUBMISSION PIPELINE ---
async function submitClaim() {
    if (!currentUser || (currentUser.role !== "CLINIC_USER" && currentUser.role !== "SYSTEM_ADMIN")) {
        document.getElementById("processingPanel").style.display = "block";
        document.getElementById("processingResult").innerHTML =
            `<p style="color:var(--accent-red)">Only Clinic User accounts can submit claims. Please switch to a clinic login.</p>`;
        return;
    }

    const notes = document.getElementById("claimTextInput").value;
    const fileBill = document.getElementById("fileBill").files[0];
    const fileEvidence = document.getElementById("fileEvidence").files[0];
    
    if (!notes.trim() && !fileBill && !fileEvidence) return alert("Please provide clinical notes or attach evidence.");

    const btnSubmit = document.getElementById("btnSubmitClaim");
    btnSubmit.disabled = true;
    
    document.getElementById("processingPanel").style.display = "block";
    document.getElementById("processingResult").innerHTML = "";

    // Reset pipeline UI
    document.querySelectorAll(".pipeline-step").forEach(el => {
        el.classList.remove("active", "done");
    });

    const activateStep = (step) => {
        document.querySelectorAll(".pipeline-step").forEach(el => el.classList.remove("active"));
        const el = document.querySelector(`.pipeline-step[data-step="${step}"]`);
        if (el) el.classList.add("active");
    };
    const finishStep = (step) => {
        const el = document.querySelector(`.pipeline-step[data-step="${step}"]`);
        if (el) { el.classList.remove("active"); el.classList.add("done"); }
    };

    try {
        // Read files as compressed base64 data URLs — embed directly in the submit payload.
        // Avoids broken two-step upload→ID-reference pattern (Vercel serverless ephemeral DB).
        // Images are compressed to ~800KB max each to stay under Vercel's 4.5MB payload limit.
        const readFileAsCompressedDataUrl = async (file) => {
            const maxPayloadBytes = 800 * 1024; // 800KB per image
            let processedFile = file;
            if (file.type.startsWith("image/")) {
                processedFile = await optimizeImageForUpload(file, maxPayloadBytes);
            }
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = e => resolve(e.target.result);
                reader.onerror = reject;
                reader.readAsDataURL(processedFile);
            });
        };

        let evidenceBase64 = null;
        if (fileEvidence) {
            btnSubmit.innerHTML = "Compressing & reading evidence...";
            evidenceBase64 = await readFileAsCompressedDataUrl(fileEvidence);
        }

        let invoiceBase64 = null;
        if (fileBill) {
            btnSubmit.innerHTML = "Compressing & reading invoice...";
            invoiceBase64 = await readFileAsCompressedDataUrl(fileBill);
        }

        if (fileBill || fileEvidence) {
            btnSubmit.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Parsing Documents...`;
            await new Promise(r => setTimeout(r, 800));
        }
        btnSubmit.innerHTML = "Initializing Claim...";

        const getField = (label, fallback = "") => {
            const m = notes.match(new RegExp(`(?:^|\\n)\\s*${label}\\s*:\\s*(.+)`, "i"));
            return (m && m[1] ? m[1].trim() : fallback).split("\n")[0].trim();
        };
        const getFirstMatch = (patterns) => {
            for (const p of patterns) {
                const m = notes.match(p);
                if (m && m[1]) return m[1].trim().split("\n")[0].trim();
            }
            return "";
        };
        const patientName = getField("Name");
        const patientIc = getField("IC");
        const clinicName = getField("Clinic");
        const visitDate = getFirstMatch([
            /(?:^|\n)\s*Visit\s*Date\s*:\s*(\d{4}-\d{2}-\d{2})/i,
            /(?:^|\n)\s*Date\s*:\s*(\d{4}-\d{2}-\d{2})/i
        ]) || getField("Date");
        const totalText = getFirstMatch([
            /(?:^|\n)\s*Total\s*(?:RM|MYR)?\s*:\s*([0-9][0-9,]*(?:\.\d+)?)/i,
            /(?:^|\n)\s*Total\s*:\s*RM?\s*([0-9][0-9,]*(?:\.\d+)?)/i
        ]) || getField("Total");
        const amountMatch = totalText.match(/(\d+(\.\d+)?)/);
        const totalAmount = amountMatch ? Number(amountMatch[1]) : null;
        if (!patientName || !patientIc || !clinicName || !visitDate || totalAmount === null) {
            throw new Error("Missing required fields in notes. Include lines: Name:, IC:, Clinic:, Date:(YYYY-MM-DD), Total:(RM).");
        }
        const vd = new Date(`${visitDate}T00:00:00`);
        const now = new Date();
        const ageDays = Math.floor((now - vd) / (1000 * 60 * 60 * 24));
        if (isNaN(vd.getTime())) {
            throw new Error("Visit Date must be in YYYY-MM-DD format.");
        }
        if (ageDays > 365) {
            console.warn(`Visit Date (${visitDate}) is ${ageDays} days old; continuing so backend can adjudicate late-filing rules.`);
        }

        const payload = {
            raw_text: notes,
            bill_attached: !!fileBill,
            evidence_attached: !!fileEvidence,
            evidence_base64: evidenceBase64,
            invoice_base64: invoiceBase64,
            evidence_upload_id: null,
            invoice_upload_id: null,
            patient_name: patientName,
            patient_ic: patientIc,
            clinic_name: clinicName,
            visit_date: visitDate,
            total_amount_myr: totalAmount
        };

        // Step 0: Intake
        const initResponse = await apiFetch(`/claims/submit`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });
        const initRes = await parseApiBody(initResponse);
        if (!initResponse.ok) {
            let detailStr = "Failed to submit claim.";
            if (initRes && Array.isArray(initRes.detail)) {
                detailStr = initRes.detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join('\n');
            } else if (initRes && typeof initRes.detail === 'object') {
                detailStr = JSON.stringify(initRes.detail);
            } else if (initRes && initRes.detail) {
                detailStr = initRes.detail;
            }
            throw new Error(detailStr);
        }
        const claimId = initRes.claim_id;

        // Backend processes claim automatically after submit (see api_server.py claims_processor.process_claim)
        // Poll for final status after a short delay to let processing complete
        const steps = ["scrub", "eligibility", "extract", "validate", "code", "adjudicate", "fraud", "advisory"];
        let finalStatus = initRes.status || "SUBMITTED";

        // Animate pipeline UI while backend processes
        const pollPromise = new Promise(async (resolve) => {
            // Give backend up to 90s to process (GLM calls take 40-60s total)
            for (let attempt = 0; attempt < 60; attempt++) {
                await new Promise(r => setTimeout(r, 1500));
                try {
                    const statusRes = await apiFetch(`/claims/${claimId}`).then(r => r.json());
                    if (statusRes.status && statusRes.status !== 'SUBMITTED' && statusRes.status !== 'INTAKE' && statusRes.status !== 'PROCESSING') {
                        resolve(statusRes.status);
                        return;
                    }
                } catch (_) {}
            }
            resolve(finalStatus);
        });

        const animPromise = (async () => {
            for(let i=0; i<steps.length; i++) {
                activateStep(steps[i]);
                await new Promise(r => setTimeout(r, 700 + Math.random()*300));
                finishStep(steps[i]);
            }
        })();

        // Wait for both animation and real status
        const [, resolvedStatus] = await Promise.all([animPromise, pollPromise]);
        finalStatus = resolvedStatus;
        
        // Fetch full claim for decision details
        let decisionBadge = '';
        try {
            const fullClaim = await apiFetch(`/claims/${claimId}`).then(r => r.json());
            const dec = fullClaim.decision;
            if (dec) {
                const aiDecision = dec._ai_decision || dec.decision || finalStatus;
                const confidence = dec.confidence ? `${(dec.confidence * 100).toFixed(0)}%` : 'N/A';
                const aiUsage = safeObj(fullClaim.ai_usage);
                decisionBadge = `
                    <div style="margin-top:12px;padding:12px;background:rgba(255,255,255,0.05);border-radius:8px;text-align:left;">
                        <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:6px;text-transform:uppercase;">AI Adjudication Result</div>
                        <span class="badge badge-${aiDecision}">${aiDecision}</span>
                        <span style="font-size:0.85rem;color:var(--text-secondary);margin-left:8px;">Confidence: ${confidence}</span>
                        ${dec.reasoning ? `<p style="margin-top:8px;font-size:0.82rem;color:var(--text-secondary);line-height:1.4;">${dec.reasoning.substring(0, 300)}${dec.reasoning.length > 300 ? '...' : ''}</p>` : ''}
                        ${(aiUsage.total_tokens || 0) > 0 ? `<div style="margin-top:8px;font-size:0.82rem;color:var(--text-secondary);">AI Usage: <b style="color:#fff">${Number(aiUsage.total_tokens || 0).toLocaleString()} tokens</b> | Cost: <b style="color:#fff">RM ${(Number(aiUsage.total_cost_myr || 0)).toFixed(6)}</b></div>` : ''}
                    </div>`;
            }
        } catch (_) {}
        
        document.getElementById("processingResult").innerHTML = `
            <div style="margin-top:20px; padding:20px; background:rgba(255,255,255,0.05); border-radius:12px; text-align:center;">
                <h3 style="margin-bottom:8px;">Claim #${claimId} Processed</h3>
                <span class="badge badge-${finalStatus}" style="font-size:1.1rem; padding:8px 16px;">${finalStatus}</span>
                ${decisionBadge}
                <p style="margin-top:16px;"><button class="btn btn-primary" onclick="openClaim(${claimId})">View Full Claim Details</button></p>
            </div>
        `;
    } catch (e) {
        document.getElementById("processingResult").innerHTML = `<p style="color:var(--accent-red)">Error: ${e.message}</p>`;
    } finally {
        document.getElementById("btnSubmitClaim").disabled = false;
        document.getElementById("btnSubmitClaim").innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13,17 18,12 13,7"/><polyline points="6,17 11,12 6,7"/></svg> Upload & Run Full Z.AI Pipeline`;
    }
}


// --- CLAIM DETAIL & MODALS ---
async function openClaim(id) {
    document.getElementById("claimModal").classList.add("active");
    const body = document.getElementById("modalBody");
    body.innerHTML = `<p class="empty-state">Loading claim data...</p>`;
    document.getElementById("chatMessages").innerHTML = `<div class="chat-msg chat-msg-system">Hi! Ask me anything about this claim.</div>`;
    
    try {
        const response = await apiFetch(`/claims/${id}`);
        const claim = await response.json();
        if (!response.ok || !claim || typeof claim !== "object" || !claim.id) {
            const detail = typeof claim?.detail === 'object' ? JSON.stringify(claim.detail) : claim?.detail;
            throw new Error(detail || "Claim not found.");
        }
        currentClaimContext = claim;
        const decisionObj = safeObj(claim.decision);
        const fraudObj = safeObj(claim.fraud);
        const aiUsage = safeObj(claim.ai_usage);
        const advisoryObj = safeObj(claim.advisory);
        const xrefObj = safeObj(claim.cross_ref_result);
        const validationFindings = safeArray(xrefObj.validation_findings);
        const deterministicSummary = safeObj(xrefObj.deterministic_summary);
        
        let html = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0;color:#fff;">Claim #${claim.id}</h2>
                    <div style="margin-top:8px;">
                        <span class="badge badge-${claim.status || 'UNKNOWN'}">${claim.status || 'UNKNOWN'}</span>
                        <span style="color:var(--text-secondary);font-size:0.85rem;margin-left:12px;">Filed: ${fmtDate(claim.filing_date)}</span>
                    </div>
                </div>
                <div style="display:flex;gap:8px;align-items:center;">
                    ${claim.eob ? `<a class="btn btn-ghost btn-sm" href="${API_BASE}/claims/${claim.id}/eob.pdf" target="_blank">EOB PDF</a>` : ''}
                    <a class="btn btn-ghost btn-sm" href="${API_BASE}/claims/${claim.id}/export" target="_blank">Export JSON</a>
                    ${(claim.status === 'DENIED' || claim.status === 'REFERRED' || claim.status === 'PENDING_APPROVAL' || claim.status === 'PENDING_DENIAL') ? `<button class="btn btn-primary" onclick="showAppealModal(${claim.id})">Appeal</button>` : ''}
                </div>
            </div>

            <!-- Lifecycle -->
            <div style="margin-top:24px;">
                <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:4px;text-transform:uppercase;">Lifecycle Progress</div>
                <div class="lifecycle-bar" style="height:8px;">
                    <div class="lifecycle-fill lc-${(claim.status || 'unknown').toLowerCase()}"></div>
                </div>
            </div>

            <div class="claim-detail-grid">
                <!-- Left Col -->
                <div>
                    <div class="detail-card" style="margin-bottom:24px;">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">Patient & Visit</h3>
                        <div class="detail-row"><span class="detail-label">Patient</span><span class="detail-value">${claim.patient_name || 'N/A'}<br><span style="font-size:0.8rem;color:var(--text-secondary)">${claim.patient_ic || ''}</span></span></div>
                        <div class="detail-row"><span class="detail-label">Clinic</span><span class="detail-value">${claim.clinic_name || 'N/A'}</span></div>
                        <div class="detail-row"><span class="detail-label">Diagnosis</span><span class="detail-value">${claim.diagnosis || 'N/A'}<br><span style="font-size:0.8rem;color:var(--text-secondary)">${claim.icd10_code || ''}</span></span></div>
                        <div class="detail-row"><span class="detail-label">DRG Readiness</span><span class="detail-value">${mapDrgFromIcd(claim.icd10_code)}</span></div>
                        <div class="detail-row"><span class="detail-label">Total Amount</span><span class="detail-value td-mono">${fmtMYR(claim.total_amount_myr)}</span></div>
                    </div>
                    ${(aiUsage.total_tokens || 0) > 0 ? `
                    <div class="detail-card" style="margin-bottom:24px;">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">AI Usage</h3>
                        <div class="detail-row"><span class="detail-label">Total Tokens</span><span class="detail-value td-mono">${Number(aiUsage.total_tokens || 0).toLocaleString()}</span></div>
                        <div class="detail-row"><span class="detail-label">Prompt Tokens</span><span class="detail-value td-mono">${Number(aiUsage.prompt_tokens || 0).toLocaleString()}</span></div>
                        <div class="detail-row"><span class="detail-label">Completion Tokens</span><span class="detail-value td-mono">${Number(aiUsage.completion_tokens || 0).toLocaleString()}</span></div>
                        <div class="detail-row"><span class="detail-label">AI Cost</span><span class="detail-value td-mono">${fmtMYR(Number(aiUsage.total_cost_myr || 0))}</span></div>
                    </div>` : ''}

                    ${claim.eob ? `
                    <div class="eob-card">
                        <div class="eob-header">
                            <h3 style="margin:0;font-size:0.9rem;text-transform:uppercase;color:var(--accent-blue);">Explanation of Benefits (EOB)</h3>
                            <span class="badge badge-INTAKE">Generated</span>
                        </div>
                        <div class="eob-amount-row"><span>Billed Amount</span><span>${fmtMYR(claim.eob.billed_amount_myr)}</span></div>
                        <div class="eob-amount-row"><span>Covered by Plan</span><span>${fmtMYR(claim.eob.covered_amount_myr)}</span></div>
                        <div class="eob-amount-row total"><span>Patient Responsibility (Copay/Limits)</span><span>${fmtMYR(claim.eob.patient_responsibility_myr)}</span></div>
                        ${claim.eob.denial_code ? `<div class="eob-denial"><strong>CARC ${claim.eob.denial_code}:</strong> ${claim.eob.denial_description}</div>` : ''}
                    </div>` : ''}

                    <div class="detail-card" style="margin-top:24px;">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">Audit Timeline</h3>
                        <div class="audit-timeline">
                            ${safeArray(claim.audit_trail).map(a => `
                                <div class="audit-item">
                                    <div class="audit-time">${new Date(a.created_at).toLocaleString()}</div>
                                    <div class="audit-action">${a.action.replace(/_/g, ' ')}</div>
                                    ${a.to_status ? `<div style="font-size:0.8rem;color:var(--text-secondary)">Status -> ${a.to_status}</div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>

                <!-- Right Col -->
                <div>
                    ${Object.keys(deterministicSummary).length ? `
                    <div class="detail-card" style="margin-bottom:24px;">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">Evidence Consistency</h3>
                        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:10px;">
                            <span class="badge badge-${deterministicSummary.verdict === 'FAIL' ? 'DENIED' : (deterministicSummary.verdict === 'WARN' ? 'PENDING' : 'APPROVED')}">${deterministicSummary.verdict || 'N/A'}</span>
                            <span style="font-size:0.85rem;color:var(--text-secondary);">Critical: ${deterministicSummary.critical_count || 0}</span>
                            <span style="font-size:0.85rem;color:var(--text-secondary);">Warnings: ${deterministicSummary.warning_count || 0}</span>
                        </div>
                        ${validationFindings.length ? `
                        <div>
                            ${validationFindings.filter(f => f.severity === 'CRITICAL' || f.severity === 'WARN').map(f => `
                                <div style="background:rgba(255,255,255,0.03);border:1px solid var(--border-color);padding:10px;border-radius:8px;margin-bottom:8px;">
                                    <div style="font-size:0.8rem;color:var(--text-secondary);">${f.type || 'CHECK'} • ${f.source_doc || 'DOC'} • ${f.field || 'field'}</div>
                                    <div style="font-size:0.85rem;margin-top:4px;">${f.note || 'No details.'}</div>
                                    <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:4px;">Claim: ${f.claim_value ?? 'N/A'} | Evidence: ${f.evidence_value ?? 'N/A'}</div>
                                </div>
                            `).join('')}
                        </div>` : `<div style="font-size:0.85rem;color:var(--text-secondary);">No cross-document inconsistencies detected.</div>`}
                    </div>` : ''}

                    ${Object.keys(decisionObj).length ? `
                    <div class="detail-card" style="margin-bottom:24px;">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">Adjudication Decision</h3>
                        <div style="margin-bottom:16px;">
                            <span class="badge badge-${decisionObj.decision || 'UNKNOWN'}">${decisionObj.decision || 'UNKNOWN'}</span>
                            ${decisionObj._ai_decision && decisionObj._ai_decision !== decisionObj.decision ? `<span class="badge badge-${decisionObj._ai_decision}" style="margin-left:8px;opacity:0.7;">AI: ${decisionObj._ai_decision}</span>` : ''}
                            <span style="float:right;font-family:var(--font-mono);font-size:0.85rem;color:var(--text-secondary);">Conf: ${((decisionObj._ai_confidence || decisionObj.confidence || 0)*100).toFixed(0)}%</span>
                        </div>
                        <p style="font-size:0.9rem;line-height:1.5;background:rgba(0,0,0,0.2);padding:12px;border-radius:var(--radius-sm);">${decisionObj.reasoning || decisionObj.explanation || decisionObj.processing_notes || (decisionObj.full_result ? JSON.stringify(decisionObj.full_result) : 'No reasoning provided by the AI model.')}</p>
                        ${decisionObj.denial_prediction ? `<div style="margin-top:10px;font-size:0.85rem;color:var(--text-secondary);">Denial Risk: <b>${Math.round((decisionObj.denial_prediction.denial_probability || 0)*100)}%</b> (${decisionObj.denial_prediction.risk_level || 'UNKNOWN'})</div>` : ''}
                        ${decisionObj.reasoning_citations ? `<div style="margin-top:10px;">${safeArray(decisionObj.reasoning_citations).map(c=>`<div class="detail-card" style="margin-bottom:6px;"><div style="font-size:0.8rem;color:var(--text-secondary);">${c.policy_reference || 'Policy'}</div><div style="font-size:0.85rem;">${c.clinical_basis || ''}</div></div>`).join('')}</div>` : ''}
                        ${(decisionObj.disposition_class || safeArray(decisionObj.rule_hits).length) ? `
                        <div style="margin-top:12px;background:rgba(255,255,255,0.03);border:1px solid var(--border-color);padding:10px;border-radius:8px;">
                            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:6px;text-transform:uppercase;">Decision Basis</div>
                            ${decisionObj.disposition_class ? `<div style="font-size:0.85rem;">Outcome Class: <strong>${decisionObj.disposition_class}</strong></div>` : ''}
                            ${decisionObj.policy_version ? `<div style="font-size:0.8rem;color:var(--text-secondary);">Policy Version: ${decisionObj.policy_version}</div>` : ''}
                            ${(decisionObj.appealable !== undefined) ? `<div style="font-size:0.8rem;color:var(--text-secondary);">Appealable: ${decisionObj.appealable ? 'Yes' : 'No'}</div>` : ''}
                            ${safeArray(decisionObj.rule_hits).length ? `
                            <div style="margin-top:8px;">
                                ${safeArray(decisionObj.rule_hits).map(r => `
                                    <div style="font-size:0.8rem;margin-bottom:4px;">${r.rule_id || 'RULE'}: ${r.reason || ''}</div>
                                `).join('')}
                            </div>` : ''}
                        </div>` : ''}
                    </div>` : ''}

                    ${Object.keys(fraudObj).length ? `
                    <div class="detail-card" style="margin-bottom:24px;">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">Fraud Analysis</h3>
                        <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
                    <div class="fraud-gauge gauge-${fraudObj.risk_level || 'UNKNOWN'}">${((fraudObj.risk_score || fraudObj.fraud_risk_score || 0)*100).toFixed(0)}%</div>
                            <div>
                                <div style="font-weight:bold;">${fraudObj.risk_level || 'UNKNOWN'} Risk</div>
                                <div style="font-size:0.85rem;color:var(--text-secondary);">Recommendation: ${fraudObj.recommendation || 'REVIEW'}</div>
                            </div>
                        </div>
                        ${safeArray(fraudObj.flags).length > 0 ? `
                        <div style="margin-top:12px;">
                            ${safeArray(fraudObj.flags).map(f => `
                                <div style="background:rgba(239, 68, 68, 0.1); border-left: 4px solid var(--accent-red); padding: 8px 12px; margin-bottom: 8px; border-radius: 4px;">
                                    <div style="font-size:0.85rem; font-weight:600; color:var(--accent-red);">${f.flag_type}</div>
                                    <div style="font-size:0.85rem; margin-top:4px;">${f.description}</div>
                                    ${f.evidence ? `<div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px; font-family:var(--font-mono);">${f.evidence}</div>` : ''}
                                </div>
                            `).join('')}
                        </div>
                        ` : ''}
                    </div>` : ''}

                    ${Object.keys(advisoryObj).length ? `
                    <div class="detail-card">
                        <h3 style="margin-bottom:16px;font-size:0.9rem;text-transform:uppercase;color:var(--accent-purple);">GP Advisory</h3>
                        <p style="font-size:0.9rem;line-height:1.5;margin-bottom:12px;">${advisoryObj.summary || 'No advisory available.'}</p>
                        ${currentLang === 'bm' && advisoryObj.summary_bm ? `<p style="font-size:0.9rem;line-height:1.5;margin-bottom:12px;color:var(--text-secondary);font-style:italic;">${advisoryObj.summary_bm}</p>` : ''}
                    </div>` : ''}
                    ${(claim.status === 'UNDER_REVIEW' || claim.status === 'PENDING_APPROVAL' || claim.status === 'PENDING_DENIAL') && currentUser && (currentUser.role === 'TPA_PROCESSOR' || currentUser.role === 'SYSTEM_ADMIN') ? `
                    <div class="detail-card" style="margin-top:24px;">
                        <h3 style="margin-bottom:12px;font-size:0.9rem;text-transform:uppercase;color:var(--text-secondary);">Human Review Required</h3>
                        <p style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:10px;">This claim has been flagged for manual sign-off. AI recommendation: <strong style="color:#fff;">${Object.keys(decisionObj).length ? (decisionObj._ai_decision || decisionObj.decision || 'N/A') : 'N/A'}</strong>${decisionObj._ai_confidence ? ` (Confidence: ${(decisionObj._ai_confidence*100).toFixed(0)}%)` : ''}</p>
                        <button class="btn btn-primary btn-sm" onclick="submitReview(${claim.id}, 'APPROVE')">✓ Approve</button>
                        <button class="btn btn-ghost btn-sm" style="margin-left:8px;background:rgba(239,68,68,0.15);color:var(--accent-red);" onclick="submitReview(${claim.id}, 'DENY')">✗ Deny</button>
                    </div>` : ''}
                </div>
            </div>
        `;
        body.innerHTML = html;

        // Update suggested chat questions
        updateChatSuggestions();

    } catch (e) {
        body.innerHTML = `<p class="empty-state" style="color:var(--accent-red)">Error loading claim: ${e.message}</p>`;
    }
}

async function submitReview(claimId, action) {
    const reasonInput = prompt(`Review reason for ${action}:`);
    if (reasonInput === null) return;
    const reason = reasonInput || "";
    const res = await apiFetch(`/claims/${claimId}/review`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ action, reason })
    });
    if (!res.ok) {
        alert("Review action failed.");
        return;
    }
    await openClaim(claimId);
    if (currentView === "claims") loadClaims();
}

function closeModal() { document.getElementById("claimModal").classList.remove("active"); currentClaimContext = null; }

// --- CHAT ---
function updateChatSuggestions(questions) {
    const defaultQs = ["Why was this decision made?", "What is the fraud risk based on?", "How can I avoid denials for this?"];
    const qs = questions || defaultQs;
    const wrap = document.getElementById("chatSuggested");
    wrap.innerHTML = '';
    qs.forEach(q => {
        const btn = document.createElement('button');
        btn.className = 'chat-sugg-btn';
        btn.textContent = q;
        btn.addEventListener('click', () => {
            document.getElementById('chatInput').value = q;
            sendChatMessage();
        });
        wrap.appendChild(btn);
    });
}

async function sendChatMessage() {
    const input = document.getElementById("chatInput");
    const text = input.value.trim();
    if (!text || !currentClaimContext) return;
    
    const messages = document.getElementById("chatMessages");
    const userMsg = document.createElement('div');
    userMsg.className = 'chat-msg chat-msg-user';
    userMsg.textContent = text;
    messages.appendChild(userMsg);
    input.value = "";
    messages.scrollTop = messages.scrollHeight;
    
    const loadingId = "msg-" + Date.now();
    messages.innerHTML += `<div class="chat-msg chat-msg-system" id="${loadingId}">Thinking...</div>`;
    messages.scrollTop = messages.scrollHeight;

    try {
        const response = await apiFetch(`/claims/${currentClaimContext.id}/chat`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ question: text })
        });
        const res = await response.json();
        
        if (!response.ok) {
            throw new Error(res.detail || "Error communicating with GLM.");
        }
        
        document.getElementById(loadingId).innerText = currentLang === 'bm' && res.answer_bm ? res.answer_bm : res.answer;
        if (res.follow_up_questions) updateChatSuggestions(res.follow_up_questions);
    } catch (e) {
        document.getElementById(loadingId).innerText = e.message || "Error communicating with GLM.";
    }
}

// --- APPEAL ---
function showAppealModal(claimId) {
    document.getElementById("appealModal").classList.add("active");
    document.getElementById("appealModal").dataset.claimId = claimId;
    document.getElementById("appealReason").value = "";
    document.getElementById("appealResult").style.display = "none";
}
function closeAppealModal() { document.getElementById("appealModal").classList.remove("active"); }

async function submitAppeal() {
    const claimId = document.getElementById("appealModal").dataset.claimId;
    const reason = document.getElementById("appealReason").value;
    if (!reason.trim()) return alert("Please provide a reason.");
    
    const btn = document.querySelector("#appealModal .btn-primary");
    btn.disabled = true; btn.innerText = "GLM is drafting rebuttal...";
    
    try {
        const res = await apiFetch(`/claims/${claimId}/appeal`, {
            method: "POST", headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ appeal_reason: reason })
        }).then(r => r.json());
        
        const resDiv = document.getElementById("appealResult");
        resDiv.style.display = "block";
        resDiv.innerHTML = `
            <div style="background:rgba(16,185,129,0.1);border:1px solid var(--accent-green);padding:16px;border-radius:8px;">
                <h3 style="color:var(--accent-green);margin-bottom:8px;">Appeal Submitted</h3>
                <p style="font-size:0.85rem;">Your appeal has been submitted and the claim is now under review. A TPA processor will evaluate it shortly.</p>
                <p style="font-size:0.85rem;margin-top:8px;color:var(--text-secondary);">Status updated to: <strong style="color:#fff;">UNDER_REVIEW</strong></p>
            </div>
        `;
        if(currentView === 'claims') loadClaims();
        if(currentView === 'denials') loadDenials();
        if(currentView === 'gpportal') loadGPPortal();
    } catch (e) {
        alert("Failed to submit appeal.");
    } finally {
        btn.disabled = false; btn.innerText = "Draft Appeal with GLM";
    }
}

// --- UTILS ---

function toggleNotif() {
    const d = document.getElementById("notifDrawer");
    d.classList.toggle("open");
}
// notifBtn listener is attached inside DOMContentLoaded below

// --- SEED DEMO ---
async function seedDemo() {
    const btn = document.getElementById("btnSeedDemo");
    if (!btn) return;

    const originalHtml = btn.innerHTML;
    btn.innerHTML = "Seeding...";
    btn.disabled = true;

    try {
        const res = await apiFetch('/demo/seed', { method: 'POST' });
        if (!res.ok) {
            const data = await parseApiBody(res);
            throw new Error(data.detail || "Failed to seed demo");
        }
        const data = await parseApiBody(res);

        // Re-apply nav in case anything changed, then navigate to dashboard
        applyRoleNav();
        if (currentView !== "dashboard") {
            window.location.hash = "#/portal/dashboard";
        } else {
            await loadDashboard();
        }

        const inserted = data.inserted_claims ?? 0;
        btn.innerHTML = `✓ Seeded (${inserted} claims)`;
        setTimeout(() => { btn.innerHTML = originalHtml; btn.disabled = false; }, 3000);
    } catch (e) {
        console.error("Seed demo error:", e);
        alert("Failed to seed demo: " + e.message);
        btn.innerHTML = originalHtml;
        btn.disabled = false;
    }
}
