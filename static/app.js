/**
 * WikiHop Client Application - Main Entry Point & Orchestrator
 * Coordinates WebSocket streaming, graph visualization, history, and analytics.
 */

import { initTheme, setupThemeToggle } from "./js/theme.js";
import { formatTextWithMath, renderMathInContainer } from "./js/math.js";
import { appSettings, setupSettingsEvents, loadPresets } from "./js/settings.js";
import { setupAudioControls, playGraphPop } from "./js/audio.js";
import { fetchAssessmentsForPath } from "./js/assessment.js";
import {
    initPathCarouselControls,
    pathScreenshotCache,
    setPathScreenshotCache
} from "./js/carousel.js";
import {
    initForceGraph,
    resetForceGraph,
    recordPageInGraph,
    highlightFinalPathInGraph,
    clearGraphPathTimers,
    graphSimulation
} from "./js/graph.js";
import {
    loadSearchHistory,
    saveCurrentSearchToHistory,
    renderHistoryList,
    setupHistoryControls,
    searchHistory,
    activeHistoryId,
    setActiveHistoryId,
    saveHistoryToStorage
} from "./js/history.js";
import {
    initStatsModule,
    fetchAndRenderPageStats,
    renderPageStatsChart
} from "./js/stats.js";
import {
    setupAutocomplete,
    setupRandomButton,
    setupFormButtons,
    setupVisitedFilter,
    setupCopyButtons,
    setupShutdown,
    showResultCard,
    appendVisitedTableRow,
    openScreenshotModal,
    showAlert,
    setRunningState,
    resetUI,
    startTimer,
    stopTimer,
    initHopChainObserver,
    renderLiveTrail
} from "./js/ui.js";

// Application State
let socket = null;
let totalLinksAccumulated = 0;
let visitedPagesList = [];
let currentFoundPath = [];
let currentLinkContext = null;
let currentCrawlParams = {
    start: "",
    target: "",
    algorithm: "heuristic",
    maxPages: 35,
    maxDepth: 5,
    contextWords: 150,
};

function getRuntimeState() {
    return {
        visitedPagesList,
        currentFoundPath,
        currentLinkContext,
        currentCrawlParams,
        totalLinksAccumulated,
        appSettings,
        pathScreenshots: { ...pathScreenshotCache }
    };
}

