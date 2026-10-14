/**
 * UI Controls, Form Management, Live Dashboard & Results Rendering
 */

import { escapeHtml, renderMathInContainer, formatTextWithMath } from "./math.js";
import { getAssessmentData, renderAssessmentBadgeHtml, renderWikiProjectHtml } from "./assessment.js";
import { appSettings } from "./settings.js";
import { renderPathCarousel } from "./carousel.js";

let timerInterval = null;
let startTime = null;
const screenshotModalEl = document.getElementById("screenshotModal");
const screenshotModal = screenshotModalEl && typeof bootstrap !== "undefined" ? new bootstrap.Modal(screenshotModalEl) : null;

export function setupAutocomplete(inputEl, dropdownEl) {
    if (!inputEl || !dropdownEl) return;
    let debounceTimer = null;
    let controller = null;
    let requestSeq = 0;

    async function fetchSuggestions() {
        clearTimeout(debounceTimer);
        const val = inputEl.value.trim();
        if (controller) controller.abort();
        const seq = ++requestSeq;
        if (val.length < 2) {
            dropdownEl.classList.add("d-none");
            dropdownEl.innerHTML = "";
            return;
        }
        controller = new AbortController();
        try {
            const langCode = appSettings.lang || "en";
            const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(val)}&lang=${encodeURIComponent(langCode)}`, { signal: controller.signal });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (seq !== requestSeq || inputEl.value.trim() !== val) return;
            renderSuggestions(data.results || [], inputEl, dropdownEl);
        } catch (e) {
            if (e.name !== "AbortError") console.error("Autocomplete fetch error:", e);
        }
    }

    inputEl.addEventListener("input", (e) => {
        clearTimeout(debounceTimer);
        if (e && e.isTrusted === false) {
            requestSeq++;
            if (controller) controller.abort();
            dropdownEl.classList.add("d-none");
            return;
        }
        debounceTimer = setTimeout(fetchSuggestions, 200);
    });

    inputEl.addEventListener("focus", () => {
        if (dropdownEl.children.length) dropdownEl.classList.remove("d-none");
    });

    document.addEventListener("click", (e) => {
        if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) {
            dropdownEl.classList.add("d-none");
        }
    });
}

export function renderSuggestions(results, inputEl, dropdownEl) {
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

export async function loadPresets() {
    const presetsContainer = document.getElementById("presetsContainer");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");
    const viaInput = document.getElementById("viaInput");
    if (!presetsContainer) return;

    try {
        const langCode = appSettings.lang || "en";
        const res = await fetch(`/api/presets?lang=${encodeURIComponent(langCode)}`);
        const data = await res.json();
        presetsContainer.innerHTML = "";
        const presets = data.presets || [];
        presets.forEach((p) => {
            const chip = document.createElement("span");
            chip.className = "preset-chip text-body-secondary";
            chip.innerHTML = `${escapeHtml(p.start)} &rarr; ${escapeHtml(p.target)}`;
            chip.title = `${p.category}: ${p.description}`;
            chip.addEventListener("click", () => {
                if (startInput) startInput.value = p.start;
                if (viaInput) viaInput.value = "";
                if (targetInput) targetInput.value = p.target;
            });
            presetsContainer.appendChild(chip);
        });

        if (presets.length > 0 && startInput && targetInput) {
            const currentStart = startInput.value.trim();
            const currentTarget = targetInput.value.trim();
            if (!currentStart || currentStart === "London" || currentStart === "Berlin" || currentStart === "Paris" || currentStart === "Madrid" || currentStart === "Roma" || currentStart === "東京" || currentStart === "Москва") {
                startInput.value = presets[0].start;
                startInput.placeholder = `e.g. ${presets[0].start}`;
            }
            if (!currentTarget || currentTarget === "New York City" || currentTarget === "Wien" || currentTarget === "Montréal" || currentTarget === "Buenos Aires" || currentTarget === "Parigi" || currentTarget === "京都" || currentTarget === "Санкт-Петербург") {
                targetInput.value = presets[0].target;
                targetInput.placeholder = `e.g. ${presets[0].target}`;
            }
        }
    } catch (e) {
        console.error("Error loading presets:", e);
    }
}

export function setupRandomButton() {
    const randomBtn = document.getElementById("randomBtn");
    const startBtn = document.getElementById("startBtn");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");
    const viaInput = document.getElementById("viaInput");
    const startSuggestions = document.getElementById("startSuggestions");
    const targetSuggestions = document.getElementById("targetSuggestions");

    if (!randomBtn) return;

    randomBtn.addEventListener("click", async () => {
        const randLang = (appSettings.lang || "en").toLowerCase();

        const origHtml = randomBtn.innerHTML;
        randomBtn.disabled = true;
        randomBtn.classList.add("disabled", "opacity-75");
        randomBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Randomizing...`;

        if (startSuggestions) startSuggestions.classList.add("d-none");
        if (targetSuggestions) targetSuggestions.classList.add("d-none");
        if (viaInput) viaInput.value = "";

        try {
            const res = await fetch(`/api/random?lang=${encodeURIComponent(randLang)}`);
            if (!res.ok) {
                throw new Error(`Server returned status ${res.status}`);
            }
            const data = await res.json();
            if (data.start && data.target) {
                if (startInput) startInput.value = data.start;
                if (targetInput) targetInput.value = data.target;

                if (startInput) startInput.dispatchEvent(new Event("input", { bubbles: true }));
                if (targetInput) targetInput.dispatchEvent(new Event("input", { bubbles: true }));
            } else {
                throw new Error(data.error || "Invalid response format");
            }
        } catch (err) {
            console.error("Error fetching random articles:", err);
            showAlert(`Failed to select random articles from ${randLang}.wikipedia.org. Please try again.`);
        } finally {
            const isRunning = startBtn && startBtn.classList.contains("d-none");
            randomBtn.innerHTML = origHtml;
            if (!isRunning) {
                randomBtn.disabled = false;
                randomBtn.classList.remove("disabled", "opacity-75", "opacity-50");
            } else {
                randomBtn.disabled = true;
                randomBtn.classList.add("disabled", "opacity-50");
                randomBtn.classList.remove("opacity-75");
            }
        }
    });
}

