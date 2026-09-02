(function () {
  "use strict";

  const STATUS_OPTIONS = ["Not Applied", "Applied", "OA", "Interview", "Offer", "Rejected", "Withdrawn"];
  const STORAGE_STATUS_KEY = "pathway.status.v1";
  const STORAGE_COLLAPSED_KEY = "pathway.collapsed.v1";
  const STORAGE_THEME_KEY = "pathway.theme.v1";
  const STORAGE_TAB_KEY = "pathway.tab.v1";

  let statuses = loadJSON(STORAGE_STATUS_KEY, {});
  let collapsed = loadJSON(STORAGE_COLLAPSED_KEY, {});
  let currentTab = localStorage.getItem(STORAGE_TAB_KEY) || "summer-internships";
  let sortKey = null;
  let sortDir = 1;

  function loadJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function saveJSON(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ }
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return "";
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
  }

  function daysFromNow(iso) {
    if (!iso) return Infinity;
    const d = new Date(iso + "T00:00:00");
    return Math.round((d - new Date()) / 86400000);
  }

  // ---------- Theme ----------
  const themeToggle = document.getElementById("theme-toggle");
  function applyTheme(t) {
    if (t === "light" || t === "dark") {
      document.documentElement.setAttribute("data-theme", t);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }
  applyTheme(localStorage.getItem(STORAGE_THEME_KEY));
  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const effectiveCurrent = current || (prefersDark ? "dark" : "light");
    const next = effectiveCurrent === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem(STORAGE_THEME_KEY, next);
  });

  // ---------- Tabs ----------
  const tabsEl = document.getElementById("tabs");
  const titleEl = document.getElementById("tracker-title");
  function renderTabs() {
    tabsEl.innerHTML = "";
    Object.keys(TRACKS).forEach((key) => {
      const track = TRACKS[key];
      const btn = document.createElement("button");
      btn.className = "tab-btn" + (key === currentTab ? " active" : "");
      btn.textContent = track.label;
      if (!track.groups.length) {
        btn.disabled = false; // still clickable, shows "coming soon"
      }
      btn.addEventListener("click", () => {
        currentTab = key;
        localStorage.setItem(STORAGE_TAB_KEY, key);
        renderTabs();
        renderTable();
      });
      tabsEl.appendChild(btn);
    });
  }

  // ---------- Filters ----------
  const searchInput = document.getElementById("search");
  const statusFilter = document.getElementById("status-filter");
  const openFilter = document.getElementById("open-filter");
  const clFilter = document.getElementById("cl-filter");
  const visaFilter = document.getElementById("visa-filter");
  const resetBtn = document.getElementById("reset-filters");

  STATUS_OPTIONS.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    statusFilter.appendChild(opt);
  });

  [searchInput, statusFilter, openFilter, clFilter].forEach((el) =>
    el.addEventListener("input", renderTable)
  );
  visaFilter.addEventListener("change", renderTable);
  resetBtn.addEventListener("click", () => {
    searchInput.value = "";
    statusFilter.value = "";
    openFilter.value = "";
    clFilter.value = "";
    visaFilter.checked = false;
    renderTable();
  });

  // ---------- Sorting ----------
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortDir *= -1;
      } else {
        sortKey = key;
        sortDir = 1;
      }
      document.querySelectorAll("th.sortable").forEach((t) => t.classList.remove("sorted"));
      th.classList.add("sorted");
      renderTable();
    });
  });

  // A listing counts as NEW for a few days after the scanner first saw it, so
  // you can spot today's additions without re-reading the whole board.
  const NEW_FOR_DAYS = 3;
  function isNew(r) {
    if (!r.firstSeen) return false;
    const seen = new Date(r.firstSeen);
    if (isNaN(seen)) return false;
    return (Date.now() - seen.getTime()) / 86400000 <= NEW_FOR_DAYS;
  }

  function getStatus(id) {
    return statuses[id] || "Not Applied";
  }
  function setStatus(id, val) {
    statuses[id] = val;
    saveJSON(STORAGE_STATUS_KEY, statuses);
  }

  function materialsBadges(materials) {
    if (!materials || !materials.length) return "";
    return `<span class="badge-row">${materials.map((m) => `<span class="badge">${m}</span>`).join("")}</span>`;
  }
  function processBadges(process) {
    if (!process || !process.length) return "";
    return `<span class="badge-row">${process
      .map((p, i) => (i === 0 ? `<span class="badge">${p}</span>` : `<span class="badge-sep">›</span><span class="badge">${p}</span>`))
      .join("")}</span>`;
  }
  function visaPill(v) {
    if (v === true) return `<span class="pill pill-yes">Yes</span>`;
    if (v === false) return `<span class="pill pill-no">No</span>`;
    return `<span class="pill pill-unknown">—</span>`;
  }
  function rollingText(v) {
    if (v === true) return "Yes";
    if (v === false) return "No";
    return "—";
  }

  function matchesFilters(r) {
    const q = searchInput.value.trim().toLowerCase();
    if (q && !(r.company.toLowerCase().includes(q) || r.programme.toLowerCase().includes(q))) return false;

    const sf = statusFilter.value;
    if (sf && getStatus(r.id) !== sf) return false;

    const of = openFilter.value;
    if (of === "open") {
      const closeDays = daysFromNow(r.closeDate);
      const opened = !r.openDate || daysFromNow(r.openDate) <= 0;
      if (!(opened && closeDays >= 0)) return false;
    } else if (of === "recent") {
      const openDays = daysFromNow(r.openDate);
      if (!(openDays <= 0 && openDays >= -14)) return false;
    }

    const cf = clFilter.value;
    const hasCL = (r.materials || []).includes("CL");
    if (cf === "yes" && !hasCL) return false;
    if (cf === "no" && hasCL) return false;

    if (visaFilter.checked && r.visa !== true) return false;

    return true;
  }

  function sortRows(rows) {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      let av = a[sortKey] || "";
      let bv = b[sortKey] || "";
      if (sortKey === "openDate" || sortKey === "closeDate") {
        av = av || "9999-99-99";
        bv = bv || "9999-99-99";
      } else {
        av = String(av).toLowerCase();
        bv = String(bv).toLowerCase();
      }
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });
  }

  const tbody = document.getElementById("table-body");
  const emptyState = document.getElementById("empty-state");
  const statsEl = document.getElementById("stats");

  function renderTable() {
    const track = TRACKS[currentTab];
    titleEl.textContent = "UK Finance Tracker — " + track.label;
    tbody.innerHTML = "";

    if (!track.groups.length) {
      emptyState.hidden = false;
      emptyState.textContent = "No listings yet for " + track.label + ". Check back soon.";
      statsEl.innerHTML = "";
      return;
    }

    let totalShown = 0;
    let totalAll = 0;
    let appliedCount = 0;
    let offerCount = 0;

    track.groups.forEach((group) => {
      const filtered = sortRows(group.rows.filter(matchesFilters));
      totalAll += group.rows.length;
      group.rows.forEach((r) => {
        const st = getStatus(r.id);
        if (st !== "Not Applied") appliedCount++;
        if (st === "Offer") offerCount++;
      });
      if (!filtered.length) return;
      totalShown += filtered.length;

      const isCollapsed = !!collapsed[group.name];
      const groupTr = document.createElement("tr");
      groupTr.className = "group-row" + (isCollapsed ? " collapsed" : "");
      groupTr.innerHTML = `<td colspan="12"><span class="chevron">▾</span>${group.name}<span class="count">${filtered.length} / ${group.rows.length}</span></td>`;
      groupTr.addEventListener("click", () => {
        collapsed[group.name] = !collapsed[group.name];
        saveJSON(STORAGE_COLLAPSED_KEY, collapsed);
        renderTable();
      });
      tbody.appendChild(groupTr);

      if (isCollapsed) return;

      filtered.forEach((r) => {
        const tr = document.createElement("tr");
        tr.className = "data-row";
        const st = getStatus(r.id);

        const closeDays = daysFromNow(r.closeDate);
        const soonClass = r.closeDate && closeDays >= 0 && closeDays <= 14 ? " soon" : "";

        tr.innerHTML = `
          <td>
            <select class="status-select" data-status="${st}" data-id="${r.id}">
              ${STATUS_OPTIONS.map((s) => `<option value="${s}" ${s === st ? "selected" : ""}>${s}</option>`).join("")}
            </select>
          </td>
          <td class="company-name">${escapeHtml(r.company)}${isNew(r) ? '<span class="new-flag">NEW</span>' : ""}</td>
          <td class="programme-name">${
            r.url
              ? `<a class="job-link" href="${escapeHtml(r.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(r.programme)}</a>`
              : escapeHtml(r.programme)
          }${r.location ? `<div class="job-location">${escapeHtml(r.location)}</div>` : ""}</td>
          <td class="date-cell">${fmtDate(r.openDate)}</td>
          <td class="date-cell${soonClass}">${fmtDate(r.closeDate)}</td>
          <td class="stage-cell">${escapeHtml(r.latestStage || "—")}</td>
          <td>${processBadges(r.process)}</td>
          <td>${escapeHtml(r.testPrep || "—")}</td>
          <td>${rollingText(r.rolling)}</td>
          <td>${materialsBadges(r.materials)}</td>
          <td>${visaPill(r.visa)}</td>
          <td class="notes-cell">${escapeHtml(r.notes || "")}</td>
        `;
        tbody.appendChild(tr);
      });
    });

    emptyState.hidden = totalShown > 0;
    if (totalShown === 0) emptyState.textContent = "No programmes match your filters.";

    statsEl.innerHTML = `<span><b>${totalAll}</b> programmes</span><span><b>${appliedCount}</b> in progress</span><span><b>${offerCount}</b> offers</span>`;

    tbody.querySelectorAll(".status-select").forEach((sel) => {
      sel.addEventListener("change", (e) => {
        setStatus(e.target.dataset.id, e.target.value);
        e.target.dataset.status = e.target.value;
        renderTable();
      });
      sel.addEventListener("click", (e) => e.stopPropagation());
    });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ---------- CSV export ----------
  document.getElementById("export-btn").addEventListener("click", () => {
    const track = TRACKS[currentTab];
    const header = ["Status", "Company", "Programme", "Opening", "Closing", "Latest Stage", "Test Prep", "Rolling", "Materials", "Visa", "Notes"];
    const lines = [header.join(",")];
    track.groups.forEach((group) => {
      group.rows.forEach((r) => {
        const fields = [
          getStatus(r.id), r.company, r.programme, r.openDate || "", r.closeDate || "",
          r.latestStage || "", r.testPrep || "", rollingText(r.rolling),
          (r.materials || []).join("/"), visaText(r.visa), r.notes || "",
        ].map((f) => `"${String(f).replace(/"/g, '""')}"`);
        lines.push(fields.join(","));
      });
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pathway-" + currentTab + ".csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
  function visaText(v) { return v === true ? "Yes" : v === false ? "No" : ""; }

  renderTabs();
  renderTable();
})();