// WebSocket Connection
function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/search`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WebSocket connected to WikiHop server.");
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        } catch (err) {
            console.error("Failed to parse WebSocket message:", err);
        }
    };

    socket.onclose = () => {
        console.log("WebSocket closed. Attempting reconnect in 2s...");
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = (err) => {
        console.error("WebSocket error:", err);
    };
}

// Handle Incoming Server Messages
function handleServerMessage(data) {
    const eventType = data.event;
    const kpiPagesSub = document.getElementById("kpiPagesSub");
    const kpiStatusBadge = document.getElementById("kpiStatusBadge");
    const statsSection = document.getElementById("statsSection");
    const liveInspectorCard = document.getElementById("liveInspectorCard");
    const intermediateSection = document.getElementById("intermediateSection");
    const liveDirectionBadge = document.getElementById("liveDirectionBadge");
    const progressBar = document.getElementById("progressBar");
    const kpiPagesVisited = document.getElementById("kpiPagesVisited");
    const kpiCurrentDepth = document.getElementById("kpiCurrentDepth");
    const kpiDepthSub = document.getElementById("kpiDepthSub");
    const kpiLinksCount = document.getElementById("kpiLinksCount");
    const kpiLinksSub = document.getElementById("kpiLinksSub");
    const liveHopBadge = document.getElementById("liveHopBadge");
    const livePageTitle = document.getElementById("livePageTitle");
    const livePageLink = document.getElementById("livePageLink");
    const livePageSnippet = document.getElementById("livePageSnippet");
    const liveScreenshotImg = document.getElementById("liveScreenshotImg");
    const noScreenshotPlaceholder = document.getElementById("noScreenshotPlaceholder");
    const intermediateCountBadge = document.getElementById("intermediateCountBadge");
    const scopePathOnly = document.getElementById("scopePathOnly");
    const scopeAllVisited = document.getElementById("scopeAllVisited");

    if (eventType === "started") {
        setRunningState(true);
        startTimer();
        if (kpiPagesSub) kpiPagesSub.textContent = "0 forward \u2022 0 backward";
        const backlinksCount = data.target_backlinks_count || 0;
        if (kpiStatusBadge) {
            if (data.is_niche) {
                const bridgeCount = data.category_bridges_count || 0;
                kpiStatusBadge.textContent = `Niche Target: Seeded ${bridgeCount} Category Bridges (${backlinksCount} direct)`;
            } else {
                kpiStatusBadge.textContent = backlinksCount > 0 ? `Mapped ${backlinksCount.toLocaleString()} target backlinks` : "Playwright navigating...";
            }
        }
        if (statsSection) statsSection.classList.remove("d-none");
        if (liveInspectorCard) liveInspectorCard.classList.remove("d-none");
        if (intermediateSection) intermediateSection.classList.remove("d-none");

        if (liveDirectionBadge) {
            liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
            liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
        }

        resetForceGraph(data.start, data.target, data.via || (currentCrawlParams ? currentCrawlParams.via : null));

    } else if (eventType === "visiting") {
        const page = data.page;
        const totalVisited = data.total_visited;

        visitedPagesList.push(page);
        totalLinksAccumulated += page.links_count || 0;

        const maxPages = appSettings.maxPages;
        const pct = Math.min(Math.round((totalVisited / maxPages) * 100), 98);
        if (progressBar) progressBar.style.width = `${pct}%`;

        if (kpiPagesVisited) kpiPagesVisited.textContent = totalVisited;
        const fCount = data.forward_visited_count !== undefined ? data.forward_visited_count : (page.direction === "forward" ? 1 : 0);
        const bCount = data.backward_visited_count !== undefined ? data.backward_visited_count : (page.direction === "backward" ? 1 : 0);
        if (kpiPagesSub) kpiPagesSub.textContent = `${fCount} forward \u2022 ${bCount} backward`;
        if (kpiCurrentDepth) kpiCurrentDepth.textContent = page.depth;
        if (kpiDepthSub) kpiDepthSub.textContent = `Hop level ${page.depth}`;
        if (kpiLinksCount) kpiLinksCount.textContent = totalLinksAccumulated.toLocaleString();
        const linkKind = (page.links_type === 'incoming_backlinks' || page.direction === 'backward') ? 'backlinks' : 'outgoing';
        if (kpiLinksSub) kpiLinksSub.textContent = `+${page.links_count} ${linkKind} on this step`;

        if (liveDirectionBadge) {
            if (page.direction === "backward") {
                liveDirectionBadge.className = "badge bg-info-subtle text-info-emphasis border border-info-subtle";
                liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-left-circle me-1"></i> Backward from Target`;
            } else {
                liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
                liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
            }
        }

        if (liveHopBadge) liveHopBadge.textContent = `Hop ${page.depth}`;
        if (livePageTitle) livePageTitle.textContent = page.title;
        if (livePageLink) livePageLink.href = page.url;
        if (livePageSnippet) {
            livePageSnippet.innerHTML = formatTextWithMath(page.snippet || "Playwright loaded page and analyzed internal links.");
            renderMathInContainer(livePageSnippet);
        }

        if (page.screenshot && liveScreenshotImg) {
            liveScreenshotImg.src = page.screenshot;
            liveScreenshotImg.classList.remove("d-none");
            if (noScreenshotPlaceholder) noScreenshotPlaceholder.classList.add("d-none");
            liveScreenshotImg.onclick = () => openScreenshotModal(page.title, page.screenshot);
        } else if (liveScreenshotImg) {
            liveScreenshotImg.classList.add("d-none");
            if (noScreenshotPlaceholder) noScreenshotPlaceholder.classList.remove("d-none");
        }

        renderLiveTrail(page.path_so_far);
        appendVisitedTableRow(page);
        if (intermediateCountBadge) intermediateCountBadge.textContent = visitedPagesList.length;

        recordPageInGraph(page, page.direction);

    } else if (eventType === "found") {
        stopTimer();
        setRunningState(false);
        if (progressBar) {
            progressBar.style.width = "100%";
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-success");
        }
        if (kpiStatusBadge) kpiStatusBadge.textContent = "Path Found!";

        if (data.forward_visited_count !== undefined && data.backward_visited_count !== undefined && kpiPagesSub) {
            kpiPagesSub.textContent = `${data.forward_visited_count} forward \u2022 ${data.backward_visited_count} backward`;
        }

        currentFoundPath = data.path;
        currentLinkContext = data.link_context;
        setPathScreenshotCache({});
        showResultCard(data, visitedPagesList, (cache) => {
            const item = searchHistory.find(h => h.id === activeHistoryId);
            if (item) {
                item.path_screenshots = { ...cache };
                saveHistoryToStorage();
            }
        });
        highlightFinalPathInGraph(data.path);
        saveCurrentSearchToHistory("found", data, getRuntimeState(), restoreHistoricalSearch);
        if (scopePathOnly) scopePathOnly.checked = true;
        fetchAndRenderPageStats();

    } else if (eventType === "bridge_seeding") {
        const count = data.new_bridges_count || 0;
        const total = data.total_bridges_count || count;
        if (kpiStatusBadge) {
            kpiStatusBadge.textContent = `⚡ Seeded ${count} category bridges (30+ pages explored)`;
            kpiStatusBadge.className = "badge bg-info text-dark rounded-pill px-3 py-1.5 shadow-sm";
        }
        console.log(`[WikiHop] Mid-crawl category bridge seeding: ${count} bridges added (total: ${total}).`);
        playGraphPop("bridge");

    } else if (eventType === "not_found") {
        stopTimer();
        setRunningState(false);
        if (progressBar) {
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-warning");
        }
        if (kpiStatusBadge) kpiStatusBadge.textContent = "Limit reached";
        showAlert(data.message || "Reached maximum search limit without finding target link.");
        saveCurrentSearchToHistory("not_found", data, getRuntimeState(), restoreHistoricalSearch);
        if (visitedPagesList.length > 0) {
            if (scopeAllVisited) scopeAllVisited.checked = true;
            fetchAndRenderPageStats();
        }

    } else if (eventType === "cancelled") {
        stopTimer();
        setRunningState(false);
        if (progressBar) {
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-secondary");
        }
        if (kpiStatusBadge) kpiStatusBadge.textContent = "Crawl stopped";
        showAlert(data.message || "Search stopped by user.");
        saveCurrentSearchToHistory("cancelled", data, getRuntimeState(), restoreHistoricalSearch);
        if (visitedPagesList.length > 0) {
            if (scopeAllVisited) scopeAllVisited.checked = true;
            fetchAndRenderPageStats();
        }

    } else if (eventType === "error") {
        stopTimer();
        setRunningState(false);
        if (progressBar) {
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-danger");
        }
        if (kpiStatusBadge) kpiStatusBadge.textContent = "Error";
        showAlert(data.message || "An error occurred during crawling.");
        saveCurrentSearchToHistory("error", data, getRuntimeState(), restoreHistoricalSearch);
    }
}

