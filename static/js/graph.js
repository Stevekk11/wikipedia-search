/**
 * Force-Directed Graph Visualizer (D3.js)
 */

import { escapeHtml } from "./math.js";
import { playGraphPop, toggleGraphSound, updateGraphSoundButtonUI } from "./audio.js";
import { appSettings } from "./settings.js";

export let graphData = { nodes: [], links: [] };
let graphNodesMap = new Map(); // id -> node
let graphLinksSet = new Set(); // source|target -> link
export let graphSimulation = null;
let graphSvg = null;
let graphZoom = null;
let graphContainerGroup = null;
let graphFinalPathSet = new Set();
let graphStartId = null;
let graphTargetId = null;
let graphViaId = null;
let graphPathEmergenceTimers = [];
let graphSnippetCache = new Map(); // id -> snippet
let currentTooltipNodeId = null;

export function clearGraphPathTimers() {
    if (graphPathEmergenceTimers && graphPathEmergenceTimers.length) {
        graphPathEmergenceTimers.forEach(t => clearTimeout(t));
        graphPathEmergenceTimers = [];
    }
}

export function initForceGraph() {
    const forceGraphSvg = document.getElementById("forceGraphSvg");
    if (!forceGraphSvg || typeof d3 === "undefined") return;

    d3.select(forceGraphSvg).selectAll("*").remove();

    const svg = d3.select(forceGraphSvg);
    graphSvg = svg;

    // Define arrowhead markers
    const defs = svg.append("defs");
    defs.append("marker")
        .attr("id", "arrow-forward")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 22)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-4L9,0L0,4")
        .attr("fill", "rgba(59, 130, 246, 0.6)");

    defs.append("marker")
        .attr("id", "arrow-backward")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 22)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-4L9,0L0,4")
        .attr("fill", "rgba(6, 182, 212, 0.6)");

    defs.append("marker")
        .attr("id", "arrow-via")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 24)
        .attr("refY", 0)
        .attr("markerWidth", 7)
        .attr("markerHeight", 7)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-4L9,0L0,4")
        .attr("fill", "rgba(168, 85, 247, 0.8)");

    defs.append("marker")
        .attr("id", "arrow-path")
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 24)
        .attr("refY", 0)
        .attr("markerWidth", 8)
        .attr("markerHeight", 8)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "#eab308");

    graphContainerGroup = svg.append("g").attr("class", "graph-zoom-layer");
    graphContainerGroup.append("g").attr("class", "links-layer");
    graphContainerGroup.append("g").attr("class", "nodes-layer");

    graphZoom = d3.zoom()
        .scaleExtent([0.15, 4])
        .on("zoom", (event) => {
            graphContainerGroup.attr("transform", event.transform);
        });

    svg.call(graphZoom);

    const graphZoomInBtn = document.getElementById("graphZoomInBtn");
    const graphZoomOutBtn = document.getElementById("graphZoomOutBtn");
    const graphResetBtn = document.getElementById("graphResetBtn");
    const graphSoundToggleBtn = document.getElementById("graphSoundToggleBtn");

    if (graphZoomInBtn) {
        graphZoomInBtn.onclick = () => {
            if (graphSvg && graphZoom) svg.transition().duration(250).call(graphZoom.scaleBy, 1.3);
        };
    }
    if (graphZoomOutBtn) {
        graphZoomOutBtn.onclick = () => {
            if (graphSvg && graphZoom) svg.transition().duration(250).call(graphZoom.scaleBy, 0.77);
        };
    }
    if (graphResetBtn) {
        graphResetBtn.onclick = () => {
            resetGraphView();
        };
    }
    if (graphSoundToggleBtn) {
        graphSoundToggleBtn.onclick = () => {
            toggleGraphSound();
        };
        updateGraphSoundButtonUI();
    }
}

export function resetGraphView() {
    const forceGraphSvg = document.getElementById("forceGraphSvg");
    if (!graphSvg || !graphZoom || !forceGraphSvg) return;
    const width = forceGraphSvg.clientWidth || 800;
    const height = forceGraphSvg.clientHeight || 480;
    graphSvg.transition().duration(400).call(
        graphZoom.transform,
        d3.zoomIdentity.translate(width / 2, height / 2).scale(0.85)
    );
}

