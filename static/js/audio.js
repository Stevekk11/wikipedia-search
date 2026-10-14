/**
 * Graph Audio Synthesizer (Web Audio API Pop Sounds)
 */

const STORAGE_KEY_GRAPH_SOUND = "wikihop-graph-sound";
let isGraphSoundEnabled = true;
try {
    const storedSoundPref = localStorage.getItem(STORAGE_KEY_GRAPH_SOUND);
    if (storedSoundPref !== null) {
        isGraphSoundEnabled = storedSoundPref === "true";
    }
} catch (_) {}

let graphAudioCtx = null;
let lastGraphPopTime = 0;

export function getGraphAudioContext() {
    if (!graphAudioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
            graphAudioCtx = new AudioContextClass();
        }
    }
    if (graphAudioCtx && graphAudioCtx.state === "suspended") {
        graphAudioCtx.resume().catch(() => {});
    }
    return graphAudioCtx;
}

export function unlockAudioOnInteraction() {
    getGraphAudioContext();
}

export function updateGraphSoundButtonUI() {
    const graphSoundToggleBtn = document.getElementById("graphSoundToggleBtn");
    const graphSoundIcon = document.getElementById("graphSoundIcon");
    if (!graphSoundToggleBtn) return;
    if (isGraphSoundEnabled) {
        if (graphSoundIcon) graphSoundIcon.className = "bi bi-volume-up-fill";
        graphSoundToggleBtn.classList.add("text-primary");
        graphSoundToggleBtn.title = "Graph Pop Sounds Enabled (Click to Mute)";
    } else {
        if (graphSoundIcon) graphSoundIcon.className = "bi bi-volume-mute-fill";
        graphSoundToggleBtn.classList.remove("text-primary");
        graphSoundToggleBtn.title = "Graph Pop Sounds Muted (Click to Enable)";
    }
}

export function toggleGraphSound() {
    isGraphSoundEnabled = !isGraphSoundEnabled;
    try {
        localStorage.setItem(STORAGE_KEY_GRAPH_SOUND, String(isGraphSoundEnabled));
    } catch (_) {}
    updateGraphSoundButtonUI();
}

/**
 * Synthesizes and plays a clean, satisfying bubble/cork "pop" sound
 * exclusively for autonomous graph actions (node spawns, additions, path emergence, bridges).
 * @param {string} action - 'node' | 'spawn' | 'path-node' | 'bridge'
 * @param {object} [options] - pitch, volume, index, total, direction
 */
export function playGraphPop(action = "node", options = {}) {
    if (!isGraphSoundEnabled) return;
    try {
        const ctx = getGraphAudioContext();
        if (!ctx) return;
        if (ctx.state === "suspended") {
            ctx.resume().catch(() => {});
        }

        const now = ctx.currentTime;
        // Throttle rapid successive node additions to prevent audio clutter
        if (action === "node" && (now - lastGraphPopTime < 0.035)) {
            return;
        }
        lastGraphPopTime = now;

        let startFreq = 800;
        let endFreq = 160;
        let duration = 0.055;
        let volume = 0.22;

        if (action === "spawn") {
            startFreq = 840;
            endFreq = 180;
            duration = 0.06;
            volume = 0.20;
        } else if (action === "node") {
            const rand = (Math.random() - 0.5) * 80;
            const dirMultiplier = options.direction === "backward" ? 1.15 : 1.0;
            startFreq = (780 + rand) * dirMultiplier;
            endFreq = (160 + rand * 0.2) * dirMultiplier;
            duration = 0.05;
            volume = 0.18;
        } else if (action === "path-node") {
            const idx = options.index || 0;
            const semitoneRatio = Math.pow(2, (idx % 12) / 12);
            startFreq = 650 * semitoneRatio;
            endFreq = 180 * Math.min(2.0, semitoneRatio);
            duration = 0.07;
            volume = 0.26;
        } else if (action === "bridge") {
            startFreq = 950;
            endFreq = 220;
            duration = 0.065;
            volume = 0.22;
        }

        if (options.pitch) {
            startFreq *= options.pitch;
            endFreq *= options.pitch;
        }
        if (options.volume !== undefined) {
            volume = options.volume;
        }

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(startFreq * 0.75, now);
        osc.frequency.linearRampToValueAtTime(startFreq, now + 0.003);
        osc.frequency.exponentialRampToValueAtTime(Math.max(25, endFreq), now + duration);

        gain.gain.setValueAtTime(0.0001, now);
        gain.gain.linearRampToValueAtTime(volume, now + 0.002);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now);
        osc.stop(now + duration);
    } catch (_) {}
}

export function setupAudioControls() {
    document.addEventListener("pointerdown", unlockAudioOnInteraction, { passive: true });
    document.addEventListener("keydown", unlockAudioOnInteraction, { passive: true });
    const graphSoundToggleBtn = document.getElementById("graphSoundToggleBtn");
    if (graphSoundToggleBtn) {
        graphSoundToggleBtn.addEventListener("click", toggleGraphSound);
        updateGraphSoundButtonUI();
    }
}
