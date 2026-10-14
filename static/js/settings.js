/**
 * Settings & Language Edition Configuration Module
 */

export const DEFAULT_SETTINGS = {
    lang: "en",
    contextWords: 150,
    algorithm: "heuristic",
    maxPages: 35,
    maxDepth: 5,
    captureScreenshots: true,
    adaptiveBalancing: true,
    headless: true,
};

export const LANG_NAMES = {
    en: { name: "English", flag: "🇬🇧", label: "EN (English)" },
    de: { name: "Deutsch", flag: "🇩🇪", label: "DE (Deutsch)" },
    fr: { name: "Français", flag: "🇫🇷", label: "FR (Français)" },
    es: { name: "Español", flag: "🇪🇸", label: "ES (Español)" },
    it: { name: "Italiano", flag: "🇮🇹", label: "IT (Italiano)" },
    ja: { name: "日本語", flag: "🇯🇵", label: "JA (日本語)" },
    ru: { name: "Русский", flag: "🇷🇺", label: "RU (Русский)" },
    zh: { name: "中文", flag: "🇨🇳", label: "ZH (中文)" },
    pt: { name: "Português", flag: "🇵🇹", label: "PT (Português)" },
    nl: { name: "Nederlands", flag: "🇳🇱", label: "NL (Nederlands)" },
    pl: { name: "Polski", flag: "🇵🇱", label: "PL (Polski)" },
};

export let appSettings = { ...DEFAULT_SETTINGS };

let onLanguageChangeCallback = null;
let onSettingsSaveCallback = null;

export function loadSavedSettings() {
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

export function saveSettings() {
    const modalLanguage = document.getElementById("modalLanguage");
    const modalContextWords = document.getElementById("modalContextWords");
    const modalAlgorithm = document.getElementById("modalAlgorithm");
    const modalMaxPages = document.getElementById("modalMaxPages");
    const modalMaxDepth = document.getElementById("modalMaxDepth");
    const modalScreenshotToggle = document.getElementById("modalScreenshotToggle");
    const modalBalancingToggle = document.getElementById("modalBalancingToggle");
    const modalHeadlessToggle = document.getElementById("modalHeadlessToggle");

    appSettings.lang = (modalLanguage ? modalLanguage.value : appSettings.lang) || "en";
    if (modalContextWords) appSettings.contextWords = parseInt(modalContextWords.value) || 150;
    if (modalAlgorithm) appSettings.algorithm = modalAlgorithm.value;
    if (modalMaxPages) appSettings.maxPages = parseInt(modalMaxPages.value) || 35;
    if (modalMaxDepth) appSettings.maxDepth = parseInt(modalMaxDepth.value) || 5;
    if (modalScreenshotToggle) appSettings.captureScreenshots = modalScreenshotToggle.checked;
    if (modalBalancingToggle) appSettings.adaptiveBalancing = modalBalancingToggle.checked;
    if (modalHeadlessToggle) appSettings.headless = modalHeadlessToggle.checked;

    localStorage.setItem("wikihop-settings", JSON.stringify(appSettings));
    syncSettingsToUI();
    if (typeof onSettingsSaveCallback === "function") {
        onSettingsSaveCallback(appSettings);
    }
}

export function setLanguage(newLang) {
    if (!newLang) return;
    newLang = newLang.toLowerCase().trim();
    appSettings.lang = newLang;
    localStorage.setItem("wikihop-settings", JSON.stringify(appSettings));
    syncSettingsToUI();

    document.querySelectorAll(".lang-option").forEach((opt) => {
        if (opt.getAttribute("data-lang") === newLang) {
            opt.classList.add("active");
        } else {
            opt.classList.remove("active");
        }
    });

    if (typeof onLanguageChangeCallback === "function") {
        onLanguageChangeCallback(newLang);
    }
}

export function syncSettingsToUI() {
    const langCode = appSettings.lang || "en";
    const langMeta = LANG_NAMES[langCode] || { name: langCode.toUpperCase(), flag: "🌐", label: `${langCode.toUpperCase()} (${langCode}.wikipedia.org)` };

    const currentLanguageLabel = document.getElementById("currentLanguageLabel");
    if (currentLanguageLabel) {
        currentLanguageLabel.innerHTML = `${langMeta.flag} ${langCode.toUpperCase()} (${langMeta.name})`;
    }

    const summaryLanguageBadge = document.getElementById("summaryLanguageBadge");
    if (summaryLanguageBadge) {
        summaryLanguageBadge.innerHTML = `<i class="bi bi-globe2 me-1"></i> Edition: ${langCode}.wikipedia.org`;
    }

    const modalLanguage = document.getElementById("modalLanguage");
    if (modalLanguage) {
        modalLanguage.value = langCode;
        if (!modalLanguage.value) {
            let customOpt = modalLanguage.querySelector(`option[value="${langCode}"]`);
            if (!customOpt) {
                customOpt = document.createElement("option");
                customOpt.value = langCode;
                customOpt.textContent = `🌐 ${langCode} (${langCode}.wikipedia.org)`;
                modalLanguage.appendChild(customOpt);
            }
            modalLanguage.value = langCode;
        }
    }

    const modalContextWords = document.getElementById("modalContextWords");
    const modalContextWordsBadge = document.getElementById("modalContextWordsBadge");
    if (modalContextWords && modalContextWordsBadge) {
        modalContextWords.value = appSettings.contextWords;
        modalContextWordsBadge.textContent = `${appSettings.contextWords} words`;
    }

    const modalAlgorithm = document.getElementById("modalAlgorithm");
    if (modalAlgorithm) modalAlgorithm.value = appSettings.algorithm;

    const modalMaxPages = document.getElementById("modalMaxPages");
    const modalMaxPagesBadge = document.getElementById("modalMaxPagesBadge");
    if (modalMaxPages && modalMaxPagesBadge) {
        modalMaxPages.value = appSettings.maxPages;
        modalMaxPagesBadge.textContent = appSettings.maxPages;
    }

    const modalMaxDepth = document.getElementById("modalMaxDepth");
    const modalMaxDepthBadge = document.getElementById("modalMaxDepthBadge");
    if (modalMaxDepth && modalMaxDepthBadge) {
        modalMaxDepth.value = appSettings.maxDepth;
        modalMaxDepthBadge.textContent = appSettings.maxDepth;
    }

    const modalScreenshotToggle = document.getElementById("modalScreenshotToggle");
    if (modalScreenshotToggle) modalScreenshotToggle.checked = appSettings.captureScreenshots;

    const modalBalancingToggle = document.getElementById("modalBalancingToggle");
    if (modalBalancingToggle) modalBalancingToggle.checked = appSettings.adaptiveBalancing !== false;

    const modalHeadlessToggle = document.getElementById("modalHeadlessToggle");
    if (modalHeadlessToggle) modalHeadlessToggle.checked = appSettings.headless;

    const summaryContextBadge = document.getElementById("summaryContextBadge");
    if (summaryContextBadge) {
        summaryContextBadge.innerHTML = `<i class="bi bi-quote me-1"></i> Context: ${appSettings.contextWords} words`;
    }

    const summaryStrategyBadge = document.getElementById("summaryStrategyBadge");
    if (summaryStrategyBadge) {
        summaryStrategyBadge.innerHTML = `<i class="bi bi-cpu me-1"></i> ${appSettings.algorithm === "heuristic" ? "Bidirectional Smart A*" : "Bidirectional BFS"}`;
    }

    const summaryLimitBadge = document.getElementById("summaryLimitBadge");
    if (summaryLimitBadge) {
        summaryLimitBadge.innerHTML = `<i class="bi bi-speedometer2 me-1"></i> Max ${appSettings.maxPages} Pages`;
    }

    const toggleBadges = [
        ["summaryScreenshotsBadge", "bi-camera", "Screenshots", appSettings.captureScreenshots],
        ["summaryBalancingBadge", "bi-sliders2", "Adaptive Balancing", appSettings.adaptiveBalancing !== false],
        ["summaryHeadlessBadge", "bi-window", "Headless", !!appSettings.headless],
    ];
    toggleBadges.forEach(([id, icon, label, on]) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = `badge ${on ? "text-bg-success" : "text-bg-secondary"}`;
        el.innerHTML = `<i class="bi ${icon} me-1"></i> ${label}: ${on ? "On" : "Off"}`;
    });

    const randomBtn = document.getElementById("randomBtn");
    const startBtn = document.getElementById("startBtn");
    if (randomBtn) {
        const isRunning = startBtn && startBtn.classList.contains("d-none");
        randomBtn.title = `Select two random articles (${langCode}.wikipedia.org)`;
        if (!isRunning) {
            randomBtn.disabled = false;
            randomBtn.classList.remove("disabled", "opacity-50");
        }
    }
}

