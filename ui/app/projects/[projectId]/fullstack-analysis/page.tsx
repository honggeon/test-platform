/**
 * 全栈分析页面
 *
 * Tab 重构版 — 将功能按标签页分组:
 *   概览 / 图谱探索 / 搜索 / 变更影响 / 执行流
 *
 * AI 功能集成：AI 设置顶栏按钮 → 侧滑面板（模型设置 + AI 对话）
 */

"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { MainLayout } from "@/components/layout";
import { useLanguage } from "@/providers/LanguageProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Code2,
  Search,
  Loader2,
  AlertTriangle,
  Network,
  BarChart3,
  Workflow,
  Settings,
  Globe,
  Wrench,
  Layers,
  ArrowLeft,
  Brain,
  MessageSquare,
  X,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

import { CodeRepoConfig } from "@/components/kg/CodeRepoConfig";
import { AnalysisSummary } from "@/components/kg/AnalysisSummary";
import { ChangeImpactAnalyzer } from "@/components/kg/ChangeImpactAnalyzer";
import { SymbolDetailPanel } from "@/components/kg/SymbolDetailPanel";
import { GraphExplorer } from "@/components/kg/GraphExplorer";
import { ProcessPanel, type ProcessInfo } from "@/components/kg/ProcessPanel";
import { ProcessTracePanel } from "@/components/kg/ProcessTracePanel";
import type { CommunityInfo } from "@/components/kg/CommunityFilter";
import { AIChatContainer } from "@/components/langgraph/AIChatContainer";
import { ClientProvider } from "@/providers/ClientProvider";
import { Assistant } from "@langchain/langgraph-sdk";
import { getDeploymentUrl } from "@/lib/langgraph/config";

import {
  getCodeRepoStatus,
  configureCodeRepo,
  triggerCodeAnalysis,
  type CodeRepoStatus,
} from "@/lib/api/code-repo";
import {
  searchCode,
  searchByType,
  getGraphData,
  getStaleness,
  type SearchResult,
  type StalenessReport,
} from "@/lib/api/code-analysis";

import {
  type LLMProvider,
  type LLMConfigData,
  PROVIDER_META,
  getLLMConfig,
  saveLLMConfig,
} from "@/lib/api/llm-config";

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

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  route: Globe,
  tool: Wrench,
  process: Workflow,
  community: Layers,
};

