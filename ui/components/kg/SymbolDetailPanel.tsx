"use client";

import * as React from "react";
import {
  ArrowLeft,
  ArrowRight,
  AlertTriangle,
  BookOpen,
  Network,
  Layers,
  Workflow,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ProcessPanel, type ProcessInfo } from "@/components/kg/ProcessPanel";
import { getSymbolContext, getImpactAnalysis, searchByType } from "@/lib/api/code-analysis";
import type {
  SearchResult,
  SymbolContext,
  ImpactResult,
} from "@/lib/api/code-analysis";

const TYPE_COLORS: Record<string, string> = {
  class: "bg-blue-100 text-blue-700",
  function: "bg-green-100 text-green-700",
  method: "bg-teal-100 text-teal-700",
  variable: "bg-purple-100 text-purple-700",
  file: "bg-gray-100 text-gray-700",
  folder: "bg-orange-100 text-orange-700",
  module: "bg-indigo-100 text-indigo-700",
  interface: "bg-pink-100 text-pink-700",
  route: "bg-sky-100 text-sky-700",
  tool: "bg-lime-100 text-lime-700",
  process: "bg-rose-100 text-rose-700",
  community: "bg-amber-100 text-amber-700",
};

const RISK_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
  none: "bg-gray-100 text-gray-500",
};

type TabKey = "context" | "processes";

interface SymbolDetailPanelProps {
  projectId: string;
  selectedSymbol: SearchResult | null;
  processes: ProcessInfo[];
  onGraphDataReady?: (nodes: any[], edges: any[]) => void;
}

