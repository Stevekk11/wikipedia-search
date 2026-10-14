/**
 * Math & LaTeX Rendering Helpers (KaTeX & HTML Escaping)
 */

export function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function renderMathInContainer(container) {
    if (!container) return;
    if (typeof renderMathInElement === "function") {
        try {
            renderMathInElement(container, {
                delimiters: [
                    { left: "$$", right: "$$", display: true },
                    { left: "\\[", right: "\\]", display: true },
                    { left: "$", right: "$", display: false },
                    { left: "\\(", right: "\\)", display: false }
                ],
                throwOnError: false,
                ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"]
            });
        } catch (err) {
            console.debug("KaTeX auto-render error:", err);
        }
    }
}

export function formatTextWithMath(text) {
    if (!text) return "";
    const escaped = escapeHtml(text);
    if (typeof katex === "undefined") {
        return escaped;
    }

    // Match LaTeX math blocks: $$, \[, \], $, \(, \)
    const mathRegex = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\(.+?\\\)|\$(?:\\.|[^$\\\n])+\$)/g;
    return escaped.replace(mathRegex, (match) => {
        let displayMode = false;
        let mathExpr = "";

        if (match.startsWith("$$") && match.endsWith("$$")) {
            displayMode = true;
            mathExpr = match.slice(2, -2);
        } else if (match.startsWith("\\[") && match.endsWith("\\]")) {
            displayMode = true;
            mathExpr = match.slice(2, -2);
        } else if (match.startsWith("\\(") && match.endsWith("\\)")) {
            displayMode = false;
            mathExpr = match.slice(2, -2);
        } else if (match.startsWith("$") && match.endsWith("$")) {
            displayMode = false;
            mathExpr = match.slice(1, -1);
        } else {
            return match;
        }

        mathExpr = mathExpr
            .replace(/&amp;/g, "&")
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">")
            .replace(/&quot;/g, '"')
            .replace(/&#039;/g, "'");

        try {
            return katex.renderToString(mathExpr, {
                displayMode: displayMode,
                throwOnError: false
            });
        } catch (err) {
            return match;
        }
    });
}