export function resetForceGraph(startInfo, targetInfo, viaInfo, silent = false) {
    clearGraphPathTimers();
    graphData = { nodes: [], links: [] };
    graphNodesMap.clear();
    graphLinksSet.clear();
    graphFinalPathSet.clear();

    const graphEmptyState = document.getElementById("graphEmptyState");
    const graphPathLegend = document.getElementById("graphPathLegend");
    const graphCard = document.getElementById("graphCard");
    const graphViaLegend = document.getElementById("graphViaLegend");

    if (graphEmptyState) graphEmptyState.classList.add("d-none");
    if (graphPathLegend) graphPathLegend.classList.add("d-none");
    if (graphCard) graphCard.classList.remove("d-none");

    initForceGraph();

    graphStartId = startInfo && startInfo.title ? startInfo.title : (typeof startInfo === "string" ? startInfo : "Start");
    graphTargetId = targetInfo && targetInfo.title ? targetInfo.title : (typeof targetInfo === "string" ? targetInfo : "Target");
    
    let viaTitle = null;
    if (viaInfo) {
        viaTitle = typeof viaInfo === "string" ? viaInfo.trim() : (viaInfo.title || "");
        viaTitle = viaTitle.trim() || null;
    }
    graphViaId = viaTitle;

    if (graphViaLegend) {
        if (graphViaId) {
            graphViaLegend.classList.remove("d-none");
        } else {
            graphViaLegend.classList.add("d-none");
        }
    }

    const startSnippet = (startInfo && (startInfo.extract || startInfo.description || startInfo.snippet)) || "";
    const targetSnippet = (targetInfo && (targetInfo.extract || targetInfo.description || targetInfo.snippet)) || "";
    const viaSnippet = (viaInfo && (viaInfo.extract || viaInfo.description || viaInfo.snippet)) || "";

    if (startSnippet) graphSnippetCache.set(graphStartId, startSnippet);
    if (targetSnippet) graphSnippetCache.set(graphTargetId, targetSnippet);
    if (viaSnippet && graphViaId) graphSnippetCache.set(graphViaId, viaSnippet);

    const lang = appSettings.lang || "en";

    addGraphNode({
        id: graphStartId,
        title: graphStartId,
        type: "start",
        depth: 0,
        x: -180,
        y: 0,
        fx: -180,
        links_count: 0,
        snippet: startSnippet,
        url: (startInfo && startInfo.url) || `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(graphStartId.replace(/ /g, "_"))}`
    });

    addGraphNode({
        id: graphTargetId,
        title: graphTargetId,
        type: "target",
        depth: 0,
        x: 180,
        y: 0,
        fx: 180,
        links_count: 0,
        snippet: targetSnippet,
        url: (targetInfo && targetInfo.url) || `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(graphTargetId.replace(/ /g, "_"))}`
    });

    if (graphViaId && graphViaId !== graphStartId && graphViaId !== graphTargetId) {
        addGraphNode({
            id: graphViaId,
            title: graphViaId,
            type: "via",
            depth: 1,
            x: 0,
            y: -60,
            fx: 0,
            links_count: 0,
            snippet: viaSnippet,
            url: (viaInfo && viaInfo.url) || `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(graphViaId.replace(/ /g, "_"))}`
        });
    }

    startOrUpdateSimulation();
    resetGraphView();

    if (!silent) {
        playGraphPop("spawn", { pitch: 1.0 });
        if (graphViaId && graphViaId !== graphStartId && graphViaId !== graphTargetId) {
            setTimeout(() => playGraphPop("spawn", { pitch: 1.25 }), 120);
        }
    }
}

export function addGraphNode(node) {
    if (node.snippet) {
        graphSnippetCache.set(node.id, node.snippet);
    } else if (graphSnippetCache.has(node.id)) {
        node.snippet = graphSnippetCache.get(node.id);
    }

    if (graphNodesMap.has(node.id)) {
        const existing = graphNodesMap.get(node.id);
        if (node.type === "start" || node.type === "target" || node.type === "via") existing.type = node.type;
        if (node.depth !== undefined && existing.depth === undefined) existing.depth = node.depth;
        if (node.links_count !== undefined) existing.links_count = node.links_count;
        if (node.snippet && !existing.snippet) existing.snippet = node.snippet;
        if (node.url && !existing.url) existing.url = node.url;
        return existing;
    }
    graphNodesMap.set(node.id, node);
    graphData.nodes.push(node);
    return node;
}

