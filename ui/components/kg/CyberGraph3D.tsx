/**
 * 知识图谱可视化 — 图计算驱动版
 *
 * 设计原则：
 * - 2D 力导向布局（无 3D 旋转，可读性优先）
 * - 节点大小 = 连接度（degree centrality）
 * - 颜色 = 社区归属（同社区同色系）
 * - 聚焦点击 = 只显示邻居关系
 * - 强排斥 → 节点不重叠
 */

"use client";

import { useEffect, useRef } from "react";

// 社区色板（12 色，高对比度）
const COMMUNITY_PALETTE = [
  "#ef4444", "#f97316", "#eab308", "#22c55e",
  "#06b6d4", "#3b82f6", "#8b5cf6", "#d946ef",
  "#ec4899", "#14b8a6", "#84cc16", "#f43f5e",
];

// 节点类型颜色（用于图例）
const TYPE_COLORS: Record<string, string> = {
  class: "#f59e0b", function: "#10b981", method: "#14b8a6",
  variable: "#94a3b8", file: "#3b82f6", folder: "#6366f1",
  module: "#7c3aed", interface: "#ec4899", enum: "#f97316",
  route: "#f43f5e", tool: "#a855f7",
};

export interface GraphNodeData {
  id: string; label: string; type: string; community?: string;
}
export interface GraphEdgeData {
  source: string; target: string; type: string;
}

interface CyberGraph3DProps {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  width: number;
  height: number;
  onNodeClick?: (nodeId: string) => void;
}