// Restore a complete historical search
function restoreHistoricalSearch(item) {
    const startBtn = document.getElementById("startBtn");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");
    const viaInput = document.getElementById("viaInput");
    const statsSection = document.getElementById("statsSection");
    const kpiPagesVisited = document.getElementById("kpiPagesVisited");
    const kpiPagesSub = document.getElementById("kpiPagesSub");
    const kpiCurrentDepth = document.getElementById("kpiCurrentDepth");
    const kpiDepthSub = document.getElementById("kpiDepthSub");
    const kpiLinksCount = document.getElementById("kpiLinksCount");
    const kpiLinksSub = document.getElementById("kpiLinksSub");
    const kpiElapsedTime = document.getElementById("kpiElapsedTime");
    const kpiStatusBadge = document.getElementById("kpiStatusBadge");
    const progressBar = document.getElementById("progressBar");
    const visitedTableBody = document.getElementById("visitedTableBody");
    const intermediateSection = document.getElementById("intermediateSection");
    const intermediateCountBadge = document.getElementById("intermediateCountBadge");
    const liveInspectorCard = document.getElementById("liveInspectorCard");
    const liveDirectionBadge = document.getElementById("liveDirectionBadge");
    const liveHopBadge = document.getElementById("liveHopBadge");
    const livePageTitle = document.getElementById("livePageTitle");
    const livePageLink = document.getElementById("livePageLink");
    const livePageSnippet = document.getElementById("livePageSnippet");
    const liveScreenshotImg = document.getElementById("liveScreenshotImg");
    const noScreenshotPlaceholder = document.getElementById("noScreenshotPlaceholder");
    const resultCard = document.getElementById("resultCard");
    const pathCarouselCard = document.getElementById("pathCarouselCard");
    const resultMeetingBadge = document.getElementById("resultMeetingBadge");
    const intermediateStepsCard = document.getElementById("intermediateStepsCard");
    const contextCard = document.getElementById("contextCard");
    const alertCard = document.getElementById("alertCard");
    const graphCard = document.getElementById("graphCard");
    const historyOffcanvasEl = document.getElementById("historyOffcanvas");

    if (socket && socket.readyState === WebSocket.OPEN && startBtn && startBtn.classList.contains("d-none")) {
        socket.send(JSON.stringify({ action: "stop" }));
    }
    setRunningState(false);
    stopTimer();

    if (startInput) startInput.value = item.start;
    if (targetInput) targetInput.value = item.target;
    if (viaInput) viaInput.value = item.via || "";

    if (statsSection) statsSection.classList.remove("d-none");
    if (kpiPagesVisited) kpiPagesVisited.textContent = item.total_visited;
    if (kpiPagesSub) kpiPagesSub.textContent = item.kpi_pages_sub || `${item.forward_visited_count || 0} forward \u2022 ${item.backward_visited_count || 0} backward`;

    const hopsOrDepth = item.result_data ? item.result_data.hops : item.max_depth_reached;
    if (kpiCurrentDepth) kpiCurrentDepth.textContent = hopsOrDepth !== undefined ? hopsOrDepth : 0;
    if (kpiDepthSub) kpiDepthSub.textContent = item.kpi_depth_sub || (item.result_data ? `Hops: ${item.result_data.hops}` : `Max hop ${item.max_depth_reached || 0}`);

    if (kpiLinksCount) kpiLinksCount.textContent = (item.total_links_accumulated || 0).toLocaleString();
    if (kpiLinksSub) kpiLinksSub.textContent = item.kpi_links_sub || "Recorded search";
    if (kpiElapsedTime) kpiElapsedTime.textContent = item.elapsed || "0.0s";
    if (kpiStatusBadge) kpiStatusBadge.textContent = item.status_badge_text || (item.status === "found" ? "Path Found!" : item.status);

    if (progressBar) {
        progressBar.style.width = "100%";
        progressBar.classList.remove("progress-bar-animated");
        if (item.status === "found") {
            progressBar.className = "progress-bar bg-success";
        } else if (item.status === "not_found") {
            progressBar.className = "progress-bar bg-warning";
        } else if (item.status === "cancelled") {
            progressBar.className = "progress-bar bg-secondary";
        } else {
            progressBar.className = "progress-bar bg-danger";
        }
    }

    visitedPagesList = item.visited_pages ? [...item.visited_pages] : [];
    totalLinksAccumulated = item.total_links_accumulated || 0;
    if (visitedTableBody) visitedTableBody.innerHTML = "";

    if (visitedPagesList.length > 0) {
        if (intermediateSection) intermediateSection.classList.remove("d-none");
        if (intermediateCountBadge) intermediateCountBadge.textContent = visitedPagesList.length;
        visitedPagesList.forEach(p => appendVisitedTableRow(p));

        if (liveInspectorCard) liveInspectorCard.classList.remove("d-none");
        const lastPage = visitedPagesList[visitedPagesList.length - 1];
        if (liveDirectionBadge) {
            if (lastPage.direction === "backward") {
                liveDirectionBadge.className = "badge bg-info-subtle text-info-emphasis border border-info-subtle";
                liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-left-circle me-1"></i> Backward from Target`;
            } else {
                liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
                liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
            }
        }
        if (liveHopBadge) liveHopBadge.textContent = `Hop ${lastPage.depth}`;
        if (livePageTitle) livePageTitle.textContent = lastPage.title;
        if (livePageLink) livePageLink.href = lastPage.url;
        if (livePageSnippet) {
            livePageSnippet.innerHTML = formatTextWithMath(lastPage.snippet || "Playwright inspected page.");
            renderMathInContainer(livePageSnippet);
        }
        if (lastPage.screenshot && liveScreenshotImg) {
            liveScreenshotImg.src = lastPage.screenshot;
            liveScreenshotImg.classList.remove("d-none");
            if (noScreenshotPlaceholder) noScreenshotPlaceholder.classList.add("d-none");
            liveScreenshotImg.onclick = () => openScreenshotModal(lastPage.title, lastPage.screenshot);
        } else if (liveScreenshotImg) {
            liveScreenshotImg.classList.add("d-none");
            if (noScreenshotPlaceholder) noScreenshotPlaceholder.classList.remove("d-none");
        }
        renderLiveTrail(lastPage.path_so_far);
    } else {
        if (intermediateSection) intermediateSection.classList.add("d-none");
        if (liveInspectorCard) liveInspectorCard.classList.add("d-none");
    }

    if (item.status === "found" && item.result_data) {
        if (alertCard) alertCard.classList.add("d-none");
        setPathScreenshotCache(item.path_screenshots || {});
        currentFoundPath = item.result_data.path || [];
        currentLinkContext = item.result_data.link_context || null;
        showResultCard(item.result_data, visitedPagesList, (cache) => {
            item.path_screenshots = { ...cache };
            saveHistoryToStorage();
        });
        if (resultCard) resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

        if (typeof d3 !== "undefined") {
            const sInfo = item.start_info || { title: currentFoundPath[0] || item.start };
            const tInfo = item.target_info || { title: currentFoundPath[currentFoundPath.length - 1] || item.target };
            const vInfo = item.via_info || (item.via ? { title: item.via } : null);
            resetForceGraph(sInfo, tInfo, vInfo, true);
            (visitedPagesList || []).forEach(p => recordPageInGraph(p, p.direction, true));
            highlightFinalPathInGraph(currentFoundPath, true);
        }

        if (!item.result_data.assessments && currentFoundPath.length > 0) {
            fetchAssessmentsForPath(currentFoundPath, appSettings.lang || "en").then(ass => {
                if (ass && Object.keys(ass).length > 0) {
                    item.result_data.assessments = ass;
                    saveHistoryToStorage();
                    showResultCard(item.result_data, visitedPagesList);
                }
            });
        }
    } else {
        if (resultCard) resultCard.classList.add("d-none");
        if (pathCarouselCard) pathCarouselCard.classList.add("d-none");
        if (resultMeetingBadge) resultMeetingBadge.classList.add("d-none");
        if (intermediateStepsCard) intermediateStepsCard.classList.add("d-none");
        if (contextCard) contextCard.classList.add("d-none");
        if (graphCard) graphCard.classList.add("d-none");
        if (graphSimulation) graphSimulation.stop();
        showAlert(item.message || (item.status === "cancelled" ? "Search stopped by user." : item.status === "not_found" ? "Reached maximum search limit without finding target link." : "An error occurred during crawling."));
        if (alertCard) alertCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    try {
        if (historyOffcanvasEl && typeof bootstrap !== "undefined") {
            const offcanvasInstance = bootstrap.Offcanvas.getInstance(historyOffcanvasEl);
            if (offcanvasInstance) offcanvasInstance.hide();
        }
    } catch (e) {
        console.error("Offcanvas hide error:", e);
    }
}

// Initialization on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    setupThemeToggle(() => {
        renderPageStatsChart();
    });

    setupSettingsEvents({
        onLanguageChange: () => {
            loadPresets();
        },
        onSettingsSave: () => {
            loadPresets();
        }
    });

    loadSearchHistory(restoreHistoricalSearch);
    setupHistoryControls(restoreHistoricalSearch);
    initStatsModule(getRuntimeState);
    initPathCarouselControls();
    initHopChainObserver();
    setupAudioControls();

    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");
    const viaInput = document.getElementById("viaInput");
    const startSuggestions = document.getElementById("startSuggestions");
    const targetSuggestions = document.getElementById("targetSuggestions");
    const viaSuggestions = document.getElementById("viaSuggestions");
    const searchForm = document.getElementById("searchForm");
    const stopBtn = document.getElementById("stopBtn");

    setupAutocomplete(startInput, startSuggestions);
    setupAutocomplete(targetInput, targetSuggestions);
    if (viaInput && viaSuggestions) setupAutocomplete(viaInput, viaSuggestions);

    setupFormButtons();
    loadPresets();
    setupRandomButton();
    setupVisitedFilter();
    setupCopyButtons(() => currentFoundPath, () => currentLinkContext);
    setupShutdown(() => {
        if (socket) {
            socket.onclose = null;
            socket.close();
        }
    });

    connectWebSocket();

    if (searchForm) {
        searchForm.addEventListener("submit", (e) => {
            e.preventDefault();

            const start = startInput ? startInput.value.trim() : "";
            const target = targetInput ? targetInput.value.trim() : "";
            const via = viaInput ? viaInput.value.trim() : "";

            if (!start || !target) return;

            currentCrawlParams = {
                start: start,
                via: via,
                target: target,
                lang: appSettings.lang || "en",
                algorithm: appSettings.algorithm,
                maxPages: appSettings.maxPages,
                maxDepth: appSettings.maxDepth,
                contextWords: appSettings.contextWords,
            };

            resetUI();

            const payload = {
                action: "start",
                start: start,
                via: via,
                target: target,
                lang: appSettings.lang || "en",
                algorithm: appSettings.algorithm,
                max_pages: appSettings.maxPages,
                max_depth: appSettings.maxDepth,
                capture_screenshots: appSettings.captureScreenshots,
                headless: appSettings.headless,
                adaptive_balancing: appSettings.adaptiveBalancing,
                context_words: appSettings.contextWords,
            };

            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify(payload));
            } else {
                alert("WebSocket is not connected. Please refresh the page.");
            }
        });
    }

    if (stopBtn) {
        stopBtn.addEventListener("click", () => {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ action: "stop" }));
            }
            setRunningState(false);
        });
    }
});