export function addGraphLink(sourceId, targetId, direction, isFinalPath = false) {
    if (!sourceId || !targetId || sourceId === targetId) return;
    const key = `${sourceId}|${targetId}`;
    if (graphLinksSet.has(key)) {
        if (isFinalPath) {
            const existing = graphData.links.find(l => 
                (l.source.id === sourceId || l.source === sourceId) &&
                (l.target.id === targetId || l.target === targetId)
            );
            if (existing) existing.isFinalPath = true;
        }
        return;
    }
    graphLinksSet.add(key);
    graphData.links.push({
        source: sourceId,
        target: targetId,
        direction: direction || "forward",
        isFinalPath: isFinalPath
    });
}

export function recordPageInGraph(page, direction, silent = false) {
    if (!page || !page.title) return;
    if (typeof d3 === "undefined") return;

    const graphEmptyState = document.getElementById("graphEmptyState");
    const graphCard = document.getElementById("graphCard");
    if (graphEmptyState) graphEmptyState.classList.add("d-none");
    if (graphCard) graphCard.classList.remove("d-none");

    const pageTitle = page.title;
    const isStart = pageTitle === graphStartId;
    const isTarget = pageTitle === graphTargetId;
    const isVia = pageTitle === graphViaId;
    const type = isStart ? "start" : isTarget ? "target" : isVia ? "via" : (direction || "forward");

    const isNewNode = !graphNodesMap.has(pageTitle);

    addGraphNode({
        id: pageTitle,
        title: pageTitle,
        type: type,
        depth: page.depth !== undefined ? page.depth : 0,
        links_count: page.links_count || 0,
        snippet: page.snippet || "",
        url: page.url || ""
    });

    let newLinksCount = 0;
    const trail = page.path_so_far || [];
    if (trail.length >= 2) {
        for (let i = 0; i < trail.length - 1; i++) {
            const src = trail[i];
            const dst = trail[i + 1];
            const srcType = src === graphStartId ? "start" : (src === graphViaId ? "via" : direction);
            const dstType = dst === graphTargetId ? "target" : (dst === graphViaId ? "via" : direction);
            addGraphNode({ id: src, title: src, type: srcType, depth: i });
            addGraphNode({ id: dst, title: dst, type: dstType, depth: i + 1 });
            const linkKey = `${src}|${dst}`;
            if (!graphLinksSet.has(linkKey)) newLinksCount++;
            addGraphLink(src, dst, direction);
        }
    } else if (trail.length === 1 && trail[0] !== pageTitle) {
        const srcType = trail[0] === graphStartId ? "start" : (trail[0] === graphViaId ? "via" : direction);
        addGraphNode({ id: trail[0], title: trail[0], type: srcType, depth: 0 });
        const linkKey = `${trail[0]}|${pageTitle}`;
        if (!graphLinksSet.has(linkKey)) newLinksCount++;
        addGraphLink(trail[0], pageTitle, direction);
    }

    updateGraphD3Elements();

    if (!silent && (isNewNode || newLinksCount > 0)) {
        playGraphPop("node", {
            direction: direction,
            depth: page.depth !== undefined ? page.depth : 0,
        });
    }
}