export function setupFormButtons() {
    const swapBtn = document.getElementById("swapBtn");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");

    if (swapBtn && startInput && targetInput) {
        swapBtn.addEventListener("click", () => {
            const temp = startInput.value;
            startInput.value = targetInput.value;
            targetInput.value = temp;
        });
    }

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
}

export function setupVisitedFilter() {
    const filterInput = document.getElementById("filterInput");
    const visitedTableBody = document.getElementById("visitedTableBody");
    if (!filterInput || !visitedTableBody) return;

    filterInput.addEventListener("input", () => {
        const query = filterInput.value.toLowerCase();
        const rows = visitedTableBody.querySelectorAll("tr");
        rows.forEach((row) => {
            const text = row.innerText.toLowerCase();
            row.style.display = text.includes(query) ? "" : "none";
        });
    });
}

export function setupCopyButtons(getFoundPath, getLinkContext) {
    const copyPathBtn = document.getElementById("copyPathBtn");
    const copyContextBtn = document.getElementById("copyContextBtn");

    if (copyPathBtn) {
        copyPathBtn.addEventListener("click", () => {
            const path = typeof getFoundPath === "function" ? getFoundPath() : [];
            if (!path.length) return;
            const text = path.join(" ➔ ") + ` (${path.length - 1} hops)`;
            navigator.clipboard.writeText(text).then(() => {
                const orig = copyPathBtn.innerHTML;
                copyPathBtn.innerHTML = `<i class="bi bi-check2 me-1"></i> Copied!`;
                setTimeout(() => (copyPathBtn.innerHTML = orig), 2000);
            });
        });
    }

    if (copyContextBtn) {
        copyContextBtn.addEventListener("click", () => {
            const ctx = typeof getLinkContext === "function" ? getLinkContext() : null;
            if (!ctx) return;
            const sourceTitle = ctx.source_title || (ctx.source_slug ? ctx.source_slug.replace(/_/g, " ") : "Source Article");
            const textToCopy = `Source Article: ${sourceTitle} (${ctx.source_url})\nTarget Link: ${ctx.target_title}\n\n"... ${ctx.words_before} [${ctx.anchor_text}] ${ctx.words_after} ..."`;
            navigator.clipboard.writeText(textToCopy).then(() => {
                const orig = copyContextBtn.innerHTML;
                copyContextBtn.innerHTML = `<i class="bi bi-check2 me-1"></i> Copied!`;
                setTimeout(() => (copyContextBtn.innerHTML = orig), 2000);
            });
        });
    }
}

