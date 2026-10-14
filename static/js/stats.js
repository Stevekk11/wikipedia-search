/**
 * Article Analytics & Page Statistics Graphs Module (XTools & MediaWiki APIs via Chart.js)
 */

import { escapeHtml } from "./math.js";
import { appSettings } from "./settings.js";

export let pageStatsCache = {};
export let currentActiveMetric = "words_size";
export let currentStatsScope = "path";
export let pageStatsChartInstance = null;

let getRuntimeStateFn = null;

export function initStatsModule(getState) {
    getRuntimeStateFn = getState;
    setupStatsEvents();
}

export function getActiveScopeTitles() {
    const state = typeof getRuntimeStateFn === "function" ? getRuntimeStateFn() : {};
    const currentFoundPath = state.currentFoundPath || [];
    const visitedPagesList = state.visitedPagesList || [];
    const currentCrawlParams = state.currentCrawlParams || {};

    if (currentStatsScope === "path" && currentFoundPath && currentFoundPath.length > 0) {
        return [...currentFoundPath];
    }

    const titles = [];
    if (visitedPagesList && visitedPagesList.length > 0) {
        visitedPagesList.forEach((p) => {
            if (p.title && !titles.includes(p.title)) {
                titles.push(p.title);
            }
        });
    }

    if (currentFoundPath && currentFoundPath.length > 0) {
        currentFoundPath.forEach((t) => {
            if (t && !titles.includes(t)) {
                titles.push(t);
            }
        });
    }

    if (titles.length === 0 && currentCrawlParams) {
        if (currentCrawlParams.start) titles.push(currentCrawlParams.start);
        if (currentCrawlParams.via) titles.push(currentCrawlParams.via);
        if (currentCrawlParams.target) titles.push(currentCrawlParams.target);
    }

    return titles;
}

export async function fetchAndRenderPageStats(forceRefresh = false) {
    const titles = getActiveScopeTitles();
    if (!titles || titles.length === 0) return;

    const pageStatsGraphSection = document.getElementById("pageStatsGraphSection");
    const scopePathCount = document.getElementById("scopePathCount");
    const scopeAllCount = document.getElementById("scopeAllCount");
    const statsChartLoading = document.getElementById("statsChartLoading");
    const statsNavbarBadge = document.getElementById("statsNavbarBadge");

    const state = typeof getRuntimeStateFn === "function" ? getRuntimeStateFn() : {};
    const currentFoundPath = state.currentFoundPath || [];
    const visitedPagesList = state.visitedPagesList || [];

    if (pageStatsGraphSection) {
        pageStatsGraphSection.classList.remove("d-none");
    }

    if (scopePathCount) {
        scopePathCount.textContent = (currentFoundPath || []).length;
    }
    if (scopeAllCount) {
        const allCount = visitedPagesList.length || (currentFoundPath || []).length;
        scopeAllCount.textContent = allCount;
    }

    if (statsNavbarBadge) {
        const count = titles.length;
        statsNavbarBadge.textContent = count;
        if (count > 0) statsNavbarBadge.classList.remove("d-none");
    }

    const missingTitles = titles.filter((t) => forceRefresh || !pageStatsCache[t]);

    if (missingTitles.length > 0) {
        if (statsChartLoading) statsChartLoading.classList.remove("d-none");
        try {
            const lang = (appSettings.lang || "en").toLowerCase();
            const encodedTitles = encodeURIComponent(missingTitles.join(","));
            const res = await fetch(`/api/batch-page-stats?titles=${encodedTitles}&lang=${lang}`);
            if (res.ok) {
                const data = await res.json();
                if (data.stats) {
                    Object.assign(pageStatsCache, data.stats);
                }
            }
        } catch (err) {
            console.warn("[WikiHop] Failed to fetch article statistics:", err);
        } finally {
            if (statsChartLoading) statsChartLoading.classList.add("d-none");
        }
    }

    renderStatsUIFromCache();
}

