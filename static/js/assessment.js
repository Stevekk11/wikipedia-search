/**
 * Article Quality Assessment & WikiProject Utilities
 */

import { escapeHtml } from "./math.js";

export function getAssessmentData(title, assessments) {
    if (!assessments || !title) return null;
    return assessments[title] ||
           assessments[title.replace(/ /g, "_")] ||
           assessments[title.toLowerCase()] ||
           assessments[title.toLowerCase().replace(/ /g, "_")] ||
           null;
}

export function renderAssessmentBadgeHtml(assessment) {
    if (!assessment || !assessment.class || assessment.class === "Unassessed") {
        return `
            <span class="badge rounded-pill assessment-badge badge-unassessed" title="Assessment: Unassessed or pending evaluation">
                <i class="bi bi-question-circle-fill me-1"></i>Unassessed
            </span>
        `;
    }
    const badgeClass = assessment.badge_class || "badge-unassessed";
    const icon = assessment.icon || "bi-patch-check-fill";
    const cls = assessment.class || "Unassessed";
    const fullName = assessment.class_name || `${cls} Class`;
    return `
        <span class="badge rounded-pill assessment-badge ${badgeClass}" title="Quality Assessment: ${escapeHtml(fullName)}">
            <i class="bi ${icon} me-1"></i>${escapeHtml(cls)}
        </span>
    `;
}

export function renderWikiProjectHtml(assessment) {
    if (!assessment || !assessment.has_wikiproject || !assessment.primary_project) {
        return "";
    }
    const primary = assessment.primary_project;
    const impText = primary.importance ? ` (${escapeHtml(primary.importance)} Importance)` : "";
    const allProjects = assessment.all_projects || [];
    const extraCount = allProjects.length - 1;

    let moreBadgeHtml = "";
    if (extraCount > 0) {
        const remainingProjects = allProjects.slice(1).join(", ");
        moreBadgeHtml = `
            <span class="badge wikiproject-more-badge" title="Additional WikiProjects: ${escapeHtml(remainingProjects)}">
                +${extraCount} more
            </span>
        `;
    }

    return `
        <div class="d-flex flex-wrap align-items-center gap-1 mt-1 w-100">
            <span class="badge wikiproject-pill text-truncate" title="WikiProject ${escapeHtml(primary.name)}${impText}">
                <i class="bi bi-diagram-2-fill me-1"></i>WikiProject ${escapeHtml(primary.name)}
            </span>
            ${moreBadgeHtml}
        </div>
    `;
}

export async function fetchAssessmentsForPath(titles, lang = "en") {
    if (!titles || !titles.length) return null;
    try {
        const res = await fetch(`/api/article-assessments?titles=${encodeURIComponent(titles.join(","))}&lang=${encodeURIComponent(lang)}`);
        if (res.ok) {
            return await res.json();
        }
    } catch (e) {
        console.warn("Failed to fetch assessments:", e);
    }
    return null;
}
