/**
 * 代码知识图谱可视化组件
 *
 * 样式仿 GitNexus Web UI — 深色 void 背景、曲线边、分层节点大小、悬停标签
 * Sigma.js + Graphology + ForceAtlas2
 */

"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";

// GitNexus 配色 — 略柔和，层次分明
const NODE_COLORS: Record<string, string> = {
  class: "#f59e0b", function: "#10b981", method: "#14b8a6",
  variable: "#64748b", file: "#3b82f6", folder: "#6366f1",
  module: "#7c3aed", interface: "#ec4899", enum: "#f97316",
  route: "#f43f5e", tool: "#a855f7", process: "#f43f5e",
  community: "#818cf8", markdown_section: "#60a5fa",
};

// 节点大小 — 结构节点大、代码节点小，形成清晰层级
function getNodeSize(type: string): number {
  switch (type) {
    case "file":    return 6;
    case "folder":  return 10;
    case "module":  return 13;
    case "class":   return 8;
    case "interface": return 7;
    case "function": return 4;
    case "method":  return 3;
    case "variable": return 2;
    case "enum":    return 5;
    case "route":   return 5;
    case "tool":    return 5;
    case "process": return 0; // 隐藏 — 元数据节点
    case "community": return 0; // 隐藏
    default:        return 4;
  }
}

// GitNexus 边样式 — 每种关系有独立颜色和粗细
const EDGE_STYLES: Record<string, { color: string; sizeMultiplier: number }> = {
  CALLS:             { color: "#7c3aed", sizeMultiplier: 0.8 },
  EXTENDS:           { color: "#c2410c", sizeMultiplier: 1.0 },
  IMPLEMENTS:        { color: "#be185d", sizeMultiplier: 0.9 },
  IMPORTS:           { color: "#1d4ed8", sizeMultiplier: 0.6 },
  CONTAINS:          { color: "#2d5a3d", sizeMultiplier: 0.4 },
  DEFINED_IN:        { color: "#0e7490", sizeMultiplier: 0.5 },
  MEMBER_OF:         { color: "#4a4a5a", sizeMultiplier: 0.4 },
  METHOD_OVERRIDES:  { color: "#be185d", sizeMultiplier: 0.7 },
  STEP_IN_PROCESS:   { color: "#f43f5e", sizeMultiplier: 0.6 },
};

const DEFAULT_NODE_COLOR = "#9ca3af";
const DEFAULT_EDGE_COLOR = "#4a4a5a";
const DIMMED_OPACITY = 0.12;

export interface GraphNodeData {
  id: string; label: string; type: string; community?: string;
}
export interface GraphEdgeData {
  source: string; target: string; type: string;
}

interface CodeGraphViewProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  width: number;
  height: number;
  onNodeClick?: (nodeId: string) => void;
  visibleNodeTypes?: string[];
  visibleEdgeTypes?: string[];
}

function assignInitialPositions(graph: Graph) {
  const count = graph.order;
  if (count === 0) return;

  // 将节点分为结构型（file/folder/module）和代码型
  const structural: string[] = [];
  const code: string[] = [];
  graph.forEachNode((nodeId, attr) => {
    if (["folder", "module", "file"].includes(attr.nodeType)) {
      structural.push(nodeId);
    } else {
      code.push(nodeId);
    }
  });

  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const spread = Math.sqrt(count) * 40;

  // 结构节点宽辐射分布
  structural.forEach((id, i) => {
    const radius = spread * Math.sqrt((i + 1) / Math.max(structural.length, 1));
    const angle = i * goldenAngle;
    graph.setNodeAttribute(id, "x", Math.cos(angle) * radius);
    graph.setNodeAttribute(id, "y", Math.sin(angle) * radius);
  });

  // 代码节点围绕结构节点分布
  const childJitter = Math.sqrt(count) * 3;
  code.forEach((id, i) => {
    const parentIdx = i % Math.max(structural.length, 1);
    const parentId = structural[parentIdx];
    if (parentId && graph.hasNode(parentId)) {
      const px = graph.getNodeAttribute(parentId, "x");
      const py = graph.getNodeAttribute(parentId, "y");
      graph.setNodeAttribute(id, "x", px + (Math.random() - 0.5) * childJitter);
      graph.setNodeAttribute(id, "y", py + (Math.random() - 0.5) * childJitter);
    } else {
      const radius = 30 + (i / count) * spread;
      const angle = i * goldenAngle;
      graph.setNodeAttribute(id, "x", Math.cos(angle) * radius);
      graph.setNodeAttribute(id, "y", Math.sin(angle) * radius);
    }
  });
}