export function setupShutdown(onShutdown) {
    const shutdownModalEl = document.getElementById("shutdownModal");
    const confirmShutdownBtn = document.getElementById("confirmShutdownBtn");
    const shutdownOverlay = document.getElementById("shutdownOverlay");

    if (confirmShutdownBtn) {
        confirmShutdownBtn.addEventListener("click", async () => {
            confirmShutdownBtn.disabled = true;
            confirmShutdownBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Shutting down...`;

            try {
                if (shutdownModalEl && typeof bootstrap !== "undefined") {
                    const modalInstance = bootstrap.Modal.getInstance(shutdownModalEl);
                    if (modalInstance) modalInstance.hide();
                }

                if (typeof onShutdown === "function") {
                    onShutdown();
                }

                await fetch("/api/shutdown", { method: "POST" });
            } catch (e) {
                console.log("Shutdown request sent:", e);
            }

            if (shutdownOverlay) {
                shutdownOverlay.classList.remove("d-none");
            }
        });
    }
}

export function showResultCard(data, visitedPagesList = [], onPersistCarousel = null) {
    const resultCard = document.getElementById("resultCard");
    const resultHopBadge = document.getElementById("resultHopBadge");
    const resultMeetingBadge = document.getElementById("resultMeetingBadge");
    const resultTitle = document.getElementById("resultTitle");
    const resultSummaryText = document.getElementById("resultSummaryText");
    const hopChainWrapper = document.getElementById("hopChainWrapper");
    const hopChainContainer = document.getElementById("hopChainContainer");
    const contextCard = document.getElementById("contextCard");
    const contextBadgeWords = document.getElementById("contextBadgeWords");
    const contextSourceTitle = document.getElementById("contextSourceTitle");
    const contextTargetTitle = document.getElementById("contextTargetTitle");
    const contextSourceLink = document.getElementById("contextSourceLink");
    const contextBefore = document.getElementById("contextBefore");
    const contextAnchor = document.getElementById("contextAnchor");
    const contextAfter = document.getElementById("contextAfter");
    const wordsBeforeCount = document.getElementById("wordsBeforeCount");
    const wordsAfterCount = document.getElementById("wordsAfterCount");

    if (!resultCard) return;
    resultCard.classList.remove("d-none");
    resultCard.scrollIntoView({ behavior: "smooth", block: "nearest" });

    const hops = data.hops;
    if (resultHopBadge) {
        resultHopBadge.textContent = `${hops} Hop${hops === 1 ? "" : "s"} Required`;
        resultHopBadge.className = `badge ${hops <= 2 ? "bg-success" : "bg-primary"} fs-6 px-3 py-1 rounded-pill`;
    }

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
    if (resultTitle) {
        resultTitle.innerHTML = `${escapeHtml(startTitle)} &rarr; ${escapeHtml(targetTitle)}`;
    }

    if (resultSummaryText) {
        resultSummaryText.innerHTML = `
            <strong>Target reached!</strong> Playwright inspected <strong>${data.total_visited}</strong> intermediate pages 
            (${data.forward_visited_count || 0} forward + ${data.backward_visited_count || 0} backward)
            and connected <strong>${escapeHtml(startTitle)}</strong> to <strong>${escapeHtml(targetTitle)}</strong> in exactly <strong>${hops}</strong> link hop${hops === 1 ? "" : "s"}.
        `;
    }

    if (hopChainWrapper) {
        hopChainWrapper.innerHTML = "";
        if (hopChainContainer) {
            hopChainContainer.classList.remove("in-view");
        }
        const langCode = appSettings.lang || "en";
        data.path.forEach((title, index) => {
            const isStart = index === 0;
            const isTarget = index === data.path.length - 1;
            const url = data.urls ? data.urls[index] : `https://${langCode}.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`;

            const node = document.createElement("div");
            node.className = `hop-node ${isStart ? "start-node" : isTarget ? "target-node" : "intermediate-node"}`;
            node.style.setProperty("--node-idx", index);
            
            let icon = isStart ? '<i class="bi bi-geo-alt-fill"></i>' : isTarget ? '<i class="bi bi-flag-fill"></i>' : '<i class="bi bi-link-45deg"></i>';
            const isVia = !isStart && !isTarget && data.via_index === index;
            let label = isStart ? "Start" : isTarget ? `Target (${index} hops)` : isVia ? `Via · Hop ${index}` : `Hop ${index}`;
            if (isVia) node.classList.add("border", "border-warning");

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
                arrow.style.setProperty("--arrow-idx", index);
                arrow.innerHTML = `<i class="bi bi-chevron-right"></i>`;
                hopChainWrapper.appendChild(arrow);
            }
        });
    }

    triggerHopChainAnimation();
    renderIntermediateSteps(data.intermediate_steps, data.assessments);
    renderPathCarousel(data.path, data.via_index, visitedPagesList, openScreenshotModal, appSettings, onPersistCarousel);

    const ctx = data.link_context;
    if (ctx && (ctx.words_before || ctx.words_after || ctx.anchor_text) && contextCard) {
        contextCard.classList.remove("d-none");
        if (contextBadgeWords) contextBadgeWords.textContent = `${ctx.requested_words || 150} words before & after`;
        if (contextSourceTitle) contextSourceTitle.textContent = ctx.source_title || (ctx.source_slug ? ctx.source_slug.replace(/_/g, " ") : "Source Article");
        if (contextTargetTitle) contextTargetTitle.textContent = ctx.target_title;
        if (contextSourceLink) contextSourceLink.href = ctx.source_url;
        
        if (contextBefore) contextBefore.innerHTML = ctx.words_before ? `... ${formatTextWithMath(ctx.words_before)}` : "(Start of page section)";
        if (contextAnchor) contextAnchor.innerHTML = formatTextWithMath(ctx.anchor_text || ctx.target_title);
        if (contextAfter) contextAfter.innerHTML = ctx.words_after ? `${formatTextWithMath(ctx.words_after)} ...` : "(End of page section)";
        renderMathInContainer(contextCard);
        
        if (wordsBeforeCount) wordsBeforeCount.textContent = ctx.before_count || 0;
        if (wordsAfterCount) wordsAfterCount.textContent = ctx.after_count || 0;
    } else if (contextCard) {
        contextCard.classList.add("d-none");
    }
}

