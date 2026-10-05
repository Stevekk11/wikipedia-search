/**
 * WikiHop Client Application
 * Real-time Wikipedia Link Hop Counter using Playwright & WebSockets
 * With Settings Modal and 150-word Connecting Link Context
 */

document.addEventListener("DOMContentLoaded", () => {
    // --- Default Settings ---
    const DEFAULT_SETTINGS = {
        contextWords: 150,
        algorithm: "heuristic",
        maxPages: 35,
        maxDepth: 5,
        captureScreenshots: true,
        headless: true,
    };

    let appSettings = { ...DEFAULT_SETTINGS };

    // --- DOM Elements ---
    const searchForm = document.getElementById("searchForm");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");
    const swapBtn = document.getElementById("swapBtn");
    const startSuggestions = document.getElementById("startSuggestions");
    const targetSuggestions = document.getElementById("targetSuggestions");
    const presetsContainer = document.getElementById("presetsContainer");

    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");

    // Settings Modal Elements
    const modalContextWords = document.getElementById("modalContextWords");
    const modalContextWordsBadge = document.getElementById("modalContextWordsBadge");
    const modalAlgorithm = document.getElementById("modalAlgorithm");
    const modalMaxPages = document.getElementById("modalMaxPages");
    const modalMaxPagesBadge = document.getElementById("modalMaxPagesBadge");
    const modalMaxDepth = document.getElementById("modalMaxDepth");
    const modalMaxDepthBadge = document.getElementById("modalMaxDepthBadge");
    const modalScreenshotToggle = document.getElementById("modalScreenshotToggle");
    const modalHeadlessToggle = document.getElementById("modalHeadlessToggle");
    const saveSettingsBtn = document.getElementById("saveSettingsBtn");
    const resetSettingsBtn = document.getElementById("resetSettingsBtn");

    // Summary Badges in Search Card
    const summaryContextBadge = document.getElementById("summaryContextBadge");
    const summaryStrategyBadge = document.getElementById("summaryStrategyBadge");
    const summaryLimitBadge = document.getElementById("summaryLimitBadge");

    // Stats & KPI
    const statsSection = document.getElementById("statsSection");
    const progressBar = document.getElementById("progressBar");
    const kpiPagesVisited = document.getElementById("kpiPagesVisited");
    const kpiPagesSub = document.getElementById("kpiPagesSub");
    const kpiCurrentDepth = document.getElementById("kpiCurrentDepth");
    const kpiDepthSub = document.getElementById("kpiDepthSub");
    const kpiLinksCount = document.getElementById("kpiLinksCount");
    const kpiLinksSub = document.getElementById("kpiLinksSub");
    const kpiElapsedTime = document.getElementById("kpiElapsedTime");
    const kpiStatusBadge = document.getElementById("kpiStatusBadge");

    // Live Inspector
    const liveInspectorCard = document.getElementById("liveInspectorCard");
    const liveDirectionBadge = document.getElementById("liveDirectionBadge");
    const liveHopBadge = document.getElementById("liveHopBadge");
    const liveScreenshotImg = document.getElementById("liveScreenshotImg");
    const noScreenshotPlaceholder = document.getElementById("noScreenshotPlaceholder");
    const livePageTitle = document.getElementById("livePageTitle");
    const livePageLink = document.getElementById("livePageLink");
    const livePageSnippet = document.getElementById("livePageSnippet");
    const livePathTrail = document.getElementById("livePathTrail");

    // Result Card & Hop Chain
    const resultCard = document.getElementById("resultCard");
    const resultHopBadge = document.getElementById("resultHopBadge");
    const resultMeetingBadge = document.getElementById("resultMeetingBadge");
    const resultTitle = document.getElementById("resultTitle");
    const hopChainWrapper = document.getElementById("hopChainWrapper");
    const resultSummaryText = document.getElementById("resultSummaryText");
    const copyPathBtn = document.getElementById("copyPathBtn");

    // Intermediate Steps Rationale Card
    const intermediateStepsCard = document.getElementById("intermediateStepsCard");
    const intermediateStepsList = document.getElementById("intermediateStepsList");
    const stepsTotalBadge = document.getElementById("stepsTotalBadge");

    // Connecting Link Context Card
    const contextCard = document.getElementById("contextCard");
    const contextBadgeWords = document.getElementById("contextBadgeWords");
    const contextSubTitle = document.getElementById("contextSubTitle");
    const copyContextBtn = document.getElementById("copyContextBtn");
    const contextSourceTitle = document.getElementById("contextSourceTitle");
    const contextTargetTitle = document.getElementById("contextTargetTitle");
    const contextSourceLink = document.getElementById("contextSourceLink");
    const contextBefore = document.getElementById("contextBefore");
    const contextAnchor = document.getElementById("contextAnchor");
    const contextAfter = document.getElementById("contextAfter");
    const wordsBeforeCount = document.getElementById("wordsBeforeCount");
    const wordsAfterCount = document.getElementById("wordsAfterCount");

    // Alert Card
    const alertCard = document.getElementById("alertCard");
    const alertMessage = document.getElementById("alertMessage");

    // Intermediate Pages
    const intermediateSection = document.getElementById("intermediateSection");
    const intermediateCountBadge = document.getElementById("intermediateCountBadge");
    const visitedTableBody = document.getElementById("visitedTableBody");
    const filterInput = document.getElementById("filterInput");

    // Screenshot Modal
    const screenshotModalEl = document.getElementById("screenshotModal");
    const screenshotModal = new bootstrap.Modal(screenshotModalEl);
    const modalScreenshotImg = document.getElementById("modalScreenshotImg");
    const screenshotModalTitle = document.getElementById("screenshotModalTitle");

    // Theme Toggle
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const themeIcon = document.getElementById("themeIcon");

    // Internal State
    let socket = null;
    let timerInterval = null;
    let startTime = null;
    let totalLinksAccumulated = 0;
    let visitedPagesList = [];
    let currentFoundPath = [];
    let currentLinkContext = null;

    // --- Load & Save Settings ---
    function loadSavedSettings() {
        try {
            const raw = localStorage.getItem("wikihop-settings");
            if (raw) {
                const parsed = JSON.parse(raw);
                appSettings = { ...DEFAULT_SETTINGS, ...parsed };
            }
        } catch (e) {
            console.error("Error reading saved settings:", e);
        }
        syncSettingsToUI();
    }

    function saveSettings() {
        appSettings.contextWords = parseInt(modalContextWords.value) || 150;
        appSettings.algorithm = modalAlgorithm.value;
        appSettings.maxPages = parseInt(modalMaxPages.value) || 35;
        appSettings.maxDepth = parseInt(modalMaxDepth.value) || 5;
        appSettings.captureScreenshots = modalScreenshotToggle.checked;
        appSettings.headless = modalHeadlessToggle.checked;

        localStorage.setItem("wikihop-settings", JSON.stringify(appSettings));
        syncSettingsToUI();
    }

    function syncSettingsToUI() {
        // Modal inputs
        modalContextWords.value = appSettings.contextWords;
        modalContextWordsBadge.textContent = `${appSettings.contextWords} words`;
        modalAlgorithm.value = appSettings.algorithm;
        modalMaxPages.value = appSettings.maxPages;
        modalMaxPagesBadge.textContent = appSettings.maxPages;
        modalMaxDepth.value = appSettings.maxDepth;
        modalMaxDepthBadge.textContent = appSettings.maxDepth;
        modalScreenshotToggle.checked = appSettings.captureScreenshots;
        modalHeadlessToggle.checked = appSettings.headless;

        // Summary Badges
        summaryContextBadge.innerHTML = `<i class="bi bi-quote me-1"></i> Context: ${appSettings.contextWords} words`;
        summaryStrategyBadge.innerHTML = `<i class="bi bi-cpu me-1"></i> ${appSettings.algorithm === "heuristic" ? "Bidirectional Smart A*" : "Bidirectional BFS"}`;
        summaryLimitBadge.innerHTML = `<i class="bi bi-speedometer2 me-1"></i> Max ${appSettings.maxPages} Pages`;
    }

    modalContextWords.addEventListener("input", (e) => {
        modalContextWordsBadge.textContent = `${e.target.value} words`;
    });
    modalMaxPages.addEventListener("input", (e) => {
        modalMaxPagesBadge.textContent = e.target.value;
    });
    modalMaxDepth.addEventListener("input", (e) => {
        modalMaxDepthBadge.textContent = e.target.value;
    });

    saveSettingsBtn.addEventListener("click", () => {
        saveSettings();
    });

    resetSettingsBtn.addEventListener("click", () => {
        appSettings = { ...DEFAULT_SETTINGS };
        localStorage.removeItem("wikihop-settings");
        syncSettingsToUI();
    });

    loadSavedSettings();

    // --- Theme Handling ---
    function initTheme() {
        const savedTheme = localStorage.getItem("wikihop-theme") || "dark";
        document.documentElement.setAttribute("data-bs-theme", savedTheme);
        updateThemeIcon(savedTheme);
    }

    function updateThemeIcon(theme) {
        if (theme === "dark") {
            themeIcon.className = "bi bi-sun-fill";
        } else {
            themeIcon.className = "bi bi-moon-fill";
        }
    }

    themeToggleBtn.addEventListener("click", () => {
        const currentTheme = document.documentElement.getAttribute("data-bs-theme");
        const nextTheme = currentTheme === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-bs-theme", nextTheme);
        localStorage.setItem("wikihop-theme", nextTheme);
        updateThemeIcon(nextTheme);
    });

    initTheme();

    // --- Swap Button ---
    swapBtn.addEventListener("click", () => {
        const temp = startInput.value;
        startInput.value = targetInput.value;
        targetInput.value = temp;
    });

    // --- Clear Buttons ---
    document.querySelectorAll(".clear-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const targetId = btn.getAttribute("data-target");
            const input = document.getElementById(targetId);
            if (input) {
                input.value = "";
                input.focus();
            }
        });
    });

    // --- Autocomplete Setup ---
    function setupAutocomplete(inputEl, dropdownEl) {
        let debounceTimer = null;

        inputEl.addEventListener("input", () => {
            clearTimeout(debounceTimer);
            const val = inputEl.value.trim();
            if (val.length < 2) {
                dropdownEl.classList.add("d-none");
                dropdownEl.innerHTML = "";
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(val)}`);
                    const data = await res.json();
                    renderSuggestions(data.results || [], inputEl, dropdownEl);
                } catch (e) {
                    console.error("Autocomplete fetch error:", e);
                }
            }, 250);
        });

        document.addEventListener("click", (e) => {
            if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) {
                dropdownEl.classList.add("d-none");
            }
        });
    }

    function renderSuggestions(results, inputEl, dropdownEl) {
        if (!results.length) {
            dropdownEl.classList.add("d-none");
            dropdownEl.innerHTML = "";
            return;
        }

        dropdownEl.innerHTML = "";
        results.forEach((item) => {
            const a = document.createElement("a");
            a.className = "list-group-item list-group-item-action d-flex flex-column py-2";
            a.href = "#";
            a.innerHTML = `
                <div class="fw-semibold text-body-emphasis">${escapeHtml(item.title)}</div>
                ${item.description ? `<small class="text-secondary text-truncate">${escapeHtml(item.description)}</small>` : ""}
            `;
            a.addEventListener("click", (e) => {
                e.preventDefault();
                inputEl.value = item.title;
                dropdownEl.classList.add("d-none");
            });
            dropdownEl.appendChild(a);
        });
        dropdownEl.classList.remove("d-none");
    }

    setupAutocomplete(startInput, startSuggestions);
    setupAutocomplete(targetInput, targetSuggestions);

    // --- Load Presets ---
    async function loadPresets() {
        try {
            const res = await fetch("/api/presets");
            const data = await res.json();
            presetsContainer.innerHTML = "";
            (data.presets || []).forEach((p) => {
                const chip = document.createElement("span");
                chip.className = "preset-chip text-body-secondary";
                chip.innerHTML = `${escapeHtml(p.start)} &rarr; ${escapeHtml(p.target)}`;
                chip.title = `${p.category}: ${p.description}`;
                chip.addEventListener("click", () => {
                    startInput.value = p.start;
                    targetInput.value = p.target;
                });
                presetsContainer.appendChild(chip);
            });
        } catch (e) {
            console.error("Error loading presets:", e);
        }
    }
    loadPresets();

    // --- Filter Visited Pages ---
    filterInput.addEventListener("input", () => {
        const query = filterInput.value.toLowerCase();
        const rows = visitedTableBody.querySelectorAll("tr");
        rows.forEach((row) => {
            const text = row.innerText.toLowerCase();
            row.style.display = text.includes(query) ? "" : "none";
        });
    });

    // --- Copy Path Button ---
    copyPathBtn.addEventListener("click", () => {
        if (!currentFoundPath.length) return;
        const text = currentFoundPath.join(" ➔ ") + ` (${currentFoundPath.length - 1} hops)`;
        navigator.clipboard.writeText(text).then(() => {
            const orig = copyPathBtn.innerHTML;
            copyPathBtn.innerHTML = `<i class="bi bi-check2 me-1"></i> Copied!`;
            setTimeout(() => (copyPathBtn.innerHTML = orig), 2000);
        });
    });

    // --- Copy Context Button ---
    copyContextBtn.addEventListener("click", () => {
        if (!currentLinkContext) return;
        const ctx = currentLinkContext;
        const textToCopy = `Source Article: ${ctx.source_title} (${ctx.source_url})\nTarget Link: ${ctx.target_title}\n\n"... ${ctx.words_before} [${ctx.anchor_text}] ${ctx.words_after} ..."`;
        navigator.clipboard.writeText(textToCopy).then(() => {
            const orig = copyContextBtn.innerHTML;
            copyContextBtn.innerHTML = `<i class="bi bi-check2 me-1"></i> Copied!`;
            setTimeout(() => (copyContextBtn.innerHTML = orig), 2000);
        });
    });

    // --- Shutdown Server Handler ---
    const shutdownModalEl = document.getElementById("shutdownModal");
    const confirmShutdownBtn = document.getElementById("confirmShutdownBtn");
    const shutdownOverlay = document.getElementById("shutdownOverlay");

    if (confirmShutdownBtn) {
        confirmShutdownBtn.addEventListener("click", async () => {
            confirmShutdownBtn.disabled = true;
            confirmShutdownBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Shutting down...`;

            try {
                const modalInstance = bootstrap.Modal.getInstance(shutdownModalEl);
                if (modalInstance) modalInstance.hide();

                if (socket) {
                    socket.onclose = null;
                    socket.close();
                }

                await fetch("/api/shutdown", { method: "POST" });
            } catch (e) {
                console.log("Shutdown request sent:", e);
            }

            setTimeout(() => {
                if (shutdownOverlay) {
                    shutdownOverlay.classList.remove("d-none");
                }
            }, 300);
        });
    }

    // --- WebSocket Connection ---
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
    connectWebSocket();

    // --- Form Submit: Start Crawl ---
    searchForm.addEventListener("submit", (e) => {
        e.preventDefault();

        const start = startInput.value.trim();
        const target = targetInput.value.trim();

        if (!start || !target) return;

        resetUI();

        const payload = {
            action: "start",
            start: start,
            target: target,
            algorithm: appSettings.algorithm,
            max_pages: appSettings.maxPages,
            max_depth: appSettings.maxDepth,
            capture_screenshots: appSettings.captureScreenshots,
            headless: appSettings.headless,
            context_words: appSettings.contextWords,
        };

        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(payload));
        } else {
            alert("WebSocket is not connected. Please refresh the page.");
        }
    });

    // --- Stop Button ---
    stopBtn.addEventListener("click", () => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action: "stop" }));
        }
        setRunningState(false);
    });

    // --- Handle Incoming Server Messages ---
    function handleServerMessage(data) {
        const eventType = data.event;

        if (eventType === "started") {
            setRunningState(true);
            startTimer();
            const maxPages = data.max_pages || appSettings.maxPages;
            kpiPagesSub.textContent = "0 forward • 0 backward";
            const backlinksCount = data.target_backlinks_count || 0;
            kpiStatusBadge.textContent = backlinksCount > 0 ? `Mapped ${backlinksCount.toLocaleString()} target backlinks` : "Playwright navigating...";
            statsSection.classList.remove("d-none");
            liveInspectorCard.classList.remove("d-none");
            intermediateSection.classList.remove("d-none");

            if (liveDirectionBadge) {
                liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
                liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
            }

        } else if (eventType === "visiting") {
            const page = data.page;
            const totalVisited = data.total_visited;

            visitedPagesList.push(page);
            totalLinksAccumulated += page.links_count || 0;

            const maxPages = appSettings.maxPages;
            const pct = Math.min(Math.round((totalVisited / maxPages) * 100), 98);
            progressBar.style.width = `${pct}%`;

            kpiPagesVisited.textContent = totalVisited;
            const fCount = data.forward_visited_count !== undefined ? data.forward_visited_count : (page.direction === "forward" ? 1 : 0);
            const bCount = data.backward_visited_count !== undefined ? data.backward_visited_count : (page.direction === "backward" ? 1 : 0);
            kpiPagesSub.textContent = `${fCount} forward • ${bCount} backward`;
            kpiCurrentDepth.textContent = page.depth;
            kpiDepthSub.textContent = `Hop level ${page.depth}`;
            kpiLinksCount.textContent = totalLinksAccumulated.toLocaleString();
            kpiLinksSub.textContent = `+${page.links_count} from this page`;

            if (liveDirectionBadge) {
                if (page.direction === "backward") {
                    liveDirectionBadge.className = "badge bg-info-subtle text-info-emphasis border border-info-subtle";
                    liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-left-circle me-1"></i> Backward from Target`;
                } else {
                    liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
                    liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
                }
            }

            liveHopBadge.textContent = `Hop ${page.depth}`;
            livePageTitle.textContent = page.title;
            livePageLink.href = page.url;
            livePageSnippet.textContent = page.snippet || "Playwright loaded page and analyzed internal links.";

            if (page.screenshot) {
                liveScreenshotImg.src = page.screenshot;
                liveScreenshotImg.classList.remove("d-none");
                noScreenshotPlaceholder.classList.add("d-none");
                liveScreenshotImg.onclick = () => openScreenshotModal(page.title, page.screenshot);
            } else {
                liveScreenshotImg.classList.add("d-none");
                noScreenshotPlaceholder.classList.remove("d-none");
            }

            renderLiveTrail(page.path_so_far);
            appendVisitedTableRow(page);
            intermediateCountBadge.textContent = visitedPagesList.length;

        } else if (eventType === "found") {
            stopTimer();
            setRunningState(false);
            progressBar.style.width = "100%";
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-success");
            kpiStatusBadge.textContent = "Path Found!";

            if (data.forward_visited_count !== undefined && data.backward_visited_count !== undefined) {
                kpiPagesSub.textContent = `${data.forward_visited_count} forward • ${data.backward_visited_count} backward`;
            }

            currentFoundPath = data.path;
            currentLinkContext = data.link_context;
            showResultCard(data);

        } else if (eventType === "not_found") {
            stopTimer();
            setRunningState(false);
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-warning");
            kpiStatusBadge.textContent = "Limit reached";
            showAlert(data.message || "Reached maximum search limit without finding target link.");

        } else if (eventType === "cancelled") {
            stopTimer();
            setRunningState(false);
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-secondary");
            kpiStatusBadge.textContent = "Crawl stopped";
            showAlert(data.message || "Search stopped by user.");

        } else if (eventType === "error") {
            stopTimer();
            setRunningState(false);
            progressBar.classList.remove("progress-bar-animated");
            progressBar.classList.add("bg-danger");
            kpiStatusBadge.textContent = "Error";
            showAlert(data.message || "An error occurred during crawling.");
        }
    }

    // --- Show Result Card & Context ---
    function showResultCard(data) {
        resultCard.classList.remove("d-none");
        resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

        const hops = data.hops;
        resultHopBadge.textContent = `${hops} Hop${hops === 1 ? "" : "s"} Required`;
        resultHopBadge.className = `badge ${hops <= 2 ? "bg-success" : "bg-primary"} fs-6 px-3 py-1 rounded-pill`;

        if (resultMeetingBadge) {
            const hasMeetingBridge = (data.intermediate_steps || []).some(s => s.badge && (s.badge.includes("Meeting") || s.badge.includes("Bridge")));
            if (hasMeetingBridge || (data.found_on_page && data.found_on_page !== data.path[data.path.length - 1] && data.found_on_page !== data.path[0])) {
                resultMeetingBadge.classList.remove("d-none");
                resultMeetingBadge.innerHTML = `<i class="bi bi-intersect me-1"></i> Frontiers Met at "${escapeHtml(data.found_on_page || 'Intersection')}"`;
            } else {
                resultMeetingBadge.classList.add("d-none");
            }
        }

        const startTitle = data.path[0];
        const targetTitle = data.path[data.path.length - 1];
        resultTitle.innerHTML = `${escapeHtml(startTitle)} &rarr; ${escapeHtml(targetTitle)}`;

        resultSummaryText.innerHTML = `
            <strong>Target reached!</strong> Playwright inspected <strong>${data.total_visited}</strong> intermediate pages 
            (${data.forward_visited_count || 0} forward + ${data.backward_visited_count || 0} backward)
            and connected <strong>${escapeHtml(startTitle)}</strong> to <strong>${escapeHtml(targetTitle)}</strong> in exactly <strong>${hops}</strong> link hop${hops === 1 ? "" : "s"}.
        `;

        // Render Visual Hop Chain
        hopChainWrapper.innerHTML = "";
        data.path.forEach((title, index) => {
            const isStart = index === 0;
            const isTarget = index === data.path.length - 1;
            const url = data.urls ? data.urls[index] : `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`;

            const node = document.createElement("div");
            node.className = `hop-node ${isStart ? "start-node" : isTarget ? "target-node" : "intermediate-node"}`;
            
            let icon = isStart ? '<i class="bi bi-geo-alt-fill"></i>' : isTarget ? '<i class="bi bi-flag-fill"></i>' : '<i class="bi bi-link-45deg"></i>';
            let label = isStart ? "Start" : isTarget ? `Target (${index} hops)` : `Hop ${index}`;

            node.innerHTML = `
                ${icon}
                <div class="d-flex flex-column text-start">
                    <span style="font-size: 0.72rem; text-transform: uppercase; opacity: 0.85;">${label}</span>
                    <a href="${url}" target="_blank" class="text-reset text-decoration-none fw-bold">${escapeHtml(title)}</a>
                </div>
            `;
            hopChainWrapper.appendChild(node);

            if (index < data.path.length - 1) {
                const arrow = document.createElement("div");
                arrow.className = "hop-arrow";
                arrow.innerHTML = `<i class="bi bi-chevron-right"></i>`;
                hopChainWrapper.appendChild(arrow);
            }
        });

        // Render Intermediate Links Used & Algorithmic Rationale
        renderIntermediateSteps(data.intermediate_steps);

        // Render Context Section (150 words before and after)
        const ctx = data.link_context;
        if (ctx && (ctx.words_before || ctx.words_after || ctx.anchor_text)) {
            contextCard.classList.remove("d-none");
            contextBadgeWords.textContent = `${ctx.requested_words || 150} words before & after`;
            contextSourceTitle.textContent = ctx.source_title;
            contextTargetTitle.textContent = ctx.target_title;
            contextSourceLink.href = ctx.source_url;
            
            contextBefore.textContent = ctx.words_before ? `... ${ctx.words_before}` : "(Start of page section)";
            contextAnchor.textContent = ctx.anchor_text || ctx.target_title;
            contextAfter.textContent = ctx.words_after ? `${ctx.words_after} ...` : "(End of page section)";
            
            wordsBeforeCount.textContent = ctx.before_count || 0;
            wordsAfterCount.textContent = ctx.after_count || 0;
        } else {
            contextCard.classList.add("d-none");
        }
    }

    // --- Render Intermediate Links Used & Algorithmic Rationale ---
    function renderIntermediateSteps(steps) {
        if (!intermediateStepsList || !intermediateStepsCard) return;
        intermediateStepsList.innerHTML = "";

        if (!steps || steps.length === 0) {
            intermediateStepsCard.classList.add("d-none");
            return;
        }

        intermediateStepsCard.classList.remove("d-none");
        stepsTotalBadge.textContent = `${steps.length} Hop Link${steps.length === 1 ? "" : "s"} Traversed`;

        steps.forEach((step, idx) => {
            const card = document.createElement("div");
            let borderClass = "";
            if (step.badge && (step.badge.includes("Meeting") || step.badge.includes("Bridge"))) {
                borderClass = "step-meeting";
            } else if (step.badge && step.badge.includes("Target")) {
                borderClass = "step-target";
            } else if (step.is_feeder) {
                borderClass = "step-feeder";
            } else if (step.badge && step.badge.includes("Hub")) {
                borderClass = "step-hub";
            }

            card.className = `card border rounded-3 p-3 shadow-sm step-card ${borderClass}`;

            const scoreVal = typeof step.score === "number" ? step.score : parseFloat(step.score);
            let scoreBadgeClass = "bg-body-secondary text-secondary border";
            if (!isNaN(scoreVal)) {
                if (scoreVal > 0) scoreBadgeClass = "bg-success-subtle text-success-emphasis border border-success-subtle";
                else if (scoreVal < 0) scoreBadgeClass = "bg-danger-subtle text-danger-emphasis border border-danger-subtle";
            }

            const formattedScore = typeof step.score === "number" 
                ? `${step.score > 0 ? "+" : ""}${step.score.toLocaleString()}` 
                : step.score;

            // Context snippet: 15 words before and 15 words after
            let contextSnippetHtml = "";
            const hasBefore = Boolean(step.words_before && step.words_before.trim());
            const hasAfter = Boolean(step.words_after && step.words_after.trim());
            const anchorText = step.anchor_text || step.to_title;

            if (hasBefore || hasAfter || anchorText) {
                const beforePart = hasBefore ? `... ${escapeHtml(step.words_before)}` : "(Section start)";
                const afterPart = hasAfter ? `${escapeHtml(step.words_after)} ...` : "(Section end)";
                contextSnippetHtml = `
                    <div class="step-context-box p-2.5 rounded-2 bg-body-tertiary border small mb-2">
                        <div class="d-flex align-items-center justify-content-between text-muted mb-1" style="font-size: 0.76rem;">
                            <span>
                                <i class="bi bi-quote text-success me-1"></i>
                                In-page context on <strong>${escapeHtml(step.from_title)}</strong>:
                            </span>
                            <span class="badge bg-secondary-subtle text-secondary border font-monospace" style="font-size: 0.7rem;">
                                15 words before &amp; after
                            </span>
                        </div>
                        <div class="step-context-text text-body">
                            <span class="text-secondary">${beforePart}</span>
                            <mark class="step-anchor-highlight px-2 py-0.5 mx-1 rounded">${escapeHtml(anchorText)}</mark>
                            <span class="text-secondary">${afterPart}</span>
                        </div>
                    </div>
                `;
            }

            let reasonsHtml = "";
            if (step.reasons && step.reasons.length > 0) {
                const pills = step.reasons.map(r => {
                    const isPenalty = r.includes("(-") || r.includes("Penalized") || r.includes("penalty");
                    const isBonus = r.includes("(+") || r.includes("Match") || r.includes("overlap");
                    const icon = isPenalty 
                        ? `<i class="bi bi-dash-circle text-danger me-1"></i>`
                        : isBonus
                        ? `<i class="bi bi-plus-circle text-success me-1"></i>`
                        : `<i class="bi bi-info-circle text-info me-1"></i>`;
                    const badgeClass = isPenalty
                        ? "bg-danger-subtle text-danger-emphasis border-danger-subtle"
                        : isBonus
                        ? "bg-success-subtle text-success-emphasis border-success-subtle"
                        : "bg-body-secondary text-secondary-emphasis border";
                    return `
                        <span class="badge ${badgeClass} border fw-normal py-1 px-2">
                            ${icon}${escapeHtml(r)}
                        </span>
                    `;
                }).join("");
                reasonsHtml = `
                    <div class="mt-2 pt-2 border-top">
                        <div class="text-secondary small fw-semibold mb-1">
                            <i class="bi bi-sliders2 text-primary me-1"></i>Score Breakdown &amp; Factors:
                        </div>
                        <div class="d-flex flex-wrap gap-1">
                            ${pills}
                        </div>
                    </div>
                `;
            }

            card.innerHTML = `
                <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 pb-2 mb-2 border-bottom">
                    <div class="d-flex align-items-center flex-wrap gap-2">
                        <span class="badge bg-primary px-2.5 py-1 rounded-pill fw-bold">
                            Hop ${step.hop || (idx + 1)}
                        </span>
                        <div class="d-flex align-items-center flex-wrap gap-1 fs-6">
                            <a href="${step.from_url || '#'}" target="_blank" class="text-body-emphasis text-decoration-none fw-semibold">
                                ${escapeHtml(step.from_title)}
                            </a>
                            <i class="bi bi-arrow-right text-primary mx-1"></i>
                            <a href="${step.to_url || '#'}" target="_blank" class="text-primary text-decoration-none fw-bold">
                                ${escapeHtml(step.to_title)}
                            </a>
                        </div>
                    </div>
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge ${step.badge_class || 'bg-secondary text-white'}">${escapeHtml(step.badge || 'Candidate Link')}</span>
                        <span class="badge ${scoreBadgeClass} font-monospace">Score: ${formattedScore}</span>
                    </div>
                </div>

                <div class="p-2.5 rounded-2 step-explanation-box mb-2">
                    <div class="small text-body-secondary">
                        <i class="bi bi-cpu-fill text-primary me-1"></i>
                        <strong class="text-body-emphasis">Why this link was chosen:</strong>
                        ${escapeHtml(step.explanation || "Selected based on graph traversal priority.")}
                    </div>
                </div>

                ${contextSnippetHtml}

                ${reasonsHtml}
            `;

            intermediateStepsList.appendChild(card);
        });
    }

    // --- Render Live Path Trail ---
    function renderLiveTrail(pathArray) {
        if (!pathArray || !pathArray.length) {
            livePathTrail.innerHTML = `<span class="text-muted">Root</span>`;
            return;
        }
        livePathTrail.innerHTML = "";
        pathArray.forEach((item, idx) => {
            const span = document.createElement("span");
            span.className = "badge bg-body border text-body-emphasis";
            span.textContent = item;
            livePathTrail.appendChild(span);

            if (idx < pathArray.length - 1) {
                const sep = document.createElement("span");
                sep.className = "text-muted";
                sep.innerHTML = "&rarr;";
                livePathTrail.appendChild(sep);
            }
        });
    }

    // --- Visited Table Row ---
    function appendVisitedTableRow(page) {
        const tr = document.createElement("tr");

        let thumbHtml = '<span class="text-muted small">None</span>';
        if (page.screenshot) {
            thumbHtml = `<img src="${page.screenshot}" class="table-thumb" alt="thumbnail" title="Click to view full screenshot">`;
        }

        const isForward = page.direction !== "backward";
        const dirBadge = isForward
            ? `<span class="badge bg-primary-subtle text-primary border border-primary-subtle"><i class="bi bi-arrow-right me-1"></i>Forward</span>`
            : `<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle"><i class="bi bi-arrow-left me-1"></i>Backward</span>`;

        const feederBadge = page.is_feeder ? '<span class="badge text-bg-warning me-1" title="Direct feeder: links directly to target!"><i class="bi bi-star-fill me-1"></i>Direct Feeder</span>' : '';

        tr.innerHTML = `
            <td class="fw-bold text-secondary">#${page.step}</td>
            <td>${thumbHtml}</td>
            <td>${dirBadge}</td>
            <td>
                <div class="fw-semibold d-flex align-items-center flex-wrap gap-1">
                    ${feederBadge}
                    <a href="${page.url}" target="_blank" class="text-body-emphasis text-decoration-none">
                        ${escapeHtml(page.title)} <i class="bi bi-box-arrow-up-right text-muted small ms-1"></i>
                    </a>
                </div>
            </td>
            <td>
                <span class="badge ${page.depth === 0 ? "text-bg-success" : page.depth === 1 ? "text-bg-info" : "text-bg-secondary"}">
                    Hop ${page.depth}
                </span>
            </td>
            <td>
                <span class="fw-semibold font-monospace">${page.links_count.toLocaleString()}</span> links
            </td>
            <td>
                <small class="text-secondary d-inline-block text-truncate" style="max-width: 320px;" title="${escapeHtml(page.snippet)}">
                    ${escapeHtml(page.snippet || "—")}
                </small>
            </td>
        `;

        if (page.screenshot) {
            const imgEl = tr.querySelector(".table-thumb");
            if (imgEl) {
                imgEl.addEventListener("click", () => openScreenshotModal(page.title, page.screenshot));
            }
        }

        visitedTableBody.appendChild(tr);
    }

    // --- Screenshot Modal ---
    function openScreenshotModal(title, base64Src) {
        screenshotModalTitle.textContent = `Playwright Capture: ${title}`;
        modalScreenshotImg.src = base64Src;
        screenshotModal.show();
    }

    // --- Alerts ---
    function showAlert(msg) {
        alertMessage.textContent = msg;
        alertCard.classList.remove("d-none");
    }

    // --- State UI Control ---
    function setRunningState(isRunning) {
        if (isRunning) {
            startBtn.classList.add("d-none");
            stopBtn.classList.remove("d-none");
            startInput.disabled = true;
            targetInput.disabled = true;
            swapBtn.disabled = true;
        } else {
            startBtn.classList.remove("d-none");
            stopBtn.classList.add("d-none");
            startInput.disabled = false;
            targetInput.disabled = false;
            swapBtn.disabled = false;
        }
    }

    function resetUI() {
        visitedPagesList = [];
        totalLinksAccumulated = 0;
        currentFoundPath = [];
        currentLinkContext = null;

        progressBar.style.width = "0%";
        progressBar.className = "progress-bar progress-bar-striped progress-bar-animated bg-primary";

        kpiPagesVisited.textContent = "0";
        kpiCurrentDepth.textContent = "0";
        kpiLinksCount.textContent = "0";
        kpiElapsedTime.textContent = "0.0s";
        kpiStatusBadge.textContent = "Initializing...";

        resultCard.classList.add("d-none");
        if (resultMeetingBadge) resultMeetingBadge.classList.add("d-none");
        if (liveDirectionBadge) {
            liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
            liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
        }
        if (intermediateStepsCard) intermediateStepsCard.classList.add("d-none");
        if (intermediateStepsList) intermediateStepsList.innerHTML = "";
        contextCard.classList.add("d-none");
        alertCard.classList.add("d-none");
        visitedTableBody.innerHTML = "";
        intermediateCountBadge.textContent = "0";

        livePageTitle.textContent = "Launching Playwright...";
        livePageSnippet.textContent = "Opening Chromium browser instance...";
        liveScreenshotImg.classList.add("d-none");
        noScreenshotPlaceholder.classList.remove("d-none");
    }

    // --- Timer ---
    function startTimer() {
        clearInterval(timerInterval);
        startTime = Date.now();
        timerInterval = setInterval(() => {
            const elapsed = (Date.now() - startTime) / 1000;
            kpiElapsedTime.textContent = `${elapsed.toFixed(1)}s`;
        }, 100);
    }

    function stopTimer() {
        clearInterval(timerInterval);
    }

    // --- Helper: Escape HTML ---
    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});