export function highlightFinalPathInGraph(pathTitles, immediate = false) {
    if (!pathTitles || pathTitles.length < 2) return;
    if (typeof d3 === "undefined") return;

    clearGraphPathTimers();
    graphFinalPathSet = new Set(pathTitles);
    const graphPathLegend = document.getElementById("graphPathLegend");
    if (graphPathLegend) graphPathLegend.classList.remove("d-none");

    const startN = graphNodesMap.get(graphStartId);
    if (startN) startN.fx = null;
    const targetN = graphNodesMap.get(graphTargetId);
    if (targetN) targetN.fx = null;
    const viaN = graphNodesMap.get(graphViaId);
    if (viaN) viaN.fx = null;

    if (graphContainerGroup) {
        graphContainerGroup.selectAll("line.graph-link")
            .classed("graph-link-dimmed", true);

        graphContainerGroup.selectAll("g.graph-node")
            .classed("graph-node-dimmed", d => !graphFinalPathSet.has(d.id));
    }

    if (immediate) {
        for (let i = 0; i < pathTitles.length; i++) {
            const title = pathTitles[i];
            const isStart = i === 0;
            const isTarget = i === pathTitles.length - 1;
            const isVia = title === graphViaId;
            const node = addGraphNode({
                id: title,
                title: title,
                type: isStart ? "start" : isTarget ? "target" : isVia ? "via" : "path",
                depth: i
            });
            node.isFinalPath = true;

            if (i < pathTitles.length - 1) {
                const next = pathTitles[i + 1];
                const nextIsTarget = (i + 1 === pathTitles.length - 1);
                const nextIsVia = next === graphViaId;
                addGraphNode({
                    id: next,
                    title: next,
                    type: nextIsTarget ? "target" : nextIsVia ? "via" : "path",
                    depth: i + 1
                });
                addGraphLink(title, next, "path", true);
            }
        }

        updateGraphD3Elements();
        if (graphContainerGroup) {
            graphContainerGroup.selectAll("line.graph-link")
                .classed("graph-link-dimmed", d => !d.isFinalPath);
        }
        if (graphSimulation) {
            graphSimulation.alpha(0.6).restart();
        }
        setTimeout(() => zoomToDiscoveredPath(pathTitles), 300);
        return;
    }

    const intervalMs = 600;

    pathTitles.forEach((title, idx) => {
        const timer = setTimeout(() => {
            const forceGraphSvg = document.getElementById("forceGraphSvg");
            if (!forceGraphSvg || typeof d3 === "undefined") return;

            const isStart = idx === 0;
            const isTarget = idx === pathTitles.length - 1;
            const isVia = title === graphViaId;

            const node = addGraphNode({
                id: title,
                title: title,
                type: isStart ? "start" : isTarget ? "target" : isVia ? "via" : "path",
                depth: idx
            });
            node.isFinalPath = true;

            if (idx > 0) {
                const prevTitle = pathTitles[idx - 1];
                addGraphLink(prevTitle, title, "path", true);
            }

            updateGraphD3Elements();

            if (graphSimulation) {
                graphSimulation.alpha(0.35).restart();
            }

            if (graphContainerGroup) {
                const nodeG = graphContainerGroup.selectAll("g.graph-node")
                    .filter(d => d.id === title);

                nodeG.classed("graph-node-dimmed", false);

                nodeG.select("circle")
                    .attr("r", 0)
                    .transition()
                    .duration(320)
                    .ease(d3.easeBackOut.overshoot(2.2))
                    .attr("r", d => (d.type === "start" || d.type === "target" || d.type === "via") ? 23 : 19)
                    .transition()
                    .duration(280)
                    .ease(d3.easeCubicOut)
                    .attr("r", d => (d.type === "start" || d.type === "target" || d.type === "via") ? 17 : 14);

                if (idx > 0) {
                    const prevTitle = pathTitles[idx - 1];
                    const linkLine = graphContainerGroup.selectAll("line.graph-link")
                        .filter(l => {
                            const s = l.source.id || l.source;
                            const t = l.target.id || l.target;
                            return (s === prevTitle && t === title) || (s === title && t === prevTitle);
                        });

                    linkLine
                        .classed("graph-link-highlight", true)
                        .classed("graph-link-dimmed", false)
                        .attr("stroke-width", 1)
                        .transition()
                        .duration(400)
                        .attr("stroke-width", 4.2);
                }
            }

            playGraphPop("path-node", { index: idx, total: pathTitles.length });

            if (idx === pathTitles.length - 1) {
                const finishTimer = setTimeout(() => {
                    zoomToDiscoveredPath(pathTitles);
                }, 400);
                graphPathEmergenceTimers.push(finishTimer);
            }

        }, idx * intervalMs);

        graphPathEmergenceTimers.push(timer);
    });
}

export function zoomToDiscoveredPath(pathTitles) {
    const forceGraphSvg = document.getElementById("forceGraphSvg");
    if (!graphSvg || !graphZoom || !forceGraphSvg || !pathTitles || pathTitles.length === 0) return;
    const pathNodes = pathTitles.map(t => graphNodesMap.get(t)).filter(n => n && n.x !== undefined && n.y !== undefined);
    if (pathNodes.length === 0) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    pathNodes.forEach(n => {
        if (n.x < minX) minX = n.x;
        if (n.x > maxX) maxX = n.x;
        if (n.y < minY) minY = n.y;
        if (n.y > maxY) maxY = n.y;
    });

    const width = forceGraphSvg.clientWidth || 800;
    const height = forceGraphSvg.clientHeight || 480;
    const padding = 80;

    const dx = Math.max(maxX - minX, 100);
    const dy = Math.max(maxY - minY, 100);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;

    const scale = Math.max(0.35, Math.min(2.0, 0.85 / Math.max(dx / (width - padding * 2), dy / (height - padding * 2))));
    const translate = [width / 2 - scale * midX, height / 2 - scale * midY];

    graphSvg.transition()
        .duration(850)
        .ease(d3.easeCubicOut)
        .call(graphZoom.transform, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale));
}

