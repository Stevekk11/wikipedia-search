/**
 * Search History Module (Last 10 Searches with IndexedDB & localStorage fallback)
 */

import { escapeHtml } from "./math.js";

const MAX_HISTORY_ITEMS = 10;
const STORAGE_KEY_HISTORY = "wikihop-search-history";
const HISTORY_DB_NAME = "wikihop-db";
const HISTORY_STORE = "kv";

let historyDbPromise = null;
export let searchHistory = [];
export let activeHistoryId = null;

export function setActiveHistoryId(id) {
    activeHistoryId = id;
}

export function openHistoryDb() {
    if (!historyDbPromise) {
        historyDbPromise = new Promise((resolve, reject) => {
            if (!window.indexedDB) return reject(new Error("IndexedDB unavailable"));
            const req = indexedDB.open(HISTORY_DB_NAME, 1);
            req.onupgradeneeded = () => req.result.createObjectStore(HISTORY_STORE);
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }
    return historyDbPromise;
}

export function historyDbGet() {
    return openHistoryDb().then(db => new Promise((resolve, reject) => {
        const req = db.transaction(HISTORY_STORE, "readonly").objectStore(HISTORY_STORE).get(STORAGE_KEY_HISTORY);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    }));
}

export function historyDbSet(value) {
    return openHistoryDb().then(db => new Promise((resolve, reject) => {
        const tx = db.transaction(HISTORY_STORE, "readwrite");
        tx.objectStore(HISTORY_STORE).put(value, STORAGE_KEY_HISTORY);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
    }));
}

export function readLegacyLocalHistory() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY_HISTORY);
        const parsed = raw ? JSON.parse(raw) : null;
        return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        console.error("Error reading search history from localStorage:", e);
        return [];
    }
}

export async function loadSearchHistory(onRender) {
    let loaded = null;
    try {
        const stored = await historyDbGet();
        if (Array.isArray(stored)) loaded = stored;
    } catch (e) {
        console.warn("IndexedDB history unavailable, using localStorage:", e);
    }
    if (loaded === null || loaded.length === 0) {
        const legacy = readLegacyLocalHistory();
        if (legacy.length) {
            loaded = legacy;
            historyDbSet(legacy).then(() => localStorage.removeItem(STORAGE_KEY_HISTORY)).catch(() => {});
        }
    }
    const pending = searchHistory.filter(r => !(loaded || []).some(l => l.id === r.id));
    searchHistory = [...pending, ...(loaded || [])].slice(0, MAX_HISTORY_ITEMS);
    renderHistoryList(onRender);
}

export function saveHistoryToLocalStorage() {
    try {
        localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(searchHistory));
    } catch (e) {
        console.warn("Storage quota warning, stripping screenshots to preserve metadata:", e);
        const pruned = searchHistory.map((item, idx) => {
            if (idx > 0 && Array.isArray(item.visited_pages)) {
                return {
                    ...item,
                    visited_pages: item.visited_pages.map(p => {
                        const { screenshot, ...rest } = p;
                        return rest;
                    })
                };
            }
            return item;
        });
        try {
            localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(pruned));
        } catch (e2) {
            console.error("Failed to store search history:", e2);
        }
    }
}

export function saveHistoryToStorage() {
    historyDbSet(searchHistory).catch(e => {
        console.warn("IndexedDB save failed, falling back to localStorage:", e);
        saveHistoryToLocalStorage();
    });
}

export function saveCurrentSearchToHistory(status, extraData = {}, runtimeState = {}, onRender = null) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const dateStr = now.toLocaleDateString([], { month: "short", day: "numeric" });

    const visitedPagesList = runtimeState.visitedPagesList || [];
    const currentCrawlParams = runtimeState.currentCrawlParams || {};
    const appSettings = runtimeState.appSettings || {};

    const fCount = extraData.forward_visited_count !== undefined
        ? extraData.forward_visited_count
        : visitedPagesList.filter(p => p.direction !== "backward").length;
    const bCount = extraData.backward_visited_count !== undefined
        ? extraData.backward_visited_count
        : visitedPagesList.filter(p => p.direction === "backward").length;

    const maxDepthReached = visitedPagesList.reduce((max, p) => Math.max(max, p.depth || 0), 0);

    const kpiStatusBadge = document.getElementById("kpiStatusBadge");
    const kpiElapsedTime = document.getElementById("kpiElapsedTime");
    const kpiPagesSub = document.getElementById("kpiPagesSub");
    const kpiDepthSub = document.getElementById("kpiDepthSub");
    const kpiLinksSub = document.getElementById("kpiLinksSub");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");

    const newRecord = {
        id: Date.now() + "-" + Math.random().toString(36).substring(2, 7),
        time: timeStr,
        date: dateStr,
        start: currentCrawlParams.start || (startInput ? startInput.value.trim() : ""),
        target: currentCrawlParams.target || (targetInput ? targetInput.value.trim() : ""),
        via: currentCrawlParams.via || "",
        algorithm: currentCrawlParams.algorithm || appSettings.algorithm,
        max_pages: currentCrawlParams.maxPages || appSettings.maxPages,
        max_depth: currentCrawlParams.maxDepth || appSettings.maxDepth,
        context_words: currentCrawlParams.contextWords || appSettings.contextWords,
        status: status,
        status_badge_text: kpiStatusBadge ? kpiStatusBadge.textContent : "",
        message: extraData.message || "",
        elapsed: kpiElapsedTime ? kpiElapsedTime.textContent || "0.0s" : "0.0s",
        total_visited: visitedPagesList.length,
        forward_visited_count: fCount,
        backward_visited_count: bCount,
        total_links_accumulated: runtimeState.totalLinksAccumulated || 0,
        kpi_pages_sub: kpiPagesSub ? kpiPagesSub.textContent : "",
        kpi_depth_sub: kpiDepthSub ? kpiDepthSub.textContent : "",
        kpi_links_sub: kpiLinksSub ? kpiLinksSub.textContent : "",
        max_depth_reached: maxDepthReached,
        result_data: status === "found" ? extraData : null,
        visited_pages: visitedPagesList.map(p => ({ ...p })),
        path_screenshots: runtimeState.pathScreenshots || null
    };

    searchHistory.unshift(newRecord);
    if (searchHistory.length > MAX_HISTORY_ITEMS) {
        searchHistory = searchHistory.slice(0, MAX_HISTORY_ITEMS);
    }

    activeHistoryId = newRecord.id;
    saveHistoryToStorage();
    renderHistoryList(onRender);
}