// 节点质量 — 结构节点更重，在 FA2 中分散更开
function getNodeMass(type: string): number {
  switch (type) {
    case "module":  return 20;
    case "folder":  return 15;
    case "file":    return 3;
    case "class":
    case "interface": return 5;
    case "function":
    case "method":  return 2;
    default:        return 1;
  }
}

function getFA2Settings(nodeCount: number): forceAtlas2.ForceAtlas2Settings {
  if (nodeCount < 200) {
    return { gravity: 0.8, scalingRatio: 15, slowDown: 1, strongGravityMode: false,
      outboundAttractionDistribution: true, adjustSizes: true, edgeWeightInfluence: 1 };
  }
  if (nodeCount < 500) {
    return { gravity: 0.5, scalingRatio: 30, slowDown: 2, strongGravityMode: false,
      outboundAttractionDistribution: true, adjustSizes: true, edgeWeightInfluence: 1,
      barnesHutOptimize: true, barnesHutTheta: 0.6 };
  }
  return { gravity: 0.3, scalingRatio: 60, slowDown: 3, strongGravityMode: false,
    outboundAttractionDistribution: true, adjustSizes: true, edgeWeightInfluence: 1,
    barnesHutOptimize: true, barnesHutTheta: 0.8 };
}

export function CodeGraphView({
  nodes, edges, width, height, onNodeClick,
  visibleNodeTypes, visibleEdgeTypes,
}: CodeGraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const onNodeClickRef = useRef(onNodeClick);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [hoveredLabel, setHoveredLabel] = useState<string | null>(null);

  onNodeClickRef.current = onNodeClick;

  const getNeighbors = useCallback((graph: Graph, nodeId: string): Set<string> => {
    const neighbors = new Set<string>();
    neighbors.add(nodeId);
    graph.forEachNeighbor(nodeId, (nid) => neighbors.add(nid));
    return neighbors;
  }, []);

  // 主 effect
  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    if (sigmaRef.current) {
      try { sigmaRef.current.kill(); } catch {}
      sigmaRef.current = null;
    }

    const graph = new Graph({ multi: true, type: "directed" });
    graphRef.current = graph;

    // 添加节点
    nodes.forEach((n) => {
      if (!graph.hasNode(n.id)) {
        graph.addNode(n.id, {
          x: 0, y: 0,
          size: getNodeSize(n.type),
          color: NODE_COLORS[n.type] || DEFAULT_NODE_COLOR,
          label: n.label,
          nodeType: n.type,
          community: n.community,
          mass: getNodeMass(n.type),
        });
      }
    });

    // 添加边 — 曲线 + 类型独立样式
    const edgeBaseSize = graph.order > 20000 ? 1.0 : graph.order > 5000 ? 1.5 : 2.5;
    edges.forEach((e) => {
      if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
        const key = `${e.source}->${e.target}:${e.type}`;
        if (!graph.hasEdge(key)) {
          try {
            const style = EDGE_STYLES[e.type] || { color: DEFAULT_EDGE_COLOR, sizeMultiplier: 0.5 };
            graph.addEdge(e.source, e.target, {
              size: edgeBaseSize * style.sizeMultiplier,
              color: style.color,
              relationType: e.type,
            });
          } catch {}
        }
      }
    });

    // 初始位置 + 布局
    assignInitialPositions(graph);
    try {
      const settings = getFA2Settings(graph.order);
      const iterations = graph.order < 200 ? 80 : graph.order < 500 ? 100 : 150;
      forceAtlas2.assign(graph, { iterations, settings });
    } catch (e) {
      console.warn("FA2 layout failed", e);
    }

    // 创建 Sigma
    let sigma: Sigma;
    try {
      sigma = new Sigma(graph, containerRef.current, {
        renderLabels: false,
        labelFont: "JetBrains Mono, ui-monospace, monospace",
        labelSize: 12,
        labelWeight: "600",
        labelColor: { color: "#e2e8f0" },
        defaultNodeColor: DEFAULT_NODE_COLOR,
        defaultEdgeColor: DEFAULT_EDGE_COLOR,
        defaultEdgeType: "arrow",
        minCameraRatio: 0.002,
        maxCameraRatio: 50,
        hideEdgesOnMove: true,
        zIndex: true,
      });
    } catch (e) {
      console.error("Sigma init failed", e);
      return;
    }
    sigmaRef.current = sigma;

    // 事件
    sigma.on("clickNode", (e) => {
      const nodeId = e.node;
      setSelectedNode((prev) => (prev === nodeId ? null : nodeId));
      onNodeClickRef.current?.(nodeId);
    });
    sigma.on("clickStage", () => setSelectedNode(null));
    sigma.on("enterNode", (e) => {
      setHoveredNode(e.node);
      const label = graph.getNodeAttribute(e.node, "label");
      setHoveredLabel(label || e.node);
    });
    sigma.on("leaveNode", () => {
      setHoveredNode(null);
      setHoveredLabel(null);
    });

    // 自适应缩放
    requestAnimationFrame(() => {
      try {
        const camera = sigma.getCamera();
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        graph.forEachNode((_node, attr) => {
          if (attr.x < minX) minX = attr.x;
          if (attr.x > maxX) maxX = attr.x;
          if (attr.y < minY) minY = attr.y;
          if (attr.y > maxY) maxY = attr.y;
        });
        const graphW = Math.max(1, maxX - minX);
        const graphH = Math.max(1, maxY - minY);
        const ratio = Math.min(width / graphW, height / graphH) * 0.85;
        const targetRatio = Math.max(0.5, Math.min(ratio, 3));
        camera.animate(
          { ratio: targetRatio, x: (minX + maxX) / 2, y: (minY + maxY) / 2 },
          { duration: 500 }
        );
      } catch {}
    });

    return () => {
      if (sigmaRef.current) {
        try { sigmaRef.current.kill(); } catch {}
        sigmaRef.current = null;
      }
    };
  }, [nodes, edges, width, height]); // eslint-disable-line react-hooks/exhaustive-deps

  // 悬停/选中高亮
  useEffect(() => {
    const sigma = sigmaRef.current;
    const graph = graphRef.current;
    if (!sigma || !graph) return;

    const targetNode = hoveredNode || selectedNode;
    const neighbors = targetNode ? getNeighbors(graph, targetNode) : null;

    sigma.setSetting("nodeReducer", (nodeId, data) => {
      if (visibleNodeTypes?.length && !visibleNodeTypes.includes(data.nodeType)) {
        return { ...data, hidden: true };
      }
      const hasLabel = graph.hasNode(nodeId);
      const label = hasLabel ? graph.getNodeAttribute(nodeId, "label") : "";
      const base = { ...data, borderColor: "#1e293b", borderSize: 2, label };
      if (!targetNode) return base;
      const isTarget = nodeId === targetNode;
      const isNeighbor = neighbors?.has(nodeId);
      if (isTarget) return { ...base, size: base.size * 2, zIndex: 2, borderColor: "#ffffff", borderSize: 4, label };
      if (isNeighbor) return { ...base, size: base.size * 1.4, zIndex: 1, borderColor: "#ffffff", borderSize: 3, label };
      return { ...base, color: dimColor(data.color, DIMMED_OPACITY), zIndex: 0, borderColor: "#1e293b", borderSize: 1 };
    });

    sigma.setSetting("edgeReducer", (edgeId, data) => {
      if (visibleEdgeTypes?.length && !visibleEdgeTypes.includes(data.relationType)) {
        return { ...data, hidden: true };
      }
      if (!targetNode) return data;
      const { source, target } = graph.extremities(edgeId);
      const isConnected =
        (source === targetNode && neighbors?.has(target)) ||
        (target === targetNode && neighbors?.has(source));
      if (isConnected) return { ...data, size: data.size * 2.5, color: brightenColor(data.color, 1.5), zIndex: 1 };
      return { ...data, color: dimColor(data.color, 0.08), size: data.size * 0.3, zIndex: 0 };
    });
  }, [selectedNode, hoveredNode, visibleNodeTypes, visibleEdgeTypes, getNeighbors]);

  if (nodes.length === 0) return null;

  const typeCounts = nodes.reduce<Record<string, number>>((acc, n) => {
    acc[n.type] = (acc[n.type] || 0) + 1;
    return acc;
  }, {});

  return (
    <div style={{ width, height, minHeight: 400 }} className="relative overflow-hidden rounded-lg">
      {/* 背景渐变 — 仿 GitNexus void 风格 */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: `
            radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.03) 0%, transparent 70%),
            linear-gradient(to bottom, #06060a, #0a0a10)
          `,
        }}
      />
      {/* Sigma 容器 */}
      <div
        ref={containerRef}
        className="absolute inset-0 cursor-grab active:cursor-grabbing"
      />

      {/* 悬停节点名称 tooltip — 仿 GitNexus 居中显示 */}
      {hoveredLabel && !selectedNode && (
        <div className="pointer-events-none absolute top-4 left-1/2 z-20 -translate-x-1/2 animate-fade-in rounded-lg border border-slate-700/60 bg-slate-900/95 px-3 py-1.5 backdrop-blur-sm">
          <span className="font-mono text-sm text-slate-200">{hoveredLabel}</span>
        </div>
      )}

      {/* 选中节点信息栏 — 仿 GitNexus */}
      {selectedNode && (() => {
        const label = graphRef.current?.getNodeAttribute(selectedNode, "label") || selectedNode;
        const type = graphRef.current?.getNodeAttribute(selectedNode, "nodeType") || "";
        return (
          <div className="absolute top-4 left-1/2 z-20 flex -translate-x-1/2 animate-slide-up items-center gap-2 rounded-xl border border-primary/30 bg-primary/20 px-4 py-2 backdrop-blur-sm">
            <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
            <span className="font-mono text-sm text-slate-200">{label}</span>
            <span className="text-xs text-slate-400">({type})</span>
            <button
              onClick={() => setSelectedNode(null)}
              className="ml-2 rounded px-2 py-0.5 text-xs text-slate-400 transition-colors hover:bg-white/10 hover:text-slate-200"
            >
              清除
            </button>
          </div>
        );
      })()}

      {/* 类型计数 — 左下 */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-1.5">
        {Object.entries(typeCounts)
          .filter(([_, count]) => count > 0)
          .map(([type, count]) => (
            <span
              key={type}
              className="flex items-center gap-1 rounded-md bg-slate-900/80 px-2 py-1 text-[10px] shadow-sm border border-slate-700/50"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: NODE_COLORS[type] || DEFAULT_NODE_COLOR }}
              />
              <span className="text-slate-300">{type}</span>
              <span className="text-slate-500">{count}</span>
            </span>
          ))}
      </div>

      {/* 操作提示 — 右下 */}
      <div className="absolute bottom-3 left-3 z-10 rounded-md bg-slate-900/80 px-2 py-1 text-[10px] text-slate-500 shadow-sm border border-slate-700/50">
        滚轮缩放 · 拖拽平移 · 点击节点查看详情
      </div>
    </div>
  );
}

// ── 颜色工具 ──
function hexToRgb(hex: string): [number, number, number] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)] : [107, 114, 128];
}
function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("");
}
function dimColor(hex: string, factor: number): string {
  const [r, g, b] = hexToRgb(hex);
  const bg = [6, 6, 10];
  return rgbToHex(r * factor + bg[0] * (1 - factor), g * factor + bg[1] * (1 - factor), b * factor + bg[2] * (1 - factor));
}
function brightenColor(hex: string, factor: number): string {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex(Math.min(255, r * factor), Math.min(255, g * factor), Math.min(255, b * factor));
}