export function renderStatsUIFromCache() {
    const titles = getActiveScopeTitles();
    if (!titles || titles.length === 0) return;

    const statsList = titles.map((t) => {
        if (pageStatsCache[t]) return pageStatsCache[t];
        const underscore = t.replace(/ /g, "_");
        const space = t.replace(/_/g, " ");
        return pageStatsCache[underscore] || pageStatsCache[space] || {
            title: t,
            words: 0,
            bytes: 0,
            file_size_formatted: "0 B",
            file_size_kb: 0,
            revisions: 0,
            editors: 0,
            watchers: 0,
            pageviews: 0,
            references: 0,
            sections: 0,
            assessment: "",
        };
    });

    updateStatsSummaryKpis(statsList);
    renderPageStatsChart(titles, statsList);
    renderStatsBreakdownTable(statsList);
}

export function updateStatsSummaryKpis(statsList) {
    if (!statsList || statsList.length === 0) return;

    const kpiTopWordsVal = document.getElementById("kpiTopWordsVal");
    const kpiTopWordsTitle = document.getElementById("kpiTopWordsTitle");
    const kpiTopSizeVal = document.getElementById("kpiTopSizeVal");
    const kpiTopSizeTitle = document.getElementById("kpiTopSizeTitle");
    const kpiTopEditsVal = document.getElementById("kpiTopEditsVal");
    const kpiTopEditsTitle = document.getElementById("kpiTopEditsTitle");
    const kpiTopViewsVal = document.getElementById("kpiTopViewsVal");
    const kpiTopViewsTitle = document.getElementById("kpiTopViewsTitle");

    const maxWordsItem = statsList.reduce((max, s) => (s.words > (max.words || 0) ? s : max), {});
    const maxSizeItem = statsList.reduce((max, s) => (s.bytes > (max.bytes || 0) ? s : max), {});
    const maxEditsItem = statsList.reduce((max, s) => (s.revisions > (max.revisions || 0) ? s : max), {});
    const maxViewsItem = statsList.reduce((max, s) => (s.pageviews > (max.pageviews || 0) ? s : max), {});

    if (kpiTopWordsVal) {
        kpiTopWordsVal.textContent = maxWordsItem.words ? maxWordsItem.words.toLocaleString() : "--";
    }
    if (kpiTopWordsTitle) {
        kpiTopWordsTitle.textContent = maxWordsItem.title || "No data";
        kpiTopWordsTitle.title = maxWordsItem.title || "";
    }

    if (kpiTopSizeVal) {
        kpiTopSizeVal.textContent = maxSizeItem.bytes ? maxSizeItem.file_size_formatted || `${maxSizeItem.file_size_kb} KB` : "--";
    }
    if (kpiTopSizeTitle) {
        kpiTopSizeTitle.textContent = maxSizeItem.title || "No data";
        kpiTopSizeTitle.title = maxSizeItem.title || "";
    }

    if (kpiTopEditsVal) {
        kpiTopEditsVal.textContent = maxEditsItem.revisions ? maxEditsItem.revisions.toLocaleString() : "--";
    }
    if (kpiTopEditsTitle) {
        kpiTopEditsTitle.textContent = maxEditsItem.title || "No data";
        kpiTopEditsTitle.title = maxEditsItem.title || "";
    }

    if (kpiTopViewsVal) {
        kpiTopViewsVal.textContent = maxViewsItem.pageviews ? formatCompactNumber(maxViewsItem.pageviews) : "--";
    }
    if (kpiTopViewsTitle) {
        kpiTopViewsTitle.textContent = maxViewsItem.title || "No data";
        kpiTopViewsTitle.title = maxViewsItem.title || "";
    }
}

export function formatCompactNumber(num) {
    if (!num) return "0";
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toLocaleString();
}