function startOrUpdateSimulation() {
    if (typeof d3 === "undefined" || !graphContainerGroup) return;

    if (!graphSimulation) {
        graphSimulation = d3.forceSimulation(graphData.nodes)
            .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(d => d.isFinalPath ? 75 : 65))
            .force("charge", d3.forceManyBody().strength(d => (d.type === "start" || d.type === "target" || d.type === "via") ? -350 : -140))
            .force("collide", d3.forceCollide().radius(26).iterations(2))
            .force("center", d3.forceCenter(0, 0).strength(0.06))
            .force("x", d3.forceX(d => d.type === "start" ? -180 : d.type === "target" ? 180 : 0).strength(0.04))
            .force("y", d3.forceY(0).strength(0.04))
            .on("tick", ticked);
    } else {
        graphSimulation.nodes(graphData.nodes);
        graphSimulation.force("link").links(graphData.links);
        graphSimulation.alpha(0.35).restart();
    }

    updateGraphD3Elements();
}

function updateGraphD3Elements() {
    if (!graphContainerGroup || typeof d3 === "undefined") return;

    if (graphSimulation) {
        graphSimulation.nodes(graphData.nodes);
        graphSimulation.force("link").links(graphData.links);
        graphSimulation.alpha(0.3).restart();
    }

    const linksLayer = graphContainerGroup.select(".links-layer");
    const nodesLayer = graphContainerGroup.select(".nodes-layer");

    // ---- LINKS ----
    const linkSel = linksLayer.selectAll("line.graph-link")
        .data(graphData.links, d => `${(d.source.id || d.source)}|${(d.target.id || d.target)}`);

    linkSel.exit().remove();

    const linkEnter = linkSel.enter().append("line")
        .attr("class", d => `graph-link ${d.isFinalPath ? "graph-link-highlight" : ""}`)
        .attr("stroke", d => {
            if (d.isFinalPath) return "#eab308";
            return d.direction === "backward" ? "rgba(6, 182, 212, 0.45)" : "rgba(59, 130, 246, 0.45)";
        })
        .attr("stroke-width", d => d.isFinalPath ? 3.5 : 1.8)
        .attr("marker-end", d => {
            if (d.isFinalPath) return "url(#arrow-path)";
            return d.direction === "backward" ? "url(#arrow-backward)" : "url(#arrow-forward)";
        });

    linkSel.merge(linkEnter)
        .classed("graph-link-highlight", d => !!d.isFinalPath)
        .attr("stroke", d => {
            if (d.isFinalPath) return "#eab308";
            return d.direction === "backward" ? "rgba(6, 182, 212, 0.45)" : "rgba(59, 130, 246, 0.45)";
        })
        .attr("stroke-width", d => d.isFinalPath ? 3.5 : 1.8)
        .attr("marker-end", d => {
            if (d.isFinalPath) return "url(#arrow-path)";
            return d.direction === "backward" ? "url(#arrow-backward)" : "url(#arrow-forward)";
        });

    // ---- NODES ----
    const nodeSel = nodesLayer.selectAll("g.graph-node")
        .data(graphData.nodes, d => d.id);

    nodeSel.exit().remove();

    const nodeEnter = nodeSel.enter().append("g")
        .attr("class", "graph-node")
        .style("cursor", "pointer")
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended)
        );

    nodeEnter.append("circle")
        .attr("r", d => (d.type === "start" || d.type === "target" || d.type === "via") ? 17 : (d.isFinalPath ? 14 : 10))
        .attr("fill", d => getNodeColor(d))
        .attr("stroke", "#ffffff")
        .attr("stroke-width", d => (d.type === "start" || d.type === "target" || d.type === "via") ? 3 : 2)
        .style("transition", "r 0.25s ease, fill 0.25s ease");

    nodeEnter.append("text")
        .attr("class", "node-icon")
        .attr("text-anchor", "middle")
        .attr("dy", "0.35em")
        .attr("fill", "#ffffff")
        .attr("font-size", d => (d.type === "start" || d.type === "target" || d.type === "via") ? "11px" : "9px")
        .attr("font-weight", "bold")
        .text(d => {
            if (d.type === "start") return "S";
            if (d.type === "target") return "T";
            if (d.type === "via") return "V";
            if (d.isFinalPath) return "★";
            return "";
        });

    nodeEnter.append("text")
        .attr("class", "node-label")
        .attr("x", 0)
        .attr("y", d => (d.type === "start" || d.type === "target" || d.type === "via") ? 27 : 20)
        .attr("text-anchor", "middle")
        .attr("font-size", d => (d.type === "start" || d.type === "target" || d.type === "via") ? "12px" : "10px")
        .attr("font-weight", d => (d.type === "start" || d.type === "target" || d.type === "via" || d.isFinalPath) ? "bold" : "500")
        .attr("fill", "var(--bs-body-color, #1f2937)")
        .text(d => truncateTitle(d.title, 18))
        .style("paint-order", "stroke")
        .style("stroke", "var(--bs-body-bg, #ffffff)")
        .style("stroke-width", "3px")
        .style("stroke-linejoin", "round");

    nodeEnter
        .on("mouseenter", (event, d) => showGraphTooltip(event, d))
        .on("mousemove", (event) => positionGraphTooltip(event))
        .on("mouseleave", () => hideGraphTooltip())
        .on("click", (event, d) => {
            if (event.defaultPrevented) return;
            const lang = appSettings.lang || "en";
            window.open(`https://${lang}.wikipedia.org/wiki/${encodeURIComponent(d.title.replace(/ /g, "_"))}`, "_blank");
        });

    const nodeMerged = nodeSel.merge(nodeEnter);
    nodeMerged.select("circle")
        .attr("r", d => (d.type === "start" || d.type === "target" || d.type === "via") ? 17 : (d.isFinalPath ? 14 : 10))
        .attr("fill", d => getNodeColor(d))
        .attr("stroke", d => d.isFinalPath ? "#facc15" : (d.type === "via" ? "#c084fc" : "#ffffff"))
        .attr("stroke-width", d => d.isFinalPath ? 3.5 : ((d.type === "start" || d.type === "target" || d.type === "via") ? 3 : 2))
        .classed("graph-node-highlight", d => !!d.isFinalPath)
        .classed("graph-node-via", d => d.type === "via");

    nodeMerged.select("text.node-icon")
        .text(d => {
            if (d.type === "start") return "S";
            if (d.type === "target") return "T";
            if (d.type === "via") return "V";
            if (d.isFinalPath) return "★";
            return "";
        });

    nodeMerged.select("text.node-label")
        .attr("font-weight", d => (d.type === "start" || d.type === "target" || d.type === "via" || d.isFinalPath) ? "bold" : "500")
        .attr("fill", d => d.isFinalPath ? "var(--bs-primary, #2563eb)" : (d.type === "via" ? "#9333ea" : "var(--bs-body-color, #1f2937)"));
}