export function triggerHopChainAnimation() {
    const hopChainContainer = document.getElementById("hopChainContainer");
    if (!hopChainContainer) return;
    hopChainContainer.classList.remove("in-view");
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (!hopChainContainer) return;
            const rect = hopChainContainer.getBoundingClientRect();
            const inViewport = rect.top < window.innerHeight && rect.bottom > 0;
            if (inViewport) {
                hopChainContainer.classList.add("in-view");
            }
        });
    });
}

export function initHopChainObserver() {
    const hopChainContainer = document.getElementById("hopChainContainer");
    if (hopChainContainer && window.IntersectionObserver) {
        const hopChainObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    hopChainContainer.classList.add("in-view");
                }
            });
        }, {
            threshold: 0.15,
            rootMargin: "0px 0px -30px 0px"
        });
        hopChainObserver.observe(hopChainContainer);
    }
}

export function renderIntermediateSteps(steps, assessments = null) {
    const intermediateStepsList = document.getElementById("intermediateStepsList");
    const intermediateStepsCard = document.getElementById("intermediateStepsCard");
    const stepsTotalBadge = document.getElementById("stepsTotalBadge");

    if (!intermediateStepsList || !intermediateStepsCard) return;
    intermediateStepsList.innerHTML = "";

    if (!steps || steps.length === 0) {
        intermediateStepsCard.classList.add("d-none");
        return;
    }

    intermediateStepsCard.classList.remove("d-none");
    if (stepsTotalBadge) {
        stepsTotalBadge.textContent = `${steps.length} Hop Link${steps.length === 1 ? "" : "s"} Traversed`;
    }

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

        let contextSnippetHtml = "";
        const hasBefore = Boolean(step.words_before && step.words_before.trim());
        const hasAfter = Boolean(step.words_after && step.words_after.trim());
        const anchorText = step.anchor_text || step.to_title;
        const isBacklinksPlaceholder = !step.section || step.section === "Backlinks / Incoming";
        const sectionText = isBacklinksPlaceholder ? "" : step.section;

        if (hasBefore || hasAfter) {
            const beforePart = hasBefore ? `... ${formatTextWithMath(step.words_before)}` : "(Section start)";
            const afterPart = hasAfter ? `${formatTextWithMath(step.words_after)} ...` : "(Section end)";
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
                        <mark class="step-anchor-highlight px-2 py-0.5 mx-1 rounded">${formatTextWithMath(anchorText)}</mark>
                        <span class="text-secondary">${afterPart}</span>
                    </div>
                </div>
            `;
        } else if (step.is_feeder || isBacklinksPlaceholder) {
            contextSnippetHtml = `
                <div class="p-2.5 rounded-2 bg-body-tertiary border small text-muted mb-2 d-flex align-items-center gap-2">
                    <i class="bi bi-diagram-3 text-info"></i>
                    <span>Discovered via Wikipedia incoming backlinks graph to <strong>${escapeHtml(step.to_title)}</strong>.</span>
                </div>
            `;
        }

        let sectionHtml = "";
        if (!isBacklinksPlaceholder && sectionText) {
            sectionHtml = `
                <div class="mb-2 d-flex align-items-center flex-wrap gap-1 small">
                    <span class="text-body-secondary fw-semibold">
                        <i class="bi bi-bookmark-fill text-warning me-1"></i>Found under section / subtitle:
                    </span>
                    <span class="badge bg-dark-subtle text-dark-emphasis border border-secondary-subtle px-2 py-1">
                        ${escapeHtml(sectionText)}
                    </span>
                </div>
            `;
        } else {
            sectionHtml = `
                <div class="mb-2 d-flex align-items-center flex-wrap gap-1 small">
                    <span class="text-body-secondary fw-semibold">
                        <i class="bi bi-diagram-3-fill text-info me-1"></i>Link Source:
                    </span>
                    <span class="badge bg-info-subtle text-info-emphasis border border-info-subtle px-2 py-1">
                        Wikipedia Incoming Backlinks Graph
                    </span>
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

        let badgesHtml = "";
        if (Array.isArray(step.badges) && step.badges.length > 0) {
            badgesHtml = step.badges.map(b => {
                const text = typeof b === "string" ? b : b.text || "";
                const bClass = (typeof b === "object" && b.class) ? b.class : "bg-secondary text-white";
                return `<span class="badge fs-6 px-2.5 py-1 ${bClass}">${escapeHtml(text)}</span>`;
            }).join(" ");
        } else {
            badgesHtml = `<span class="badge fs-6 px-2.5 py-1 ${step.badge_class || 'bg-secondary text-white'}">${escapeHtml(step.badge || 'Candidate Link')}</span>`;
        }

        const fromAssessment = getAssessmentData(step.from_title, assessments);
        const toAssessment = getAssessmentData(step.to_title, assessments);
        const fromBadge = fromAssessment ? renderAssessmentBadgeHtml(fromAssessment) : "";
        const toBadge = toAssessment ? renderAssessmentBadgeHtml(toAssessment) : "";
        const fromWikiProject = fromAssessment ? renderWikiProjectHtml(fromAssessment) : "";
        const toWikiProject = toAssessment ? renderWikiProjectHtml(toAssessment) : "";

        let assessmentBoxHtml = "";
        if (fromAssessment || toAssessment) {
            assessmentBoxHtml = `
                <div class="p-3 rounded-3 bg-body-tertiary border mb-3">
                    <div class="row g-3 align-items-center">
                        <div class="col-md-6 d-flex flex-column gap-1.5">
                            <div class="d-flex align-items-center flex-wrap gap-2">
                                <span class="text-secondary fw-semibold">
                                    <i class="bi bi-file-earmark-text text-primary me-1"></i>${escapeHtml(step.from_title)}:
                                </span>
                                ${fromBadge}
                            </div>
                            ${fromWikiProject}
                        </div>
                        <div class="col-md-6 d-flex flex-column gap-1.5">
                            <div class="d-flex align-items-center flex-wrap gap-2">
                                <span class="text-secondary fw-semibold">
                                    <i class="bi bi-link-45deg text-success me-1"></i>${escapeHtml(step.to_title)}:
                                </span>
                                ${toBadge}
                            </div>
                            ${toWikiProject}
                        </div>
                    </div>
                </div>
            `;
        }

        card.innerHTML = `
            <div class="d-flex flex-wrap align-items-center justify-content-between gap-3 pb-3 mb-3 border-bottom">
                <div class="d-flex align-items-center flex-wrap gap-2.5">
                    <span class="badge bg-primary m-2 px-3 py-1.5 rounded-pill fw-bold fs-6">
                        Hop ${step.hop || (idx + 1)}
                    </span>
                    <div class="d-flex align-items-center flex-wrap gap-2 fs-5">
                        <a href="${step.from_url || '#'}" target="_blank" class="text-body-emphasis text-decoration-none fw-semibold">
                            ${escapeHtml(step.from_title)}
                        </a>
                        <i class="bi bi-arrow-right text-primary mx-1"></i>
                        <a href="${step.to_url || '#'}" target="_blank" class="text-primary text-decoration-none fw-bold">
                            ${escapeHtml(step.to_title)}
                        </a>
                    </div>
                </div>
                <div class="d-flex align-items-center flex-wrap gap-2">
                    ${badgesHtml}
                    <span class="badge ${scoreBadgeClass} font-monospace fs-6 px-3 py-1.5">Score: ${formattedScore}</span>
                </div>
            </div>

            ${assessmentBoxHtml}

            <div class="p-3 rounded-3 step-explanation-box mb-3">
                <div class="text-body-secondary">
                    <i class="bi bi-cpu-fill text-primary me-1"></i>
                    <strong class="text-body-emphasis">Why this link was chosen:</strong>
                    ${formatTextWithMath(step.explanation || "Selected based on graph traversal priority.")}
                </div>
            </div>

            ${sectionHtml}
            ${contextSnippetHtml}
            ${reasonsHtml}
        `;

        renderMathInContainer(card);
        intermediateStepsList.appendChild(card);
    });
}

