/**
 * Theme Handling Module (Dark / Light mode)
 */

export function initTheme() {
    const savedTheme = localStorage.getItem("wikihop-theme") || "dark";
    document.documentElement.setAttribute("data-bs-theme", savedTheme);
    updateThemeIcon(savedTheme);
    return savedTheme;
}

export function updateThemeIcon(theme) {
    const themeIcon = document.getElementById("themeIcon");
    if (!themeIcon) return;
    if (theme === "dark") {
        themeIcon.className = "bi bi-sun-fill";
    } else {
        themeIcon.className = "bi bi-moon-fill";
    }
}

export function setupThemeToggle(onThemeChange) {
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    if (!themeToggleBtn) return;

    themeToggleBtn.addEventListener("click", () => {
        const currentTheme = document.documentElement.getAttribute("data-bs-theme");
        const nextTheme = currentTheme === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-bs-theme", nextTheme);
        localStorage.setItem("wikihop-theme", nextTheme);
        updateThemeIcon(nextTheme);
        if (typeof onThemeChange === "function") {
            onThemeChange(nextTheme);
        }
    });
}