function getNodeColor(d) {
    if (d.type === "start") return "#10b981";
    if (d.type === "target") return "#ef4444";
    if (d.type === "via") return "#9333ea";
    if (d.isFinalPath) return "#f59e0b";
    if (d.type === "backward") return "#06b6d4";
    return "#3b82f6";
}

function truncateTitle(str, maxLen = 16) {
    if (!str) return "";
    return str.length > maxLen ? str.slice(0, maxLen - 1) + "…" : str;
}

function ticked() {
    if (!graphContainerGroup) return;

    graphContainerGroup.selectAll("line.graph-link")
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);

    graphContainerGroup.selectAll("g.graph-node")
        .attr("transform", d => `translate(${d.x},${d.y})`);
}

function dragstarted(event, d) {
    if (!event.active && graphSimulation) graphSimulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active && graphSimulation) graphSimulation.alphaTarget(0);
    if (!graphFinalPathSet.size && (d.type === "start" || d.type === "target" || d.type === "via")) {
        d.fx = d.x;
        d.fy = d.y;
    } else {
        d.fx = null;
        d.fy = null;
    }
}

function showGraphTooltip(event, d) {
    const graphTooltip = document.getElementById("graphTooltip");
    if (!graphTooltip) return;
    currentTooltipNodeId = d.id;

    const typeLabel = d.type === "start" ? "Start Article" :
                      d.type === "target" ? "Target Article" :
                      d.type === "via" ? "Via Milestone Article" :
                      d.isFinalPath ? "Discovered Path" :
                      d.type === "backward" ? "Backward Frontier" : "Forward Frontier";

    const badgeClass = d.type === "start" ? "text-bg-success" :
                       d.type === "target" ? "text-bg-danger" :
                       d.type === "via" ? "text-bg-purple text-white" :
                       d.isFinalPath ? "text-bg-warning text-dark" :
                       d.type === "backward" ? "text-bg-info text-dark" : "text-bg-primary";

    let snippetText = d.snippet || graphSnippetCache.get(d.id) || "";

    let snippetHtml = "";
    if (snippetText) {
        snippetHtml = `<div class="text-muted small text-truncate-2" style="font-size: 0.75rem; max-height: 48px; overflow: hidden;" title="${escapeHtml(snippetText)}">${escapeHtml(snippetText)}</div>`;
    } else {
        snippetHtml = `<div id="graphTooltipSnippet" class="text-muted small text-truncate-2" style="font-size: 0.75rem; max-height: 48px; overflow: hidden;"><span class="spinner-border spinner-border-sm me-1 text-secondary" style="width: 0.65rem; height: 0.65rem;" role="status"></span>Loading summary...</div>`;
    }

    graphTooltip.innerHTML = `
        <div class="d-flex align-items-center justify-content-between gap-2 mb-1">
            <span class="badge ${badgeClass} text-uppercase" style="font-size: 0.65rem;">${typeLabel}</span>
            <span class="text-secondary small">Hop ${d.depth !== undefined ? d.depth : 0}</span>
        </div>
        <div class="fw-bold mb-1 text-truncate">${escapeHtml(d.title)}</div>
        ${d.links_count ? `<div class="text-secondary small mb-1"><i class="bi bi-link-45deg"></i> ${d.links_count} links explored</div>` : ""}
        ${snippetHtml}
        <div class="text-primary small mt-1" style="font-size: 0.7rem;"><i class="bi bi-box-arrow-up-right me-1"></i>Click to open in Wikipedia</div>
    `;
    graphTooltip.classList.remove("d-none");
    positionGraphTooltip(event);

    if (!snippetText) {
        const nodeId = d.id;
        const nodeTitle = d.title || d.id;
        const lang = appSettings.lang || "en";
        fetch(`/api/info?title=${encodeURIComponent(nodeTitle)}&lang=${encodeURIComponent(lang)}`)
            .then(r => r.ok ? r.json() : null)
            .then(info => {
                const fetchedSnippet = (info && (info.extract || info.description)) ? (info.extract || info.description) : "No summary available.";
                d.snippet = fetchedSnippet;
                graphSnippetCache.set(nodeId, fetchedSnippet);
                if (currentTooltipNodeId === nodeId) {
                    const snippetEl = document.getElementById("graphTooltipSnippet");
                    if (snippetEl) {
                        snippetEl.textContent = fetchedSnippet;
                        snippetEl.title = fetchedSnippet;
                    }
                }
            })
            .catch(() => {
                const fallbackSnippet = "No summary available.";
                d.snippet = fallbackSnippet;
                graphSnippetCache.set(nodeId, fallbackSnippet);
                if (currentTooltipNodeId === nodeId) {
                    const snippetEl = document.getElementById("graphTooltipSnippet");
                    if (snippetEl) {
                        snippetEl.textContent = fallbackSnippet;
                    }
                }
            });
    }
}

function positionGraphTooltip(event) {
    const graphTooltip = document.getElementById("graphTooltip");
    const graphContainer = document.getElementById("graphContainer");
    if (!graphTooltip || !graphContainer) return;
    const bounds = graphContainer.getBoundingClientRect();
    const mouseX = event.clientX - bounds.left;
    const mouseY = event.clientY - bounds.top;
    const ttWidth = graphTooltip.offsetWidth || 260;
    const ttHeight = graphTooltip.offsetHeight || 120;

    let left = mouseX + 15;
    let top = mouseY + 15;

    if (left + ttWidth > bounds.width) left = mouseX - ttWidth - 15;
    if (top + ttHeight > bounds.height) top = mouseY - ttHeight - 15;

    graphTooltip.style.left = `${Math.max(5, left)}px`;
    graphTooltip.style.top = `${Math.max(5, top)}px`;
}

function hideGraphTooltip() {
    currentTooltipNodeId = null;
    const graphTooltip = document.getElementById("graphTooltip");
    if (graphTooltip) graphTooltip.classList.add("d-none");
}