export function renderPageStatsChart(titles = null, statsList = null) {
    const pageStatsChartCanvas = document.getElementById("pageStatsChart");
    if (!pageStatsChartCanvas || typeof Chart === "undefined") return;

    if (!titles || !statsList) {
        titles = getActiveScopeTitles();
        statsList = titles.map((t) => pageStatsCache[t] || { title: t, words: 0, bytes: 0, revisions: 0, editors: 0, watchers: 0, pageviews: 0 });
    }

    const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    const textColor = isDark ? "#cbd5e1" : "#475569";
    const gridColor = isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.06)";
    const tooltipBg = isDark ? "rgba(15, 23, 42, 0.95)" : "rgba(255, 255, 255, 0.96)";
    const tooltipText = isDark ? "#f8fafc" : "#0f172a";
    const tooltipBorder = isDark ? "rgba(255, 255, 255, 0.15)" : "rgba(0, 0, 0, 0.15)";

    if (pageStatsChartInstance) {
        pageStatsChartInstance.destroy();
        pageStatsChartInstance = null;
    }

    const labels = titles.map((t) => {
        const clean = t.replace(/_/g, " ");
        return clean.length > 16 ? clean.substring(0, 14) + "..." : clean;
    });

    let datasets = [];
    let scalesConfig = {};

    if (currentActiveMetric === "words_size") {
        datasets = [
            {
                label: "Word Count",
                type: "bar",
                data: statsList.map((s) => s.words || 0),
                backgroundColor: "rgba(59, 130, 246, 0.75)",
                borderColor: "#3b82f6",
                borderWidth: 1.5,
                borderRadius: 6,
                yAxisID: "yWords",
            },
            {
                label: "File Size (KB)",
                type: "line",
                data: statsList.map((s) => s.file_size_kb || Math.round((s.bytes || 0) / 1024)),
                borderColor: "#10b981",
                backgroundColor: "rgba(16, 185, 129, 0.15)",
                pointBackgroundColor: "#10b981",
                pointBorderColor: "#ffffff",
                pointRadius: 5,
                pointHoverRadius: 7,
                tension: 0.25,
                borderWidth: 2.5,
                yAxisID: "ySize",
            },
        ];

        scalesConfig = {
            x: {
                grid: { display: false },
                ticks: { color: textColor, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
            },
            yWords: {
                type: "linear",
                position: "left",
                beginAtZero: true,
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: (v) => v.toLocaleString(),
                    font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                },
                title: {
                    display: true,
                    text: "Words (Prose)",
                    color: "#3b82f6",
                    font: { weight: "600", size: 11 },
                },
            },
            ySize: {
                type: "linear",
                position: "right",
                beginAtZero: true,
                grid: { drawOnChartArea: false },
                ticks: {
                    color: textColor,
                    callback: (v) => `${v} KB`,
                    font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                },
                title: {
                    display: true,
                    text: "File Size (KB)",
                    color: "#10b981",
                    font: { weight: "600", size: 11 },
                },
            },
        };
    } else if (currentActiveMetric === "edits_editors") {
        datasets = [
            {
                label: "Total Revisions / Edits",
                type: "bar",
                data: statsList.map((s) => s.revisions || 0),
                backgroundColor: "rgba(245, 158, 11, 0.75)",
                borderColor: "#f59e0b",
                borderWidth: 1.5,
                borderRadius: 6,
            },
            {
                label: "Unique Editors",
                type: "bar",
                data: statsList.map((s) => s.editors || 0),
                backgroundColor: "rgba(139, 92, 246, 0.75)",
                borderColor: "#8b5cf6",
                borderWidth: 1.5,
                borderRadius: 6,
            },
        ];

        scalesConfig = {
            x: {
                grid: { display: false },
                ticks: { color: textColor, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
            },
            y: {
                beginAtZero: true,
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: (v) => v.toLocaleString(),
                    font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                },
                title: {
                    display: true,
                    text: "Count",
                    color: textColor,
                    font: { weight: "600", size: 11 },
                },
            },
        };
    } else if (currentActiveMetric === "views_watchers") {
        datasets = [
            {
                label: "30-Day Pageviews",
                type: "bar",
                data: statsList.map((s) => s.pageviews || 0),
                backgroundColor: "rgba(6, 182, 212, 0.75)",
                borderColor: "#06b6d4",
                borderWidth: 1.5,
                borderRadius: 6,
                yAxisID: "yViews",
            },
            {
                label: "Page Watchers",
                type: "line",
                data: statsList.map((s) => s.watchers || 0),
                borderColor: "#ec4899",
                backgroundColor: "rgba(236, 72, 153, 0.15)",
                pointBackgroundColor: "#ec4899",
                pointBorderColor: "#ffffff",
                pointRadius: 5,
                pointHoverRadius: 7,
                tension: 0.25,
                borderWidth: 2.5,
                yAxisID: "yWatchers",
            },
        ];

        scalesConfig = {
            x: {
                grid: { display: false },
                ticks: { color: textColor, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
            },
            yViews: {
                type: "linear",
                position: "left",
                beginAtZero: true,
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: (v) => formatCompactNumber(v),
                    font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                },
                title: {
                    display: true,
                    text: "30-Day Views",
                    color: "#06b6d4",
                    font: { weight: "600", size: 11 },
                },
            },
            yWatchers: {
                type: "linear",
                position: "right",
                beginAtZero: true,
                grid: { drawOnChartArea: false },
                ticks: {
                    color: textColor,
                    callback: (v) => v.toLocaleString(),
                    font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                },
                title: {
                    display: true,
                    text: "Watchers",
                    color: "#ec4899",
                    font: { weight: "600", size: 11 },
                },
            },
        };
    } else if (currentActiveMetric === "refs_sections") {
        datasets = [
            {
                label: "Citations / References",
                type: "bar",
                data: statsList.map((s) => s.references || 0),
                backgroundColor: "rgba(20, 184, 166, 0.75)",
                borderColor: "#14b8a6",
                borderWidth: 1.5,
                borderRadius: 6,
            },
            {
                label: "Article Sections",
                type: "bar",
                data: statsList.map((s) => s.sections || 0),
                backgroundColor: "rgba(99, 102, 241, 0.75)",
                borderColor: "#6366f1",
                borderWidth: 1.5,
                borderRadius: 6,
            },
        ];

        scalesConfig = {
            x: {
                grid: { display: false },
                ticks: { color: textColor, font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 } },
            },
            y: {
                beginAtZero: true,
                grid: { color: gridColor },
                ticks: {
                    color: textColor,
                    callback: (v) => v.toLocaleString(),
                    font: { family: "'Plus Jakarta Sans', sans-serif", size: 11 },
                },
                title: {
                    display: true,
                    text: "Count",
                    color: textColor,
                    font: { weight: "600", size: 11 },
                },
            },
        };
    }

    const ctx = pageStatsChartCanvas.getContext("2d");
    pageStatsChartInstance = new Chart(ctx, {
        data: {
            labels: labels,
            datasets: datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 650, easing: "easeOutQuart" },
            plugins: {
                legend: {
                    display: true,
                    position: "top",
                    labels: {
                        color: textColor,
                        font: { family: "'Plus Jakarta Sans', sans-serif", size: 12, weight: "500" },
                        usePointStyle: true,
                        pointStyle: "circle",
                        padding: 16,
                    },
                },
                tooltip: {
                    backgroundColor: tooltipBg,
                    titleColor: tooltipText,
                    bodyColor: tooltipText,
                    borderColor: tooltipBorder,
                    borderWidth: 1,
                    padding: 12,
                    boxPadding: 6,
                    usePointStyle: true,
                    bodyFont: { family: "'Plus Jakarta Sans', sans-serif", size: 12 },
                    titleFont: { family: "'Plus Jakarta Sans', sans-serif", size: 13, weight: "600" },
                    callbacks: {
                        title: (items) => {
                            if (items && items.length > 0) {
                                const idx = items[0].dataIndex;
                                return titles[idx] || labels[idx];
                            }
                            return "";
                        },
                        label: (context) => {
                            const val = context.parsed.y;
                            const dsLabel = context.dataset.label || "";
                            if (dsLabel.includes("Size")) {
                                return ` ${dsLabel}: ${val.toLocaleString()} KB`;
                            }
                            return ` ${dsLabel}: ${val.toLocaleString()}`;
                        },
                    },
                },
            },
            scales: scalesConfig,
        },
    });
}

