/**
 * Final Path Screenshot Carousel Module
 */

import { escapeHtml } from "./math.js";

export let pathScreenshotCache = {};
let pathCarouselToken = 0;

export function setPathScreenshotCache(newCache) {
    pathScreenshotCache = { ...(newCache || {}) };
}

export function renderPathCarousel(path, viaIndex, visitedPagesList = [], openScreenshotModal = null, appSettings = {}, onPersist = null) {
    const card = document.getElementById("pathCarouselCard");
    const track = document.getElementById("pathCarouselTrack");
    const countBadge = document.getElementById("pathCarouselCount");
    if (!card || !track) return;
    track.innerHTML = "";

    const norm = (t) => (t || "").replace(/_/g, " ").trim().toLowerCase();
    const shots = {};
    (visitedPagesList || []).forEach(p => {
        const key = norm(p.title);
        if (p.screenshot && !shots[key]) shots[key] = p;
    });

    // Screenshots regenerated earlier for this path (persisted in history)
    const extra = pathScreenshotCache;
    const items = (path || []).map((title, index) => {
        const page = shots[norm(title)] || (extra[norm(title)] ? { screenshot: extra[norm(title)] } : null);
        return { title, index, page };
    });
    if (!items.length) {
        card.classList.add("d-none");
        return;
    }

    const slides = [];
    items.forEach(({ title, index, page }) => {
        const last = index === path.length - 1;
        const label = index === 0 ? "Start" : last ? "Target" : (viaIndex === index ? `Via · Hop ${index}` : `Hop ${index}`);
        const el = document.createElement("div");
        el.className = "path-carousel-item";
        const fillImage = (shot) => {
            el.querySelector(".path-carousel-empty, img")?.remove();
            const img = document.createElement("img");
            img.src = shot;
            img.alt = `Screenshot of ${title}`;
            if (typeof openScreenshotModal === "function") {
                img.addEventListener("click", () => openScreenshotModal(title, shot));
            }
            el.prepend(img);
        };
        if (page) {
            fillImage(page.screenshot);
        } else {
            el.insertAdjacentHTML("beforeend", `<div class="path-carousel-empty"><span class="spinner-border text-secondary" role="status"></span></div>`);
            slides.push({ title, el, fillImage });
        }
        el.insertAdjacentHTML("beforeend", `
            <div class="path-carousel-caption">
                <div class="text-secondary text-uppercase" style="font-size: 0.7rem;">${label}</div>
                <div class="fw-semibold text-truncate" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
            </div>`);
        track.appendChild(el);
    });

    if (countBadge) countBadge.textContent = items.length;
    card.classList.remove("d-none");
    track.scrollLeft = 0;

    // Re-create any missing screenshots one at a time
    const token = ++pathCarouselToken;
    const lang = appSettings.lang || "en";
    (async () => {
        for (const s of slides) {
            if (token !== pathCarouselToken) return; // a newer render superseded this one
            try {
                const res = await fetch(`/api/screenshot?lang=${encodeURIComponent(lang)}&title=${encodeURIComponent(s.title)}`);
                if (!res.ok) throw new Error(`status ${res.status}`);
                const data = await res.json();
                if (!data.screenshot) throw new Error("empty screenshot");
                pathScreenshotCache[norm(s.title)] = data.screenshot;
                s.fillImage(data.screenshot);
                if (typeof onPersist === "function") {
                    onPersist(pathScreenshotCache);
                }
            } catch (err) {
                console.warn("Could not re-create screenshot for", s.title, err);
                const placeholder = s.el.querySelector(".path-carousel-empty");
                if (placeholder) {
                    placeholder.innerHTML = `<i class="bi bi-image fs-1" title="Screenshot unavailable"></i>`;
                }
            }
        }
    })();
}

export function initPathCarouselControls() {
    const track = document.getElementById("pathCarouselTrack");
    const prev = document.getElementById("pathCarouselPrev");
    const next = document.getElementById("pathCarouselNext");
    if (!track || !prev || !next) return;
    const step = () => Math.max(track.clientWidth * 0.8, 200);
    prev.addEventListener("click", () => track.scrollBy({ left: -step(), behavior: "smooth" }));
    next.addEventListener("click", () => track.scrollBy({ left: step(), behavior: "smooth" }));
    track.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft") { e.preventDefault(); prev.click(); }
        if (e.key === "ArrowRight") { e.preventDefault(); next.click(); }
    });
}