export function setupSettingsEvents(callbacks = {}) {
    onLanguageChangeCallback = callbacks.onLanguageChange;
    onSettingsSaveCallback = callbacks.onSettingsSave;

    document.querySelectorAll(".lang-option").forEach((opt) => {
        opt.addEventListener("click", (e) => {
            e.preventDefault();
            const chosen = opt.getAttribute("data-lang");
            if (chosen === "custom") {
                const customCode = prompt("Enter ISO 639-1 language code for Wikipedia (e.g., 'sv', 'ko', 'ar', 'uk', 'he'):", "en");
                if (customCode && customCode.trim()) {
                    setLanguage(customCode.trim().toLowerCase());
                }
            } else {
                setLanguage(chosen);
            }
        });
    });

    const modalLanguage = document.getElementById("modalLanguage");
    if (modalLanguage) {
        modalLanguage.addEventListener("change", (e) => {
            setLanguage(e.target.value);
        });
    }

    const modalContextWords = document.getElementById("modalContextWords");
    const modalContextWordsBadge = document.getElementById("modalContextWordsBadge");
    if (modalContextWords && modalContextWordsBadge) {
        modalContextWords.addEventListener("input", (e) => {
            modalContextWordsBadge.textContent = `${e.target.value} words`;
        });
    }

    const modalMaxPages = document.getElementById("modalMaxPages");
    const modalMaxPagesBadge = document.getElementById("modalMaxPagesBadge");
    if (modalMaxPages && modalMaxPagesBadge) {
        modalMaxPages.addEventListener("input", (e) => {
            modalMaxPagesBadge.textContent = e.target.value;
        });
    }

    const modalMaxDepth = document.getElementById("modalMaxDepth");
    const modalMaxDepthBadge = document.getElementById("modalMaxDepthBadge");
    if (modalMaxDepth && modalMaxDepthBadge) {
        modalMaxDepth.addEventListener("input", (e) => {
            modalMaxDepthBadge.textContent = e.target.value;
        });
    }

    const saveSettingsBtn = document.getElementById("saveSettingsBtn");
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener("click", () => {
            saveSettings();
        });
    }

    const resetSettingsBtn = document.getElementById("resetSettingsBtn");
    if (resetSettingsBtn) {
        resetSettingsBtn.addEventListener("click", () => {
            appSettings = { ...DEFAULT_SETTINGS };
            localStorage.removeItem("wikihop-settings");
            syncSettingsToUI();
            if (typeof onSettingsSaveCallback === "function") {
                onSettingsSaveCallback(appSettings);
            }
        });
    }

    loadSavedSettings();
}