export function renderStatsBreakdownTable(statsList) {
    const statsTableBody = document.getElementById("statsTableBody");
    if (!statsTableBody) return;
    statsTableBody.innerHTML = "";

    const lang = (appSettings.lang || "en").toLowerCase();

    statsList.forEach((s) => {
        const tr = document.createElement("tr");
        const slug = (s.slug || s.title || "").replace(/ /g, "_");
        const wikiUrl = `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(slug)}`;
        const xtoolsUrl = `https://xtools.wmflabs.org/articleinfo/${lang}.wikipedia.org/${encodeURIComponent(slug)}`;

        tr.innerHTML = `
            <td>
                <div class="fw-semibold">
                    <a href="${wikiUrl}" target="_blank" class="text-body-emphasis text-decoration-none">
                        ${escapeHtml(s.title || slug)}
                        <i class="bi bi-box-arrow-up-right text-muted small ms-1" style="font-size: 0.75rem;"></i>
                    </a>
                </div>
            </td>
            <td class="text-end font-monospace fw-medium">${(s.words || 0).toLocaleString()}</td>
            <td class="text-end font-monospace">${s.file_size_formatted || `${s.file_size_kb || 0} KB`}</td>
            <td class="text-end font-monospace text-warning-emphasis">${(s.revisions || 0).toLocaleString()}</td>
            <td class="text-end font-monospace text-primary">${(s.editors || 0).toLocaleString()}</td>
            <td class="text-end font-monospace text-info">${formatCompactNumber(s.pageviews || 0)}</td>
            <td class="text-end font-monospace text-danger-emphasis">${(s.watchers || 0).toLocaleString()}</td>
            <td class="text-end font-monospace text-success">${(s.references || 0).toLocaleString()}</td>
            <td class="text-center">
                <a href="${xtoolsUrl}" target="_blank" class="btn btn-outline-secondary btn-sm py-0 px-2 rounded-pill" title="View comprehensive history on XTools" style="font-size: 0.75rem;">
                    <i class="bi bi-bar-chart me-1 text-primary"></i>XTools
                </a>
            </td>
        `;

        statsTableBody.appendChild(tr);
    });
}