/** 内联 LLM 设置表单（非 Dialog 版，用于侧滑面板） */
function InlineLLMConfig({ projectId }: { projectId: string }) {
  const [provider, setProvider] = React.useState<LLMProvider>("deepseek");
  const [modelName, setModelName] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [showApiKey, setShowApiKey] = React.useState(false);
  const [baseUrl, setBaseUrl] = React.useState("");
  const [temperature, setTemperature] = React.useState<number | null>(0.7);
  const [maxTokens, setMaxTokens] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [saveStatus, setSaveStatus] = React.useState<"idle" | "success" | "error">("idle");
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!projectId) return;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const res = await getLLMConfig(projectId);
        if (res.success && res.data) {
          const cfg = res.data;
          setProvider(cfg.provider as LLMProvider);
          setModelName(cfg.model_name || "");
          setApiKey(cfg.api_key || "");
          setBaseUrl(cfg.base_url || "");
          setTemperature(cfg.temperature);
          setMaxTokens(cfg.max_tokens);
        }
      } catch {
        setProvider("deepseek");
        setModelName("");
        setApiKey("");
        setBaseUrl("");
        setTemperature(0.7);
        setMaxTokens(null);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [projectId]);

  const handleProviderChange = (p: LLMProvider) => {
    setProvider(p);
    setSaveStatus("idle");
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveStatus("idle");
    setError("");
    try {
      const meta = PROVIDER_META[provider];
      const data: LLMConfigData = {
        provider,
        model_name: modelName.trim() || meta.defaultModel,
        api_key: meta.needApiKey ? apiKey.trim() || null : null,
        base_url: meta.needBaseUrl ? baseUrl.trim() || null : null,
        temperature,
        max_tokens: maxTokens,
      };
      await saveLLMConfig(projectId, data);
      setSaveStatus("success");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
      setSaveStatus("error");
    } finally {
      setSaving(false);
    }
  };

  const meta = PROVIDER_META[provider];

  return (
    <div className="p-5 space-y-5">
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">加载配置中...</span>
        </div>
      ) : (
        <>
          {/* Provider 选择 */}
          <div className="space-y-2">
            <Label className="text-xs">模型提供商</Label>
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(PROVIDER_META) as LLMProvider[]).map((p) => (
                <Card
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  className={`cursor-pointer p-2.5 transition-all border-2 ${
                    provider === p
                      ? "border-primary bg-primary/5"
                      : "border-transparent hover:border-border"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-base">{PROVIDER_META[p].icon}</span>
                    <span className="text-xs font-medium">
                      {PROVIDER_META[p].label}
                    </span>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          {/* 模型名称 */}
          <div className="space-y-1.5">
            <Label htmlFor="model-name" className="text-xs">模型名称</Label>
            <Input
              id="model-name"
              value={modelName}
              onChange={(e) => {
                setModelName(e.target.value);
                setSaveStatus("idle");
              }}
              placeholder={meta.placeholder}
              className="font-mono text-xs"
            />
            <p className="text-[10px] text-muted-foreground">
              默认: {meta.defaultModel}
            </p>
          </div>

          {/* API Key */}
          {meta.needApiKey && (
            <div className="space-y-1.5">
              <Label htmlFor="api-key" className="text-xs">API Key</Label>
              <div className="relative">
                <Input
                  id="api-key"
                  type={showApiKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setSaveStatus("idle");
                  }}
                  placeholder={`输入 ${meta.label} API Key`}
                  className="pr-10 font-mono text-xs"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground transition-colors"
                  tabIndex={-1}
                >
                  {showApiKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>
          )}

          {/* Base URL */}
          {meta.needBaseUrl && (
            <div className="space-y-1.5">
              <Label htmlFor="base-url" className="text-xs">
                Base URL <span className="text-muted-foreground font-normal">(可选)</span>
              </Label>
              <Input
                id="base-url"
                value={baseUrl}
                onChange={(e) => {
                  setBaseUrl(e.target.value);
                  setSaveStatus("idle");
                }}
                placeholder={meta.baseUrlPlaceholder}
                className="font-mono text-xs"
              />
              {meta.baseUrlHelper && (
                <p className="text-[10px] text-muted-foreground">{meta.baseUrlHelper}</p>
              )}
            </div>
          )}

          {/* 温度参数 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="temperature" className="text-xs">温度参数 (Temperature)</Label>
              <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                {temperature ?? "默认"}
              </span>
            </div>
            <input
              id="temperature"
              type="range"
              min={0}
              max={2}
              step={0.1}
              value={temperature ?? 0.7}
              onChange={(e) => {
                setTemperature(parseFloat(e.target.value));
                setSaveStatus("idle");
              }}
              className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>精确 (0)</span>
              <span>平衡 (1)</span>
              <span>创意 (2)</span>
            </div>
          </div>

          {/* 最大 Token */}
          <div className="space-y-1.5">
            <Label htmlFor="max-tokens" className="text-xs">
              最大 Token 数 <span className="text-muted-foreground font-normal">(可选)</span>
            </Label>
            <Input
              id="max-tokens"
              type="number"
              value={maxTokens ?? ""}
              onChange={(e) => {
                const val = e.target.value;
                setMaxTokens(val ? parseInt(val) : null);
                setSaveStatus("idle");
              }}
              placeholder="不限制"
              className="font-mono text-xs"
            />
          </div>

          {/* 隐私提示 */}
          <div className="rounded-lg border bg-muted/50 p-2.5">
            <div className="flex gap-2 items-start">
              <Settings className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
              <p className="text-[10px] text-muted-foreground leading-relaxed">
                API Key 保存在后端数据库中。Agent 运行时在后端直接调用 LLM Provider。
              </p>
            </div>
          </div>

          {/* 错误提示 */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-2.5 text-red-600 text-xs">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />
              {error}
            </div>
          )}

          {/* 操作按钮 */}
          <div className="flex items-center justify-between">
            <div>
              {saveStatus === "success" && (
                <span className="flex items-center gap-1 text-xs text-green-600 animate-in fade-in">
                  <Check className="h-3.5 w-3.5" />已保存
                </span>
              )}
            </div>
            <Button size="sm" onClick={handleSave} disabled={saving}>
              {saving ? (
                <><Loader2 className="mr-1 h-3 w-3 animate-spin" />保存中</>
              ) : (
                "保存配置"
              )}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

export default function FullStackAnalysisPage() {
  const params = useParams();
  const projectId = params?.projectId as string;
  const { t } = useLanguage();

  // ── Tab ──
  const [activeTab, setActiveTab] = React.useState("overview");

  // ── 仓库状态 ──
  const [repoStatus, setRepoStatus] = React.useState<CodeRepoStatus | null>(null);
  const [staleness, setStaleness] = React.useState<StalenessReport | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [repoUrl, setRepoUrl] = React.useState("");
  const [repoBranch, setRepoBranch] = React.useState("main");
  const [analyzing, setAnalyzing] = React.useState(false);
  const [error, setError] = React.useState("");
  const [analysisStats, setAnalysisStats] = React.useState<Record<string, number> | null>(null);

  // ── 搜索 ──
  const [searchQuery, setSearchQuery] = React.useState("");
  const [searchType, setSearchType] = React.useState("");
  const [searchResults, setSearchResults] = React.useState<SearchResult[]>([]);
  const [searching, setSearching] = React.useState(false);

  // ── 选中符号 ──
  const [selectedSymbol, setSelectedSymbol] = React.useState<SearchResult | null>(null);
  const [selectedProcessId, setSelectedProcessId] = React.useState<string | null>(null);

  // ── 图谱 ──
  const [graphNodes, setGraphNodes] = React.useState<Array<{ id: string; label: string; type: string; community?: string }>>([]);
  const [graphEdges, setGraphEdges] = React.useState<Array<{ source: string; target: string; type: string }>>([]);
  const [communities, setCommunities] = React.useState<CommunityInfo[]>([]);
  const [processes, setProcesses] = React.useState<ProcessInfo[]>([]);

  // ── 图谱尺寸 ──
  const [canvasSize, setCanvasSize] = React.useState({ w: 600, h: 400 });
  const panelRef = React.useRef<HTMLDivElement>(null);

  // ── AI 综合面板（设置 + 聊天） ──
  const [aiPanelOpen, setAiPanelOpen] = React.useState(false);
  const [aiSubTab, setAiSubTab] = React.useState<"settings" | "chat">("settings");
  const [assistant, setAssistant] = React.useState<Assistant | null>(null);

  const hasAnalysis = repoStatus?.analyzed;

  // ── 初始化 Assistant ──
  React.useEffect(() => {
    const initAssistant = async () => {
      try {
        const mockAssistant: Assistant = {
          assistant_id: "code_analysis_agent",
          graph_id: "code_analysis_agent",
          config: { configurable: { project_identifier: projectId } },
          context: {},
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          metadata: {},
          version: 1,
          name: "代码分析助手",
        };
        setAssistant(mockAssistant);
      } catch (error) {
        console.error("Failed to initialize code analysis assistant:", error);
      }
    };
    if (projectId) initAssistant();
  }, [projectId]);

  // ── 加载仓库状态 ──
  const loadRepoStatus = React.useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await getCodeRepoStatus(projectId);
      if (res.success && res.data) {
        setRepoStatus(res.data);
        setAnalyzing(!!res.data.analyzing);
        if (res.data.repo_url) setRepoUrl(res.data.repo_url);
        if (res.data.repo_branch) setRepoBranch(res.data.repo_branch);
        if (res.data.analyzed && res.data.message) {
          parseStatsFromMessage(res.data.message);
        }
      }
    } catch {} finally { setLoading(false); }
  }, [projectId]);

  const parseStatsFromMessage = React.useCallback((msg: string) => {
    const fileMatch = msg.match(/(\d+)\s*文件/);
    const folderMatch = msg.match(/(\d+)\s*目录/);
    const nodeMatch = msg.match(/(\d+)\s*节点/);
    const relMatch = msg.match(/(\d+)\s*关系/);
    setAnalysisStats({
      file: parseInt(fileMatch?.[1] || "0"),
      folder: parseInt(folderMatch?.[1] || "0"),
      node: parseInt(nodeMatch?.[1] || "0"),
      relationship: parseInt(relMatch?.[1] || "0"),
    });
  }, []);

  // ── 加载社区和执行流 ──
  const loadCommunitiesAndProcesses = async () => {
    try {
      const [commRes, procRes] = await Promise.all([
        searchByType(projectId, "community", 100),
        searchByType(projectId, "process", 100),
      ]);
      if (commRes.success && commRes.data) {
        const palette = [
          "#3b82f6", "#22c55e", "#f59e0b", "#ec4899", "#8b5cf6",
          "#14b8a6", "#f97316", "#6366f1", "#84cc16", "#06b6d4",
        ];
        setCommunities(
          commRes.data.map((c, i) => ({
            id: c.node_id,
            name: c.name,
            label: c.properties?.heuristic_label || c.name,
            symbol_count: c.properties?.symbol_count || 0,
            color: palette[i % palette.length],
          }))
        );
      }
      if (procRes.success && procRes.data) {
        setProcesses(
          procRes.data.map((p) => ({
            id: p.node_id,
            name: p.name,
            process_type: p.properties?.process_type || "function",
            step_count: p.properties?.step_count || 0,
            entry_point: p.properties?.entry_point_id,
          }))
        );
      }
    } catch {}
  };

  React.useEffect(() => { loadRepoStatus(); }, [loadRepoStatus]);

  React.useEffect(() => {
    if (repoStatus?.analyzed) {
      loadCommunitiesAndProcesses();
    }
  }, [repoStatus?.analyzed, projectId]);

  // ── 分析轮询 ──
  React.useEffect(() => {
    if (!analyzing && !repoStatus?.analyzing) return;
    const interval = setInterval(async () => {
      try {
        const res = await getCodeRepoStatus(projectId);
        if (res.success && res.data) {
          setRepoStatus(res.data);
          if (res.data.analyzed && res.data.message && !res.data.message.includes("失败")) {
            parseStatsFromMessage(res.data.message);
          }
          if (res.data.current_step === "失败") {
            setError(res.data.message || "分析失败");
            setAnalyzing(false);
          } else if (!res.data.analyzing) {
            setAnalyzing(false);
          }
        }
      } catch {}
    }, 2000);
    return () => clearInterval(interval);
  }, [analyzing, repoStatus?.analyzing, projectId, parseStatsFromMessage]);

  // ── 仓库操作 ──
  const handleSaveConfig = async () => {
    if (!repoUrl.trim()) return;
    setError("");
    try {
      const res = await configureCodeRepo(projectId, {
        repo_url: repoUrl.trim(), repo_branch: repoBranch || "main",
      });
      if (res.success) await loadRepoStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    }
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError("");
    try {
      // 先保存仓库配置，再触发分析
      await configureCodeRepo(projectId, {
        repo_url: repoUrl.trim(), repo_branch: repoBranch || "main",
      });
      const res = await triggerCodeAnalysis(projectId);
      if (res.success) {
        setRepoStatus(res.data);
        setAnalyzing(!!res.data.analyzing);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "分析失败");
      setAnalyzing(false);
    }
  };

  // ── 搜索 ──
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSelectedSymbol(null);
    setGraphNodes([]);
    setGraphEdges([]);
    try {
      const res = await searchCode(projectId, searchQuery.trim(), searchType || undefined, 20, "hybrid");
      if (res.success) setSearchResults(res.data || []);
    } catch {}
    setSearching(false);
  };

  // ── 图谱 ──
  const handleExploreGraph = async () => {
    setActiveTab("graph");
    setSelectedSymbol(null);
    try {
      const res = await getGraphData(projectId, 300, 800);
      if (res.success && res.data) {
        setGraphNodes(res.data.nodes.map((n) => ({ id: n.id, label: n.name, type: n.type })));
        setGraphEdges(res.data.edges.map((e) => ({ source: e.source, target: e.target, type: e.type })));
      }
    } catch {}
  };

  const handleGraphNodeClick = (nodeId: string) => {
    const node = graphNodes.find((n) => n.id === nodeId);
    if (node) {
      const result = searchResults.find((r) => r.node_id === node.id || r.name === node.label);
      if (result) setSelectedSymbol(result);
    }
  };

  // ── 图谱画布尺寸 ──
  React.useEffect(() => {
    const el = panelRef.current;
    if (!el) return;
    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      const h = Math.max(600, window.innerHeight - 240);
      setCanvasSize({ w: Math.max(800, rect.width - 48), h });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(el);
    window.addEventListener("resize", updateSize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateSize);
    };
  }, []);

  // ── 切换到图谱标签页时自动加载 ──
  const graphLoadingRef = React.useRef(false);
  React.useEffect(() => {
    if (activeTab !== "graph" || !hasAnalysis || graphNodes.length > 0 || graphLoadingRef.current) return;
    graphLoadingRef.current = true;
    getGraphData(projectId, 300, 800)
      .then((res) => {
        if (res.success && res.data) {
          setGraphNodes(res.data.nodes.map((n) => ({ id: n.id, label: n.name, type: n.type })));
          setGraphEdges(res.data.edges.map((e) => ({ source: e.source, target: e.target, type: e.type })));
        }
      })
      .catch(() => {})
      .finally(() => { graphLoadingRef.current = false; });
  }, [activeTab, hasAnalysis, projectId, graphNodes.length]);

  // ── 从 SymbolDetailPanel 接收图谱数据 ──
  const handleSymbolGraphData = (nodes: typeof graphNodes, edges: typeof graphEdges) => {
    if (nodes.length > 0) {
      setGraphNodes(nodes);
      setGraphEdges(edges);
    }
  };

  // ── 打开 AI 面板 ──
  const openAiPanel = (tab: "settings" | "chat" = "settings") => {
    setAiSubTab(tab);
    setAiPanelOpen(true);
  };

  return (
    <MainLayout>
      <div className="flex h-full flex-col">
        {/* ── 顶栏 ── */}
        <div className="flex items-center justify-between border-b bg-white px-6 py-3 shadow-sm shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
              <Code2 className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-base font-semibold">全栈分析</h1>
              <p className="text-[10px] text-muted-foreground -mt-0.5">
                代码知识图谱 · 调用链分析 · 变更影响
              </p>
            </div>
            {hasAnalysis && (
              <Badge
                variant="outline"
                className="ml-2 bg-green-50 text-green-700 border-green-200 text-[10px]"
              >
                已分析
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {hasAnalysis && assistant && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => openAiPanel("chat")}
                className="gap-1.5"
              >
                <MessageSquare className="h-3.5 w-3.5" />
                AI 对话
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={() => openAiPanel("settings")}
              className="gap-1.5"
            >
              <Settings className="h-3.5 w-3.5" />
              AI 设置
            </Button>
          </div>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* ── 左侧面板 (w-64) ── */}
          <div className="flex w-64 flex-col border-r overflow-y-auto shrink-0 bg-white">
            <CodeRepoConfig
              projectId={projectId}
              repoStatus={repoStatus}
              loading={loading}
              repoUrl={repoUrl}
              repoBranch={repoBranch}
              analyzing={analyzing}
              error={error}
              staleness={staleness}
              onRepoUrlChange={setRepoUrl}
              onRepoBranchChange={setRepoBranch}
              onSave={handleSaveConfig}
              onAnalyze={handleAnalyze}
            />

            {hasAnalysis && (
              <div className="p-3 space-y-1">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider px-1 font-medium">
                  快速操作
                </p>
                <button
                  onClick={() => setActiveTab("graph")}
                  className="w-full text-left text-xs px-2 py-1.5 rounded-md hover:bg-muted transition-colors flex items-center gap-2"
                >
                  <Network className="h-3 w-3 text-blue-500" /> 探索图谱
                </button>
                <button
                  onClick={() => setActiveTab("change-impact")}
                  className="w-full text-left text-xs px-2 py-1.5 rounded-md hover:bg-muted transition-colors flex items-center gap-2"
                >
                  <AlertTriangle className="h-3 w-3 text-amber-500" /> 变更影响
                </button>
                <button
                  onClick={() => setActiveTab("processes")}
                  className="w-full text-left text-xs px-2 py-1.5 rounded-md hover:bg-muted transition-colors flex items-center gap-2"
                >
                  <Workflow className="h-3 w-3 text-rose-500" /> 执行流
                </button>
              </div>
            )}
          </div>

          {/* ── 右侧主面板 ── */}
          <div ref={panelRef} className="flex-1 overflow-y-auto p-6 bg-muted/20">
            {!hasAnalysis && !selectedSymbol && !selectedProcessId ? (
              <div className="flex h-full items-center justify-center">
                <div className="max-w-sm text-center">
                  <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/5">
                    <Code2 className="h-8 w-8 text-primary/40" />
                  </div>
                  <h3 className="mt-4 text-lg font-medium">代码知识图谱</h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    先在左侧配置代码仓库地址并开始分析
                  </p>
                </div>
              </div>
            ) : hasAnalysis && !selectedSymbol && !selectedProcessId ? (
              <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                <TabsList className="mb-2">
                  <TabsTrigger value="overview" className="gap-1.5 text-xs">
                    <BarChart3 className="h-3.5 w-3.5" />概览
                  </TabsTrigger>
                  <TabsTrigger value="graph" className="gap-1.5 text-xs">
                    <Network className="h-3.5 w-3.5" />图谱探索
                  </TabsTrigger>
                  <TabsTrigger value="search" className="gap-1.5 text-xs">
                    <Search className="h-3.5 w-3.5" />搜索
                  </TabsTrigger>
                  <TabsTrigger value="change-impact" className="gap-1.5 text-xs">
                    <AlertTriangle className="h-3.5 w-3.5" />变更影响
                  </TabsTrigger>
                  <TabsTrigger value="processes" className="gap-1.5 text-xs">
                    <Workflow className="h-3.5 w-3.5" />执行流
                  </TabsTrigger>
                </TabsList>

                {/* ── 概览 ── */}
                <TabsContent value="overview" className="mt-6">
                  <AnalysisSummary
                    projectId={projectId}
                    analysisStats={analysisStats}
                    exploringGraph={false}
                    onExploreGraph={handleExploreGraph}
                  />
                </TabsContent>

                {/* ── 图谱探索 ── */}
                <TabsContent value="graph" className="mt-6">
                  {graphNodes.length > 0 ? (
                    <GraphExplorer
                      nodes={graphNodes}
                      edges={graphEdges}
                      width={canvasSize.w}
                      height={canvasSize.h}
                      communities={communities}
                      onNodeClick={handleGraphNodeClick}
                      onClose={() => { setGraphNodes([]); setGraphEdges([]); }}
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-sm text-muted-foreground">
                      <Loader2 className="h-6 w-6 animate-spin mb-2" />
                      <p>正在加载知识图谱数据...</p>
                    </div>
                  )}
                </TabsContent>

                {/* ── 搜索 ── */}
                <TabsContent value="search" className="mt-6">
                  {selectedSymbol ? (
                    <>
                      <button
                        onClick={() => setSelectedSymbol(null)}
                        className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <ArrowLeft className="h-3 w-3" /> 返回搜索结果
                      </button>
                      <SymbolDetailPanel
                        projectId={projectId}
                        selectedSymbol={selectedSymbol}
                        processes={processes}
                        onGraphDataReady={handleSymbolGraphData}
                      />
                    </>
                  ) : (
                    <div className="space-y-4 max-w-2xl">
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            placeholder="搜索类名、函数名、方法名..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                            className="text-sm pl-9"
                          />
                        </div>
                        <Button
                          size="sm"
                          onClick={handleSearch}
                          disabled={!searchQuery.trim() || searching}
                        >
                          {searching ? (
                            <><Loader2 className="mr-1 h-3 w-3 animate-spin" />搜索</>
                          ) : (
                            "搜索"
                          )}
                        </Button>
                      </div>

                      {/* 类型过滤 */}
                      <div className="flex flex-wrap gap-1">
                        {["", "class", "function", "method", "file", "interface", "route"].map((t) => (
                          <button
                            key={t}
                            onClick={() => setSearchType(t === searchType ? "" : t)}
                            className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                              t === searchType
                                ? "bg-primary text-primary-foreground border-primary"
                                : "border-border hover:bg-muted"
                            }`}
                          >
                            {t || "全部"}
                          </button>
                        ))}
                      </div>

                      {/* 搜索结果 */}
                      {searchResults.length === 0 && !searching && (
                        <div className="py-12 text-center">
                          <Search className="mx-auto h-8 w-8 text-muted-foreground/30 mb-2" />
                          <p className="text-sm text-muted-foreground">
                            输入关键词开始搜索代码符号
                          </p>
                        </div>
                      )}
                      <div className="space-y-1">
                        {searchResults.map((r) => {
                          const Icon = TYPE_ICONS[r.type];
                          return (
                            <button
                              key={r.node_id}
                              onClick={() => setSelectedSymbol(r)}
                              className={`w-full text-left p-3 rounded-lg text-sm transition-all hover:bg-muted border ${
                                selectedSymbol?.node_id === r.node_id
                                  ? "bg-muted ring-1 ring-primary/40 border-primary/20"
                                  : "border-border/60"
                              }`}
                            >
                              <div className="flex items-center gap-2">
                                <span
                                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                    TYPE_COLORS[r.type] || "bg-gray-100"
                                  }`}
                                >
                                  {Icon && <Icon className="h-3 w-3" />}
                                  {r.type}
                                </span>
                                <span className="font-medium truncate">{r.name}</span>
                              </div>
                              {r.file_path && (
                                <p className="mt-0.5 text-[10px] text-muted-foreground truncate pl-1 font-mono">
                                  {r.file_path}
                                  {r.start_line ? `#${r.start_line}` : ""}
                                </p>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </TabsContent>

                {/* ── 变更影响 ── */}
                <TabsContent value="change-impact" className="mt-6 max-w-2xl">
                  <ChangeImpactAnalyzer
                    projectId={projectId}
                    hasAnalysis={hasAnalysis}
                  />
                </TabsContent>

                {/* ── 执行流 ── */}
                <TabsContent value="processes" className="mt-6 max-w-2xl">
                  <div className="rounded-lg border bg-white p-4">
                    <h3 className="flex items-center gap-2 text-sm font-medium mb-4">
                      <Workflow className="h-4 w-4 text-rose-500" /> 执行流
                    </h3>
                    <ProcessPanel
                      processes={processes}
                      selectedId={selectedProcessId}
                      onSelect={(id) => {
                        if (id) {
                          setSelectedProcessId(id);
                          setSelectedSymbol(null);
                        } else {
                          setSelectedProcessId(null);
                        }
                      }}
                    />
                  </div>
                </TabsContent>
              </Tabs>
            ) : null}

            {/* 选中符号时显示详情 */}
            {selectedSymbol && hasAnalysis && (
              <div className="mt-6">
                <SymbolDetailPanel
                  projectId={projectId}
                  selectedSymbol={selectedSymbol}
                  processes={processes}
                  onGraphDataReady={handleSymbolGraphData}
                />
              </div>
            )}

            {/* 选中执行流时显示调用链 */}
            {selectedProcessId && hasAnalysis && (
              <div className="mt-6">
                <ProcessTracePanel
                  projectId={projectId}
                  processId={selectedProcessId}
                  onBack={() => setSelectedProcessId(null)}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── AI 综合面板（侧滑，非 Dialog，一进页面不会弹出） ── */}
      <div
        className={cn(
          "fixed right-0 top-0 z-50 h-full bg-white transition-transform duration-300 ease-in-out border-l shadow-2xl flex flex-col",
          aiPanelOpen ? "translate-x-0 w-[520px]" : "translate-x-full w-[520px]"
        )}
      >
        {/* 面板头部 */}
        <div className="flex items-center justify-between border-b px-5 py-3 shrink-0">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">AI 代码分析</span>
          </div>
          <button
            onClick={() => setAiPanelOpen(false)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 子标签页切换 */}
        <div className="flex border-b bg-muted/10 shrink-0">
          <button
            onClick={() => setAiSubTab("settings")}
            className={cn(
              "flex-1 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors flex items-center justify-center gap-1.5",
              aiSubTab === "settings"
                ? "border-primary text-primary bg-white"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <Settings className="h-3.5 w-3.5" /> 模型设置
          </button>
          <button
            onClick={() => setAiSubTab("chat")}
            className={cn(
              "flex-1 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors flex items-center justify-center gap-1.5",
              aiSubTab === "chat"
                ? "border-primary text-primary bg-white"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            <MessageSquare className="h-3.5 w-3.5" /> AI 对话
          </button>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-hidden">
          {aiSubTab === "settings" ? (
            <div className="h-full overflow-y-auto">
              <InlineLLMConfig projectId={projectId} />
            </div>
          ) : (
            <div className="h-full flex flex-col">
              {assistant ? (
                <ClientProvider
                  deploymentUrl={getDeploymentUrl()}
                  apiKey={process.env.NEXT_PUBLIC_LANGSMITH_API_KEY || ""}
                >
                  <div className="flex-1">
                    <AIChatContainer
                      assistant={assistant}
                      onClose={() => setAiPanelOpen(false)}
                      createNewThread={false}
                    />
                  </div>
                </ClientProvider>
              ) : (
                <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  初始化中...
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </MainLayout>
  );
}