export function renderHistoryList(onSelectHistoryItem = null) {
    const historyList = document.getElementById("historyList");
    const historyCountBadge = document.getElementById("historyCountBadge");
    const clearHistoryBtn = document.getElementById("clearHistoryBtn");
    const historyEmptyPlaceholder = document.getElementById("historyEmptyPlaceholder");

    if (!historyList) return;
    historyList.innerHTML = "";

    const count = searchHistory.length;
    if (historyCountBadge) {
        historyCountBadge.textContent = count;
        if (count > 0) {
            historyCountBadge.classList.remove("d-none");
        } else {
            historyCountBadge.classList.add("d-none");
        }
    }

    if (clearHistoryBtn) {
        clearHistoryBtn.disabled = count === 0;
    }

    if (count === 0) {
        if (historyEmptyPlaceholder) historyEmptyPlaceholder.classList.remove("d-none");
        return;
    }

    if (historyEmptyPlaceholder) historyEmptyPlaceholder.classList.add("d-none");

    searchHistory.forEach((item) => {
        let statusLabel = "";
        let badgeClass = "";
        if (item.status === "found") {
            const hops = item.result_data ? item.result_data.hops : "?";
            statusLabel = `${hops} Hop${hops === 1 ? "" : "s"}`;
            badgeClass = "bg-success-subtle text-success-emphasis border border-success-subtle";
        } else if (item.status === "not_found") {
            statusLabel = "Limit Reached";
            badgeClass = "bg-warning-subtle text-warning-emphasis border border-warning-subtle";
        } else if (item.status === "cancelled") {
            statusLabel = "Stopped";
            badgeClass = "bg-secondary-subtle text-secondary border";
        } else {
            statusLabel = "Error";
            badgeClass = "bg-danger-subtle text-danger-emphasis border border-danger-subtle";
        }

        const isActive = activeHistoryId === item.id;
        const card = document.createElement("div");
        card.className = `card p-3 shadow-sm history-item status-${item.status} ${isActive ? "active-history" : ""}`;
        card.style.cursor = "pointer";

        card.innerHTML = `
            <div class="d-flex align-items-center justify-content-between mb-1">
                <span class="badge ${badgeClass} rounded-pill px-2 py-1" style="font-size: 0.75rem;">
                    ${statusLabel}
                </span>
                <small class="text-secondary font-monospace" style="font-size: 0.72rem;">
                    ${item.date} ${item.time} &bull; ${item.elapsed}
                </small>
            </div>
            <div class="fw-bold text-body-emphasis text-truncate mb-1" style="font-size: 0.9rem;" title="${escapeHtml(item.start)} \u2192 ${escapeHtml(item.target)}">
                ${escapeHtml(item.start)} <i class="bi bi-arrow-right text-primary mx-1"></i> ${escapeHtml(item.target)}
            </div>
            <div class="d-flex align-items-center justify-content-between text-secondary small" style="font-size: 0.76rem;">
                <span><i class="bi bi-file-earmark-text me-1"></i>${item.total_visited} pages</span>
                <span><i class="bi bi-cpu me-1"></i>${item.algorithm === 'heuristic' ? 'Smart A*' : 'BFS'}</span>
                <button type="button" class="btn btn-link btn-sm text-danger p-0 delete-item-btn" title="Delete this search" style="line-height: 1;">
                    <i class="bi bi-x-circle"></i>
                </button>
            </div>
        `;

        const delBtn = card.querySelector(".delete-item-btn");
        if (delBtn) {
            delBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                searchHistory = searchHistory.filter(h => h.id !== item.id);
                if (activeHistoryId === item.id) activeHistoryId = null;
                saveHistoryToStorage();
                renderHistoryList(onSelectHistoryItem);
            });
        }

        card.addEventListener("click", () => {
            activeHistoryId = item.id;
            renderHistoryList(onSelectHistoryItem);
            if (typeof onSelectHistoryItem === "function") {
                onSelectHistoryItem(item);
            }
        });

        historyList.appendChild(card);
    });
}

export function setupHistoryControls(onSelectHistoryItem) {
    const clearHistoryBtn = document.getElementById("clearHistoryBtn");
    if (clearHistoryBtn) {
        clearHistoryBtn.addEventListener("click", () => {
            if (confirm("Clear all recent search history?")) {
                searchHistory = [];
                activeHistoryId = null;
                localStorage.removeItem(STORAGE_KEY_HISTORY);
                historyDbSet([]);
                renderHistoryList(onSelectHistoryItem);
            }
        });
    }
}