export function CyberGraph3D({ nodes, edges, width, height, onNodeClick }: CyberGraph3DProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef(0);

  // 布局 + 图计算
  const state = useRef({
    x: [] as number[], y: [] as number[],
    vx: [] as number[], vy: [] as number[],
    adj: [] as number[][],
    degree: [] as number[],
    community: [] as number[], // community index per node
    simFrame: 0,
  });

  // 交互
  const selIdx = useRef(-1);
  const hovIdx = useRef(-1);
  const cam = useRef({ offsetX: 0, offsetY: 0, zoom: 1, dragging: false, lx: 0, ly: 0 });
  const zoomTarget = useRef(1);

  const valid = nodes.filter(n => n.type !== "process" && n.type !== "community");
  const idMap = new Map(valid.map((v, i) => [v.id, i]));

  // 初始化布局 + 图计算
  useEffect(() => {
    const n = valid.length;
    if (n === 0) return;

    // 建立邻接表 + 计算度
    const adj: number[][] = Array.from({ length: n }, () => []);
    const degree: number[] = new Array(n).fill(0);
    edges.forEach(e => {
      const si = idMap.get(e.source), ti = idMap.get(e.target);
      if (si !== undefined && ti !== undefined && si !== ti) {
        if (!adj[si].includes(ti)) { adj[si].push(ti); degree[si]++; }
        if (!adj[ti].includes(si)) { adj[ti].push(si); degree[ti]++; }
      }
    });

    // 社区分配 — 使用已有 community 字段或按类型
    const communityMap = new Map<string, number>();
    let commIdx = 0;
    const community: number[] = valid.map(n => {
      const key = n.community || n.type;
      if (!communityMap.has(key)) { communityMap.set(key, commIdx++); }
      return communityMap.get(key)!;
    });

    if (state.current.x.length !== n) {
      // 初始化位置 — 按社区分区
      const commNodes = new Map<number, number[]>();
      community.forEach((c, i) => {
        if (!commNodes.has(c)) commNodes.set(c, []);
        commNodes.get(c)!.push(i);
      });

      const commCount = commNodes.size;
      const spread = Math.sqrt(n) * 45;
      const x: number[] = [], y: number[] = [];
      const vx: number[] = [], vy: number[] = [];

      const golden = Math.PI * (3 - Math.sqrt(5));

      // 每个社区分配一个扇形区域
      let commIdx2 = 0;
      for (const [c, indices] of commNodes) {
        const angleStart = (commIdx2 / commCount) * 2 * Math.PI;
        const angleSpan = (2 * Math.PI) / commCount * 0.7;
        const radius = spread * 0.5;

        indices.forEach((nodeI, j) => {
          const a = angleStart + (j / indices.length) * angleSpan;
          const r = radius * Math.sqrt((j + 1) / indices.length);
          x.push(Math.cos(a) * r + (Math.random() - 0.5) * 10);
          y.push(Math.sin(a) * r + (Math.random() - 0.5) * 10);
          vx.push(0); vy.push(0);
        });
        commIdx2++;
      }

      state.current = { x, y, vx, vy, adj, degree, community, simFrame: 0 };
    } else {
      state.current.adj = adj;
      state.current.degree = degree;
      state.current.community = community;
    }
  }, [nodes, edges]); // eslint-disable-line react-hooks/exhaustive-deps

  // 渲染
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !width || !height) return;
    const ctx = canvas.getContext("2d")!;
    const st = state.current;
    if (st.x.length === 0) return;

    const maxDeg = Math.max(...st.degree, 1);

    const render = () => {
      const w = (canvas!.width = width);
      const h = (canvas!.height = height);
      const { zoom, offsetX, offsetY } = cam.current;

      // === 力导向模拟（前 200 帧） ===
      if (st.simFrame < 200) {
        const rep = 8000, att = 0.005, damp = 0.85, maxV = 5;
        for (let i = 0; i < st.x.length; i++) {
          let fx = 0, fy = 0;
          for (let j = 0; j < st.x.length; j++) {
            if (i === j) continue;
            const dx = st.x[i] - st.x[j], dy = st.y[i] - st.y[j];
            const d2 = Math.max(dx * dx + dy * dy, 1);
            const f = rep / d2;
            const d = Math.sqrt(d2);
            fx += (dx / d) * f; fy += (dy / d) * f;
          }
          for (const j of st.adj[i] || []) {
            fx += (st.x[j] - st.x[i]) * att;
            fy += (st.y[j] - st.y[i]) * att;
          }
          fx -= st.x[i] * 0.002; fy -= st.y[i] * 0.002;
          st.vx[i] = (st.vx[i] + fx) * damp;
          st.vy[i] = (st.vy[i] + fy) * damp;
          const spd = Math.sqrt(st.vx[i] ** 2 + st.vy[i] ** 2);
          if (spd > maxV) { st.vx[i] /= spd / maxV; st.vy[i] /= spd / maxV; }
          st.x[i] += st.vx[i]; st.y[i] += st.vy[i];
        }
        st.simFrame++;
      }

      // === 绘制 ===
      ctx.fillStyle = "#050510";
      ctx.fillRect(0, 0, w, h);

      // 微网格
      ctx.strokeStyle = "rgba(99,102,241,0.04)";
      ctx.lineWidth = 0.5;
      for (let gx = -2000; gx < 2000; gx += 60) {
        const sx = w / 2 + (gx + offsetX) * zoom;
        ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, h); ctx.stroke();
      }
      for (let gy = -2000; gy < 2000; gy += 60) {
        const sy = h / 2 + (gy + offsetY) * zoom;
        ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(w, sy); ctx.stroke();
      }

      // 投影坐标
      const pts = st.x.map((_, i) => ({
        sx: w / 2 + (st.x[i] + offsetX) * zoom,
        sy: h / 2 + (st.y[i] + offsetY) * zoom,
        i,
      }));

      // 选中/悬停相关
      const sel = selIdx.current;
      const hov = hovIdx.current;
      const neighbors = new Set<number>();
      if (sel >= 0 && st.adj[sel]) for (const nb of st.adj[sel]) neighbors.add(nb);
      const isHL = (i: number) => sel < 0 || i === sel || neighbors.has(i);

      // === 边 ===
      const EDGE_COLORS: Record<string, string> = {
        CALLS: "#a78bfa", EXTENDS: "#fb923c", IMPLEMENTS: "#f472b6",
        IMPORTS: "#60a5fa", CONTAINS: "#4ade80", DEFINED_IN: "#22d3ee",
        MEMBER_OF: "#64748b", METHOD_OVERRIDES: "#fb7185",
      };

      for (const e of edges) {
        const si = idMap.get(e.source), ti = idMap.get(e.target);
        if (si === undefined || ti === undefined) continue;
        const p1 = pts[si], p2 = pts[ti];
        if (!p1 || !p2) continue;

        let alpha = 0.35;
        let lw = 1.5;
        if (sel >= 0) {
          if (si === sel || ti === sel) { alpha = 0.7; lw = 2.5; }
          else if (neighbors.has(si) && neighbors.has(ti)) { alpha = 0.2; lw = 1; }
          else { alpha = 0.03; lw = 0.3; }
        }

        const ec = EDGE_COLORS[e.type] || "#64748b";

        // 发光底层
        ctx.beginPath(); ctx.moveTo(p1.sx, p1.sy); ctx.lineTo(p2.sx, p2.sy);
        ctx.strokeStyle = ec + "30";
        ctx.lineWidth = lw * 3;
        ctx.stroke();

        // 主线
        ctx.beginPath(); ctx.moveTo(p1.sx, p1.sy); ctx.lineTo(p2.sx, p2.sy);
        ctx.strokeStyle = ec + Math.round(alpha * 255).toString(16).padStart(2, "0");
        ctx.lineWidth = lw;
        ctx.stroke();
      }

      // === 节点 ===
      // 先画非高亮组（dimmed），再画高亮组
      for (const highlight of [false, true]) {
        for (const pt of pts) {
          if (isHL(pt.i) !== highlight) continue;
          const dim = sel >= 0 && !isHL(pt.i);
          const node = valid[pt.i];
          if (!node) continue;

          const deg = st.degree[pt.i] || 1;
          const baseSize = Math.max(3, 4 + (deg / maxDeg) * 18);
          const size = baseSize * zoom;

          const commIdx2 = st.community[pt.i] % COMMUNITY_PALETTE.length;
          const col = COMMUNITY_PALETTE[commIdx2];

          // 辉光
          const gr = size * (dim ? 1.5 : pt.i === sel ? 5 : 3);
          const g = ctx.createRadialGradient(pt.sx, pt.sy, 0, pt.sx, pt.sy, gr);
          if (dim) {
            g.addColorStop(0, "rgba(100,100,150,0.05)");
            g.addColorStop(1, "rgba(100,100,150,0)");
          } else {
            g.addColorStop(0, col + (pt.i === sel ? "80" : "40"));
            g.addColorStop(0.5, col + "20");
            g.addColorStop(1, col + "00");
          }
          ctx.fillStyle = g;
          ctx.beginPath(); ctx.arc(pt.sx, pt.sy, gr, 0, Math.PI * 2);
          ctx.fill();

          // 主体
          const g2 = ctx.createRadialGradient(pt.sx - size * 0.2, pt.sy - size * 0.2, 0, pt.sx, pt.sy, size);
          if (dim) {
            g2.addColorStop(0, "rgba(60,60,80,0.3)");
            g2.addColorStop(1, "rgba(30,30,50,0.3)");
          } else {
            g2.addColorStop(0, "#ffffffdd");
            g2.addColorStop(0.2, col);
            g2.addColorStop(0.8, col);
            g2.addColorStop(1, darken(col, 0.35));
          }
          ctx.fillStyle = g2;
          ctx.beginPath(); ctx.arc(pt.sx, pt.sy, size, 0, Math.PI * 2);
          ctx.fill();

          // 边框
          if (pt.i === sel) {
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2.5;
          } else if (pt.i === hov && !dim) {
            ctx.strokeStyle = col;
            ctx.lineWidth = 1.5;
          } else if (!dim) {
            ctx.strokeStyle = darken(col, 0.5);
            ctx.lineWidth = 0.8;
          }
          if (pt.i === sel || pt.i === hov || !dim) {
            ctx.beginPath(); ctx.arc(pt.sx, pt.sy, size, 0, Math.PI * 2);
            ctx.stroke();
          }
        }
      }

      // === 标签（仅高亮节点 + 大尺寸）===
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      for (const pt of pts) {
        if (sel >= 0 && !isHL(pt.i)) continue;
        const size = Math.max(3, 4 + (st.degree[pt.i] / maxDeg) * 18) * zoom;
        if (size < 6) continue;
        const label = valid[pt.i]?.label;
        if (!label) continue;

        const fs = Math.max(10, Math.min(14, 11 * zoom));
        ctx.font = `${fs}px "JetBrains Mono", monospace`;
        const tw = ctx.measureText(label).width;

        // 背景
        ctx.fillStyle = "rgba(3,3,8,0.75)";
        const ly = pt.sy - size - 2;
        ctx.beginPath();
        ctx.roundRect(pt.sx - tw / 2 - 5, ly - fs + 2, tw + 10, fs + 3, 3);
        ctx.fill();

        ctx.fillStyle = pt.i === sel ? "#ffffff" : "#e2e8f0";
        ctx.fillText(label, pt.sx, ly);
      }

      // === 顶部选中信息 ===
      if (sel >= 0 && valid[sel]) {
        const n = valid[sel];
        const commIdx2 = st.community[sel] % COMMUNITY_PALETTE.length;
        const info = `${n.label}  ·  ${n.type}  ·  ${st.degree[sel]} 连接`;
        ctx.font = '13px "JetBrains Mono", monospace';
        const tw = ctx.measureText(info).width;
        const bx = (w - tw) / 2 - 14;
        ctx.fillStyle = "rgba(3,3,8,0.9)";
        ctx.beginPath();
        ctx.roundRect(bx, 10, tw + 28, 32, 8);
        ctx.fill();
        ctx.beginPath(); ctx.arc(bx + 14, 26, 4, 0, Math.PI * 2);
        ctx.fillStyle = COMMUNITY_PALETTE[commIdx2];
        ctx.fill();
        ctx.fillStyle = "#e2e8f0";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(info, w / 2 + 4, 27);
      }

      // === 图例（右上：社区颜色） ===
      const uniqueComms = [...new Set(st.community)];
      const commNames = new Map<number, string>();
      for (let i = 0; i < valid.length; i++) {
        const c = st.community[i];
        if (!commNames.has(c)) commNames.set(c, valid[i].type);
      }
      let lx = w - 12;
      let ly = 12;
      ctx.font = '10px "JetBrains Mono", monospace';
      for (const c of uniqueComms.slice(0, 10)) {
        const col = COMMUNITY_PALETTE[c % COMMUNITY_PALETTE.length];
        const name = commNames.get(c) || `group ${c}`;
        const tw = ctx.measureText(name).width;
        const bw = tw + 24;
        ctx.fillStyle = "rgba(3,3,8,0.8)";
        ctx.beginPath();
        ctx.roundRect(lx - bw, ly, bw, 16, 4);
        ctx.fill();
        ctx.beginPath(); ctx.arc(lx - 12, ly + 8, 3, 0, Math.PI * 2);
        ctx.fillStyle = col; ctx.fill();
        ctx.fillStyle = "#94a3b8";
        ctx.textAlign = "right"; ctx.textBaseline = "middle";
        ctx.fillText(name, lx - 18, ly + 8);
        ly += 19;
      }

      // === 度分布 + 边图例（左下） ===
      ctx.textAlign = "left"; ctx.textBaseline = "bottom";
      ctx.fillStyle = "rgba(148,163,184,0.35)";
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText(`${valid.length} 节点 · ${edges.length} 边 · 最大度 ${maxDeg}`, 10, h - 8);

      // 边类型图例（左下一行，小圆点 + 类型名）
      const edgeTypes = [...new Set(edges.map(e => e.type))].slice(0, 6);
      let ex = 10;
      const ey = h - 22;
      ctx.font = '8px "JetBrains Mono", monospace';
      ctx.textBaseline = "middle";
      for (const et of edgeTypes) {
        const ec2 = EDGE_COLORS[et] || "#64748b";
        // 小线
        ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex + 12, ey);
        ctx.strokeStyle = ec2 + "99";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // 标签
        ctx.fillStyle = "rgba(148,163,184,0.5)";
        ctx.textAlign = "left";
        ctx.fillText(et, ex + 16, ey);
        ex += ctx.measureText(et).width + 28;
      }

      // 继续渲染（永远不停止，鼠标操作靠持续的 rAF 更新）
      animRef.current = requestAnimationFrame(render);
    };

    animRef.current = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animRef.current);
  }, [nodes, edges, width, height, valid, idMap]);

    // 鼠标事件
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const st = state.current;

    const getPos = (mx: number, my: number) => {
      const { zoom, offsetX, offsetY } = cam.current;
      const worldX = (mx - canvas!.width / 2) / zoom - offsetX;
      const worldY = (my - canvas!.height / 2) / zoom - offsetY;
      return { worldX, worldY };
    };

    const hitTest = (mx: number, my: number) => {
      const { zoom, offsetX, offsetY } = cam.current;
      let best = -1, bestDist = Infinity;
      for (let i = 0; i < st.x.length; i++) {
        const sx = canvas!.width / 2 + (st.x[i] + offsetX) * zoom;
        const sy = canvas!.height / 2 + (st.y[i] + offsetY) * zoom;
        const dx = mx - sx, dy = my - sy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const maxDeg = Math.max(...st.degree, 1);
        const r = Math.max(3, 4 + ((st.degree[i] || 1) / maxDeg) * 18) * zoom + 4;
        if (dist < r && dist < bestDist) { best = i; bestDist = dist; }
      }
      return best;
    };

    const triggerRender = () => {};

    const onMouseDown = (e: MouseEvent) => {
      const c = cam.current;
      const idx = hitTest(e.offsetX, e.offsetY);
      if (idx >= 0) return; // 点中节点，不拖拽
      c.dragging = true;
      c.lx = e.clientX;
      c.ly = e.clientY;
    };

    const onMouseMove = (e: MouseEvent) => {
      const c = cam.current;
      const rect = canvas!.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      if (c.dragging) {
        c.offsetX += (e.clientX - c.lx) / c.zoom;
        c.offsetY += (e.clientY - c.ly) / c.zoom;
        c.lx = e.clientX;
        c.ly = e.clientY;
        triggerRender();
        return;
      }

      const idx = hitTest(mx, my);
      if (hovIdx.current !== idx) {
        hovIdx.current = idx;
        canvas!.style.cursor = idx >= 0 ? "pointer" : "grab";
        triggerRender();
      }
    };

    const onMouseUp = () => { cam.current.dragging = false; };

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const c = cam.current;
      const delta = e.deltaY > 0 ? 0.92 : 1 / 0.92;
      c.zoom = Math.max(0.1, Math.min(10, c.zoom * delta));
      triggerRender();
    };

    const onClick = (e: MouseEvent) => {
      if (cam.current.dragging) return;
      const rect = canvas!.getBoundingClientRect();
      const idx = hitTest(e.clientX - rect.left, e.clientY - rect.top);
      if (idx >= 0) {
        selIdx.current = selIdx.current === idx ? -1 : idx;
        onNodeClick?.(valid[idx].id);
      } else {
        selIdx.current = -1;
      }
      triggerRender();
    };

    canvas.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("click", onClick);

    return () => {
      canvas.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("click", onClick);
    };
  }, [valid, idMap, onNodeClick]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ width, height, display: "block", borderRadius: "0.5rem", cursor: "grab" }}
    />
  );
}

function darken(hex: string, f: number): string {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return hex;
  return `rgb(${Math.round(parseInt(m[1], 16) * f)},${Math.round(parseInt(m[2], 16) * f)},${Math.round(parseInt(m[3], 16) * f)})`;
}