export function renderLiveTrail(pathArray) {
    const livePathTrail = document.getElementById("livePathTrail");
    if (!livePathTrail) return;
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

export function appendVisitedTableRow(page) {
    const visitedTableBody = document.getElementById("visitedTableBody");
    if (!visitedTableBody) return;

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
            <span class="fw-semibold font-monospace">${(page.links_count || 0).toLocaleString()}</span> <span class="text-secondary small ms-1">${(page.links_type === "incoming_backlinks" || page.direction === "backward") ? "backlinks" : "outgoing"}</span>
        </td>
    `;

    renderMathInContainer(tr);

    if (page.screenshot) {
        const imgEl = tr.querySelector(".table-thumb");
        if (imgEl) {
            imgEl.addEventListener("click", () => openScreenshotModal(page.title, page.screenshot));
        }
    }

    visitedTableBody.appendChild(tr);
}

export function openScreenshotModal(title, base64Src) {
    const screenshotModalTitle = document.getElementById("screenshotModalTitle");
    const modalScreenshotImg = document.getElementById("modalScreenshotImg");
    if (screenshotModalTitle) screenshotModalTitle.textContent = `Playwright Capture: ${title}`;
    if (modalScreenshotImg) modalScreenshotImg.src = base64Src;
    if (screenshotModal) screenshotModal.show();
}

export function showAlert(msg) {
    const alertMessage = document.getElementById("alertMessage");
    const alertCard = document.getElementById("alertCard");
    if (alertMessage) alertMessage.textContent = msg;
    if (alertCard) alertCard.classList.remove("d-none");
}

export function setRunningState(isRunning) {
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const randomBtn = document.getElementById("randomBtn");
    const startInput = document.getElementById("startInput");
    const targetInput = document.getElementById("targetInput");
    const viaInput = document.getElementById("viaInput");
    const swapBtn = document.getElementById("swapBtn");

    if (isRunning) {
        if (startBtn) startBtn.classList.add("d-none");
        if (stopBtn) stopBtn.classList.remove("d-none");
        if (randomBtn) {
            randomBtn.disabled = true;
            randomBtn.classList.add("disabled", "opacity-50");
        }
        if (startInput) startInput.disabled = true;
        if (targetInput) targetInput.disabled = true;
        if (viaInput) viaInput.disabled = true;
        if (swapBtn) swapBtn.disabled = true;
    } else {
        if (startBtn) startBtn.classList.remove("d-none");
        if (stopBtn) stopBtn.classList.add("d-none");
        if (randomBtn) {
            randomBtn.disabled = false;
            randomBtn.classList.remove("disabled", "opacity-50");
            randomBtn.title = `Select two random articles (${(appSettings.lang || "en").toLowerCase()}.wikipedia.org)`;
        }
        if (startInput) startInput.disabled = false;
        if (targetInput) targetInput.disabled = false;
        if (viaInput) viaInput.disabled = false;
        if (swapBtn) swapBtn.disabled = false;
    }
}

export function resetUI() {
    const progressBar = document.getElementById("progressBar");
    const kpiPagesVisited = document.getElementById("kpiPagesVisited");
    const kpiCurrentDepth = document.getElementById("kpiCurrentDepth");
    const kpiLinksCount = document.getElementById("kpiLinksCount");
    const kpiElapsedTime = document.getElementById("kpiElapsedTime");
    const kpiStatusBadge = document.getElementById("kpiStatusBadge");

    const resultCard = document.getElementById("resultCard");
    const pathCarouselCard = document.getElementById("pathCarouselCard");
    const resultMeetingBadge = document.getElementById("resultMeetingBadge");
    const liveDirectionBadge = document.getElementById("liveDirectionBadge");
    const intermediateStepsCard = document.getElementById("intermediateStepsCard");
    const intermediateStepsList = document.getElementById("intermediateStepsList");
    const contextCard = document.getElementById("contextCard");
    const alertCard = document.getElementById("alertCard");
    const pageStatsGraphSection = document.getElementById("pageStatsGraphSection");
    const statsNavbarBadge = document.getElementById("statsNavbarBadge");
    const visitedTableBody = document.getElementById("visitedTableBody");
    const intermediateCountBadge = document.getElementById("intermediateCountBadge");

    const livePageTitle = document.getElementById("livePageTitle");
    const livePageSnippet = document.getElementById("livePageSnippet");
    const liveScreenshotImg = document.getElementById("liveScreenshotImg");
    const noScreenshotPlaceholder = document.getElementById("noScreenshotPlaceholder");

    if (progressBar) {
        progressBar.style.width = "0%";
        progressBar.className = "progress-bar progress-bar-striped progress-bar-animated bg-primary";
    }

    if (kpiPagesVisited) kpiPagesVisited.textContent = "0";
    if (kpiCurrentDepth) kpiCurrentDepth.textContent = "0";
    if (kpiLinksCount) kpiLinksCount.textContent = "0";
    if (kpiElapsedTime) kpiElapsedTime.textContent = "0.0s";
    if (kpiStatusBadge) kpiStatusBadge.textContent = "Initializing...";

    if (resultCard) resultCard.classList.add("d-none");
    if (pathCarouselCard) pathCarouselCard.classList.add("d-none");
    if (resultMeetingBadge) resultMeetingBadge.classList.add("d-none");
    if (liveDirectionBadge) {
        liveDirectionBadge.className = "badge bg-primary-subtle text-primary border border-primary-subtle";
        liveDirectionBadge.innerHTML = `<i class="bi bi-arrow-right-circle me-1"></i> Forward from Start`;
    }
    if (intermediateStepsCard) intermediateStepsCard.classList.add("d-none");
    if (intermediateStepsList) intermediateStepsList.innerHTML = "";
    if (contextCard) contextCard.classList.add("d-none");
    if (alertCard) alertCard.classList.add("d-none");

    if (pageStatsGraphSection && typeof bootstrap !== "undefined") {
        try {
            const offcanvasInstance = bootstrap.Offcanvas.getInstance(pageStatsGraphSection);
            if (offcanvasInstance) offcanvasInstance.hide();
        } catch (e) {}
    }

    if (statsNavbarBadge) {
        statsNavbarBadge.textContent = "0";
        statsNavbarBadge.classList.add("d-none");
    }
    if (visitedTableBody) visitedTableBody.innerHTML = "";
    if (intermediateCountBadge) intermediateCountBadge.textContent = "0";

    if (livePageTitle) livePageTitle.textContent = "Launching Playwright...";
    if (livePageSnippet) livePageSnippet.textContent = "Opening Chromium browser instance...";
    if (liveScreenshotImg) liveScreenshotImg.classList.add("d-none");
    if (noScreenshotPlaceholder) noScreenshotPlaceholder.classList.remove("d-none");
}

export function startTimer() {
    clearInterval(timerInterval);
    startTime = Date.now();
    const kpiElapsedTime = document.getElementById("kpiElapsedTime");
    timerInterval = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000;
        if (kpiElapsedTime) kpiElapsedTime.textContent = `${elapsed.toFixed(1)}s`;
    }, 100);
}

export function stopTimer() {
    clearInterval(timerInterval);
}