export function SymbolDetailPanel({
  projectId,
  selectedSymbol,
  processes,
  onGraphDataReady,
}: SymbolDetailPanelProps) {
  const [symbolContext, setSymbolContext] = React.useState<SymbolContext | null>(null);
  const [contextLoading, setContextLoading] = React.useState(false);
  const [impactResult, setImpactResult] = React.useState<ImpactResult | null>(null);
  const [impactLoading, setImpactLoading] = React.useState(false);
  const [impactDirection, setImpactDirection] = React.useState("upstream");
  const [activeTab, setActiveTab] = React.useState<TabKey>("context");

  // 加载符号上下文
  React.useEffect(() => {
    if (!selectedSymbol) return;
    const loadContext = async () => {
      setContextLoading(true);
      setImpactResult(null);
      setActiveTab("context");
      try {
        const res = await getSymbolContext(projectId, selectedSymbol.name);
        if (res.success && res.data) {
          setSymbolContext(res.data);

          // 构建局部图谱数据
          const nodeMap = new Map<string, { id: string; label: string; type: string; community?: string }>();
          const edges: Array<{ source: string; target: string; type: string }> = [];
          const mainId = res.data.node.id;

          let mainCommunity: string | undefined;
          for (const r of res.data.relationships) {
            if (r.type === "MEMBER_OF") {
              mainCommunity = r.target;
              break;
            }
          }
          nodeMap.set(mainId, {
            id: mainId,
            label: res.data.node.name,
            type: res.data.node.type,
            community: mainCommunity,
          });

          for (const r of res.data.relationships) {
            if (["CALLS", "EXTENDS", "METHOD_OVERRIDES", "MEMBER_OF"].includes(r.type)) {
              const sLabel = r.source.split("::").pop() || r.source;
              const tLabel = r.target.split("::").pop() || r.target;
              if (!nodeMap.has(r.source)) {
                nodeMap.set(r.source, { id: r.source, label: sLabel, type: "function" });
              }
              if (!nodeMap.has(r.target)) {
                nodeMap.set(r.target, { id: r.target, label: tLabel, type: "function" });
              }
              if (r.type !== "MEMBER_OF") {
                edges.push({ source: r.source, target: r.target, type: r.type });
              }
            }
          }

          const allNodes = Array.from(nodeMap.values()).slice(0, 40);
          onGraphDataReady?.(allNodes, edges.slice(0, 60));
        }
      } catch {}
      setContextLoading(false);
    };
    loadContext();
  }, [selectedSymbol, projectId, onGraphDataReady]);

  const handleImpact = async (symbol: string) => {
    setImpactLoading(true);
    try {
      const res = await getImpactAnalysis(projectId, symbol, impactDirection);
      if (res.success) setImpactResult(res.data);
    } catch {}
    setImpactLoading(false);
  };

  if (!selectedSymbol) return null;

  if (contextLoading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!symbolContext) return null;

  return (
    <div className="space-y-6 max-w-4xl">
      {/* 符号头部 */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <Badge className={TYPE_COLORS[symbolContext.node.type] || ""}>
            {symbolContext.node.type}
          </Badge>
          <h2 className="text-xl font-bold">{symbolContext.node.name}</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          {symbolContext.node.file_path || "?"}
          {symbolContext.node.start_line ? `#${symbolContext.node.start_line}` : ""}
        </p>
      </div>

      {/* 调用者/被调用概览 */}
      <div className="grid grid-cols-2 gap-4">
        <CallerView relationships={symbolContext.relationships} nodeId={symbolContext.node.id} />
        <CalleeView relationships={symbolContext.relationships} nodeId={symbolContext.node.id} />
      </div>

      {/* 标签页切换 */}
      <div className="flex gap-2 mb-4">
        {[
          { key: "context" as TabKey, label: "上下文" },
          { key: "processes" as TabKey, label: "执行流" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3 py-1 text-xs rounded-full border transition-colors ${
              activeTab === tab.key
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border hover:bg-muted"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "context" && (
        <>
          {/* 调用关系详情 */}
          <div className="grid grid-cols-2 gap-4">
            <CallerView relationships={symbolContext.relationships} nodeId={symbolContext.node.id} />
            <CalleeView relationships={symbolContext.relationships} nodeId={symbolContext.node.id} />
          </div>

          {/* 方法重写链 */}
          <MethodOverrideChain relationships={symbolContext.relationships} nodeId={symbolContext.node.id} />

          {/* 影响分析 */}
          <div className="rounded-lg border p-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="flex items-center gap-2 text-sm font-medium">
                <AlertTriangle className="h-4 w-4 text-amber-500" /> 影响分析
              </h4>
              <div className="flex gap-2">
                {["upstream", "downstream", "both"].map((d) => (
                  <button
                    key={d}
                    onClick={() => setImpactDirection(d)}
                    className={`px-2 py-0.5 text-xs rounded-full border ${
                      d === impactDirection
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border hover:bg-muted"
                    }`}
                  >
                    {d === "upstream" ? "上游" : d === "downstream" ? "下游" : "双向"}
                  </button>
                ))}
              </div>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleImpact(symbolContext.node.name)}
              disabled={impactLoading}
            >
              {impactLoading ? (
                <><Loader2 className="mr-1 h-3 w-3 animate-spin" />分析中</>
              ) : (
                <><Network className="mr-1 h-3 w-3" />开始分析</>
              )}
            </Button>
            {impactResult && (
              <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">风险:</span>
                  <Badge className={RISK_COLORS[impactResult.risk] || ""}>
                    {impactResult.risk === "high" ? "高风险" :
                     impactResult.risk === "medium" ? "中风险" :
                     impactResult.risk === "low" ? "低风险" : "无风险"}
                  </Badge>
                </div>
                {impactResult.upstream && (
                  <div>
                    <p className="text-xs font-medium mb-1">上游影响（{impactResult.upstream.length} 处）:</p>
                    <div className="flex flex-wrap gap-1">
                      {impactResult.upstream.slice(0, 15).map((name) => (
                        <Badge key={name} variant="secondary" className="text-[10px]">{name}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {impactResult.downstream && (
                  <div>
                    <p className="text-xs font-medium mb-1">下游依赖（{impactResult.downstream.length} 处）:</p>
                    <div className="flex flex-wrap gap-1">
                      {impactResult.downstream.slice(0, 15).map((name) => (
                        <Badge key={name} variant="secondary" className="text-[10px]">{name}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}

      {activeTab === "processes" && (
        <div className="rounded-lg border p-4">
          <h4 className="flex items-center gap-2 text-sm font-medium mb-3">
            <Workflow className="h-4 w-4 text-rose-500" /> 执行流
          </h4>
          <ProcessPanel
            processes={processes}
            selectedId={null}
            onSelect={(id) => {
              console.log("Selected process:", id);
            }}
          />
        </div>
      )}

      {/* 源码 */}
      {symbolContext.source && (
        <div className="rounded-lg border">
          <div className="flex items-center gap-2 border-b px-4 py-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs font-medium">
              源码 {symbolContext.source.start_line}-{symbolContext.source.end_line} 行
            </span>
          </div>
          <pre className="overflow-x-auto p-4 text-xs leading-relaxed">
            {symbolContext.source.content.split("\n").map((line, i) => (
              <div key={i} className="flex">
                <span className="w-8 text-right text-muted-foreground select-none mr-3 shrink-0">
                  {symbolContext.source!.start_line + i}
                </span>
                <span className="whitespace-pre">{line}</span>
              </div>
            ))}
          </pre>
        </div>
      )}
    </div>
  );
}

// ── 子组件 ──

function CallerView({
  relationships,
  nodeId,
}: {
  relationships: Array<{ id: string; source: string; target: string; type: string }>;
  nodeId: string;
}) {
  const callers = relationships.filter(
    (r) => r.type === "CALLS" && r.target === nodeId
  );
  return (
    <div className="rounded-lg border p-4">
      <h4 className="flex items-center gap-2 text-sm font-medium mb-2">
        <ArrowLeft className="h-4 w-4 text-blue-500" /> 调用者
      </h4>
      {callers.length > 0 ? (
        <ul className="space-y-1">
          {callers.slice(0, 10).map((r) => (
            <li key={r.id} className="text-xs text-muted-foreground truncate">
              {r.source.split("::").pop() || r.source}
            </li>
          ))}
          {callers.length > 10 && (
            <li className="text-xs text-muted-foreground">
              ...还有 {callers.length - 10} 个
            </li>
          )}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">暂无调用者</p>
      )}
    </div>
  );
}

function CalleeView({
  relationships,
  nodeId,
}: {
  relationships: Array<{ id: string; source: string; target: string; type: string }>;
  nodeId: string;
}) {
  const callees = relationships.filter(
    (r) => r.type === "CALLS" && r.source === nodeId
  );
  return (
    <div className="rounded-lg border p-4">
      <h4 className="flex items-center gap-2 text-sm font-medium mb-2">
        <ArrowRight className="h-4 w-4 text-green-500" /> 被调用
      </h4>
      {callees.length > 0 ? (
        <ul className="space-y-1">
          {callees.slice(0, 10).map((r) => (
            <li key={r.id} className="text-xs text-muted-foreground truncate">
              {r.target.split("::").pop() || r.target}
            </li>
          ))}
          {callees.length > 10 && (
            <li className="text-xs text-muted-foreground">
              ...还有 {callees.length - 10} 个
            </li>
          )}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">无依赖</p>
      )}
    </div>
  );
}

function MethodOverrideChain({
  relationships,
  nodeId,
}: {
  relationships: Array<{ id: string; source: string; target: string; type: string }>;
  nodeId: string;
}) {
  const overrides = relationships.filter(
    (r) => r.type === "METHOD_OVERRIDES" && r.target === nodeId
  );
  if (overrides.length === 0) return null;

  return (
    <div className="rounded-lg border p-4">
      <h4 className="flex items-center gap-2 text-sm font-medium mb-2">
        <Layers className="h-4 w-4 text-purple-500" /> 方法重写链
      </h4>
      <p className="text-xs text-muted-foreground mb-2">
        以下 {overrides.length} 个子类重写了此方法，修改会影响它们
      </p>
      <div className="flex flex-wrap gap-1">
        {overrides.slice(0, 15).map((r) => (
          <Badge key={r.id} variant="secondary" className="text-[10px]">
            {r.source.split("::").pop() || r.source}
          </Badge>
        ))}
      </div>
    </div>
  );
}