function setupStatsEvents() {
    const scopePathOnly = document.getElementById("scopePathOnly");
    const scopeAllVisited = document.getElementById("scopeAllVisited");
    const refreshStatsBtn = document.getElementById("refreshStatsBtn");
    const pageStatsGraphSection = document.getElementById("pageStatsGraphSection");
    const activeMetricLabel = document.getElementById("activeMetricLabel");

    if (scopePathOnly) {
        scopePathOnly.addEventListener("change", () => {
            if (scopePathOnly.checked) {
                currentStatsScope = "path";
                renderStatsUIFromCache();
            }
        });
    }

    if (scopeAllVisited) {
        scopeAllVisited.addEventListener("change", () => {
            if (scopeAllVisited.checked) {
                currentStatsScope = "all";
                renderStatsUIFromCache();
            }
        });
    }

    document.querySelectorAll(".metric-option").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const metric = btn.getAttribute("data-metric");
            if (!metric) return;
            currentActiveMetric = metric;

            document.querySelectorAll(".metric-option").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            if (activeMetricLabel) {
                activeMetricLabel.textContent = btn.textContent.trim();
            }

            renderPageStatsChart();
        });
    });

    if (refreshStatsBtn) {
        refreshStatsBtn.addEventListener("click", () => {
            fetchAndRenderPageStats(true);
        });
    }

    if (pageStatsGraphSection) {
        pageStatsGraphSection.addEventListener("shown.bs.offcanvas", () => {
            if (pageStatsChartInstance) {
                pageStatsChartInstance.resize();
            } else {
                renderPageStatsChart();
            }
        });
    }
}
