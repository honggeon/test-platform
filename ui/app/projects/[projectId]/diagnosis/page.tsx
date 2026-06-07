"use client";

import * as React from "react";
import { useParams, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { MainLayout } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ArrowLeft,
  RefreshCw,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  BarChart3,
  Zap,
  BrainCircuit,
  ChevronDown,
  ChevronUp,
  Search,
  MessagesSquare,
} from "lucide-react";
import { AIChatContainer } from "@/components/langgraph/AIChatContainer";
import { ClientProvider } from "@/providers/ClientProvider";
import { getDeploymentUrl } from "@/lib/langgraph/config";
import { Assistant } from "@langchain/langgraph-sdk";
import { cn } from "@/lib/utils";
import { useDiagnosisWebSocket } from "@/hooks/useDiagnosisWebSocket";
import {
  listDiagnosisReports,
  getDiagnosisReport,
  getRuleStats,
  reloadDiagnosisRules,
  retryDiagnosisReport,
} from "@/lib/api/diagnosis";
import type {
  DiagnosisReport,
  DiagnosisReportListItem,
  DiagnosisFinding,
  RuleStats,
  RootCauseCounts,
  WSDiagnosisCompletedPayload,
  WSDiagnosisProgressPayload,
} from "@/types/diagnosis";

// ==================== 常量 ====================
const ROOT_CAUSE_LABELS: Record<string, string> = {
  token_expired: "Token 过期",
  permission_denied: "权限拒绝",
  api_changed: "API 变更",
  data_error: "数据错误",
  network_timeout: "网络超时",
  script_error: "脚本错误",
  unknown: "未知",
};

const ROOT_CAUSE_COLORS: Record<string, string> = {
  token_expired: "bg-amber-500",
  permission_denied: "bg-red-500",
  api_changed: "bg-purple-500",
  data_error: "bg-orange-500",
  network_timeout: "bg-blue-500",
  script_error: "bg-pink-500",
  unknown: "bg-gray-500",
};

const ROOT_CAUSE_BORDER_COLORS: Record<string, string> = {
  token_expired: "border-amber-200",
  permission_denied: "border-red-200",
  api_changed: "border-purple-200",
  data_error: "border-orange-200",
  network_timeout: "border-blue-200",
  script_error: "border-pink-200",
  unknown: "border-gray-200",
};

// ==================== 工具函数 ====================
function formatTime(iso: string | null): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

function getStatusBadge(status: string) {
  const configs: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
    completed: { label: "已完成", variant: "default" },
    analyzing: { label: "分析中", variant: "secondary" },
    pending: { label: "等待中", variant: "outline" },
    failed: { label: "失败", variant: "destructive" },
  };
  const cfg = configs[status] || { label: status, variant: "outline" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

function getDegradationBadge(level: string) {
  const configs: Record<string, { label: string; cls: string }> = {
    none: { label: "完整分析", cls: "bg-green-100 text-green-800 border-green-300" },
    partial: { label: "部分降级", cls: "bg-yellow-100 text-yellow-800 border-yellow-300" },
    severe: { label: "严重降级", cls: "bg-red-100 text-red-800 border-red-300" },
  };
  const cfg = configs[level] || { label: level, cls: "bg-gray-100 text-gray-800 border-gray-300" };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cfg.cls}`}>
      {cfg.label}
    </span>
  );
}

function getRootCauseDistribution(counts: RootCauseCounts): { type: string; count: number }[] {
  const result: { type: string; count: number }[] = [];
  for (const type in counts) {
    const count = counts[type];
    if (typeof count === "number" && count > 0) {
      result.push({ type, count });
    }
  }
  return result.sort((a, b) => b.count - a.count);
}

// ==================== 根因 Mini 分布条 ====================
function RootCauseMiniBar({ counts }: { counts: RootCauseCounts }) {
  const items = getRootCauseDistribution(counts);
  const total = items.reduce((sum, i) => sum + i.count, 0);
  if (total === 0) return <span className="text-xs text-muted-foreground">无失败</span>;

  return (
    <div className="flex items-center gap-2">
      <div className="flex h-2 w-24 rounded-full overflow-hidden">
        {items.map((item) => (
          <div
            key={item.type}
            className={ROOT_CAUSE_COLORS[item.type] || "bg-gray-400"}
            style={{ width: `${(item.count / total) * 100}%` }}
            title={`${ROOT_CAUSE_LABELS[item.type] || item.type}: ${item.count}`}
          />
        ))}
      </div>
      <span className="text-xs text-muted-foreground">{total} 失败</span>
    </div>
  );
}

// ==================== 报告列表项 ====================
function ReportListItem({
  report,
  onSelect,
  onRetry,
  retrying,
}: {
  report: DiagnosisReportListItem;
  onSelect: () => void;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  const canRetry = report.status === "analyzing" || report.status === "failed";

  return (
    <div className="rounded-lg border bg-card hover:bg-accent/50 transition-colors">
      <button
        onClick={onSelect}
        className="w-full p-4 text-left"
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">#{report.id.slice(0, 8)}</span>
            <span className="text-xs text-muted-foreground">Run: {report.run_id.slice(0, 8)}</span>
            {getStatusBadge(report.status)}
          </div>
          <div className="flex items-center gap-2">
            {getDegradationBadge(report.degradation_level)}
            <span className="text-xs text-muted-foreground">{formatTime(report.created_at)}</span>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <RootCauseMiniBar counts={report.summary.root_cause_counts} />
          <span className="text-xs text-muted-foreground">
            来源: {report.source_type}
          </span>
        </div>
      </button>
      {canRetry && onRetry && (
        <div className="border-t px-4 py-2 flex justify-end">
          <Button
            variant="outline"
            size="sm"
            disabled={retrying}
            onClick={(e) => {
              e.stopPropagation();
              onRetry();
            }}
          >
            <RefreshCw className={cn("mr-2 h-3 w-3", retrying && "animate-spin")} />
            重新诊断
          </Button>
        </div>
      )}
    </div>
  );
}

// ==================== Finding 详情行 ====================
function FindingRow({ finding }: { finding: DiagnosisFinding }) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="rounded-lg border bg-card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-accent/50 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span
            className={`flex-shrink-0 w-2 h-2 rounded-full ${
              ROOT_CAUSE_COLORS[finding.root_cause_type] || "bg-gray-400"
            }`}
          />
          <span className="text-sm font-medium truncate">
            {finding.method} {finding.endpoint}
          </span>
          <Badge variant="outline" className="text-xs shrink-0">
            {finding.status_code}
          </Badge>
          <span
            className={`text-xs px-1.5 py-0.5 rounded border shrink-0 ${
              ROOT_CAUSE_BORDER_COLORS[finding.root_cause_type] || "border-gray-200"
            } ${ROOT_CAUSE_COLORS[finding.root_cause_type]?.replace("bg-", "text-") || "text-gray-600"}`}
          >
            {ROOT_CAUSE_LABELS[finding.root_cause_type] || finding.root_cause_type}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Badge variant={finding.classifier === "rule" ? "default" : "secondary"} className="text-xs">
            {finding.classifier === "rule" ? "规则" : "LLM"}
          </Badge>
          {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t px-4 py-3 space-y-3">
          {finding.root_cause_detail && (
            <div className="rounded-md bg-muted/50 p-2 text-xs">
              <span className="text-muted-foreground">根因详情: </span>
              {finding.root_cause_detail}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-muted-foreground">错误信息: </span>
              <span className="text-xs">{finding.error_message || "-"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">匹配规则: </span>
              <span className="font-mono text-xs">{finding.matching_rule || "-"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">分类器: </span>
              <span className="text-xs">{finding.classifier}</span>
            </div>
            <div>
              <span className="text-muted-foreground">LLM 缓存: </span>
              <span className="text-xs">{finding.llm_cache_hit ? "命中" : "未命中"}</span>
            </div>
          </div>

          {finding.affects_apis.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">影响 API:</p>
              <ul className="list-disc list-inside text-xs space-y-1">
                {finding.affects_apis.map((api, i) => (
                  <li key={i} className="font-mono">{api}</li>
                ))}
              </ul>
            </div>
          )}

          {/* 代码位置 */}
          {finding.code_locations.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-2">代码位置:</p>
              <div className="space-y-2">
                {finding.code_locations.map((loc, idx) => (
                  <div key={idx} className="rounded bg-muted p-2 text-xs">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-medium">{loc.strategy}</span>
                      <span className="text-muted-foreground">置信度: {(loc.confidence * 100).toFixed(0)}%</span>
                    </div>
                    <pre className="text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">
                      {JSON.stringify(loc.result, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 修复建议 */}
          {finding.fix_suggestions.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">修复建议:</p>
              <ul className="list-disc list-inside text-xs space-y-1">
                {finding.fix_suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ==================== 报告详情视图 ====================
function ReportDetailView({
  report,
  onBack,
  onRetry,
  retrying,
  progress,
}: {
  report: DiagnosisReport;
  onBack: () => void;
  onRetry?: () => void;
  retrying?: boolean;
  progress?: WSDiagnosisProgressPayload | null;
}) {
  const [filterRootCause, setFilterRootCause] = React.useState<string | null>(null);

  const rootCauseDistribution = getRootCauseDistribution(report.summary.root_cause_counts);
  const totalFailures = report.summary.total_failures;

  let filteredFindings = report.findings;
  if (filterRootCause) {
    filteredFindings = filteredFindings.filter(
      (f) => f.root_cause_type === filterRootCause
    );
  }

  return (
    <div className="space-y-4">
      {/* 返回按钮 */}
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        返回报告列表
      </button>

      {/* 报告头部 */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold">诊断报告详情</h2>
            <p className="text-xs text-muted-foreground mt-1">
              报告 ID: {report.report_id} | Run: {report.run_id} | 耗时: {formatDuration(report.analysis_duration_ms)}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {getStatusBadge(report.status)}
            {getDegradationBadge(
              report.degradation.fallback_reason
                ? report.degradation.has_db_logs
                  ? "partial"
                  : "severe"
                : "none"
            )}
            {(report.status === "analyzing" || report.status === "failed") && onRetry && (
              <Button variant="outline" size="sm" disabled={retrying} onClick={onRetry}>
                <RefreshCw className={cn("mr-2 h-3 w-3", retrying && "animate-spin")} />
                重新诊断
              </Button>
            )}
          </div>
        </div>

        {report.status === "analyzing" && progress?.report_id === report.report_id && (
          <div className="mb-3 space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{progress.message || progress.phase}</span>
              {progress.progress != null && <span>{Math.round(progress.progress)}%</span>}
            </div>
            <Progress value={progress.progress ?? undefined} className="h-2" />
          </div>
        )}

        {/* 降级状态 */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className={`text-center rounded-md p-2 text-xs ${report.degradation.has_db_logs ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
            <CheckCircle2 className="h-4 w-4 mx-auto mb-1" />
            日志收集
          </div>
          <div className={`text-center rounded-md p-2 text-xs ${report.degradation.has_kg_locations ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
            <CheckCircle2 className="h-4 w-4 mx-auto mb-1" />
            代码定位
          </div>
          <div className={`text-center rounded-md p-2 text-xs ${report.degradation.has_llm_analysis ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
            <BrainCircuit className="h-4 w-4 mx-auto mb-1" />
            LLM 分析
          </div>
          <div className="text-center rounded-md bg-muted p-2 text-xs">
            <Zap className="h-4 w-4 mx-auto mb-1" />
            Tokens: {report.llm_token_cost.total_tokens}
          </div>
        </div>

        {report.degradation.fallback_reason && (
          <div className="rounded-md bg-yellow-50 border border-yellow-200 p-2 text-xs text-yellow-800 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            降级原因: {report.degradation.fallback_reason}
          </div>
        )}
      </div>

      {/* 根因分布 */}
      {totalFailures > 0 && (
        <div className="rounded-lg border bg-card p-4">
          <h3 className="text-sm font-medium mb-3">根因分布</h3>
          <div className="space-y-2">
            {rootCauseDistribution.map((item) => {
              const pct = totalFailures > 0 ? (item.count / totalFailures) * 100 : 0;
              return (
                <div key={item.type}>
                  <div className="flex justify-between text-xs mb-1">
                    <span>{ROOT_CAUSE_LABELS[item.type] || item.type}</span>
                    <span className="text-muted-foreground">
                      {item.count} ({Math.round(pct)}%)
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full ${ROOT_CAUSE_COLORS[item.type] || "bg-gray-400"}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Findings 筛选和列表 */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium">详细发现 ({filteredFindings.length})</h3>
          <div className="flex items-center gap-2">
            <Select
              value={filterRootCause || "all"}
              onValueChange={(v) => setFilterRootCause(v === "all" ? null : v)}
            >
              <SelectTrigger className="w-36 h-8 text-xs">
                <SelectValue placeholder="筛选根因" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部根因</SelectItem>
                {Object.keys(ROOT_CAUSE_LABELS).map((key) => (
                  <SelectItem key={key} value={key}>
                    {ROOT_CAUSE_LABELS[key]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          {filteredFindings.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">暂无发现</div>
          ) : (
            filteredFindings.map((finding) => (
              <FindingRow key={finding.failure_id} finding={finding} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ==================== 规则统计对话框 ====================
function RuleStatsDialog({
  open,
  onOpenChange,
  projectId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projectId: string;
}) {
  const [stats, setStats] = React.useState<RuleStats | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [days, setDays] = React.useState(7);

  React.useEffect(() => {
    if (!open || !projectId) return;
    setLoading(true);
    getRuleStats(projectId, days)
      .then((res) => {
        if (res.success) setStats(res.data);
      })
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [open, projectId, days]);

  const hitEntries = stats
    ? Object.entries(stats.hit_counts).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            规则命中率统计
          </DialogTitle>
          <DialogDescription>
            统计周期内规则引擎 vs LLM 兜底的比例
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">统计周期:</span>
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger className="w-32 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">最近 1 天</SelectItem>
                <SelectItem value="7">最近 7 天</SelectItem>
                <SelectItem value="30">最近 30 天</SelectItem>
                <SelectItem value="90">最近 90 天</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {loading ? (
            <div className="text-center py-8 text-sm text-muted-foreground">加载中...</div>
          ) : !stats ? (
            <div className="text-center py-8 text-sm text-muted-foreground">暂无数据</div>
          ) : (
            <>
              {/* 总览 */}
              <div className="grid grid-cols-3 gap-3">
                <div className="text-center rounded-md bg-muted p-3">
                  <p className="text-xl font-bold">{stats.total_classified}</p>
                  <p className="text-xs text-muted-foreground">总分类数</p>
                </div>
                <div className="text-center rounded-md bg-green-50 p-3">
                  <p className="text-xl font-bold text-green-700">{(stats.hit_rate * 100).toFixed(1)}%</p>
                  <p className="text-xs text-green-600">规则命中率</p>
                </div>
                <div className="text-center rounded-md bg-blue-50 p-3">
                  <p className="text-xl font-bold text-blue-700">{stats.llm_fallback_count}</p>
                  <p className="text-xs text-blue-600">LLM 兜底</p>
                </div>
              </div>

              {/* 各规则命中 */}
              {hitEntries.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">规则命中详情</p>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {hitEntries.map(([ruleId, count]) => {
                      const pct = stats.total_classified > 0 ? (count / stats.total_classified) * 100 : 0;
                      return (
                        <div key={ruleId}>
                          <div className="flex justify-between text-xs mb-0.5">
                            <span className="font-mono">{ruleId}</span>
                            <span className="text-muted-foreground">{count}</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ==================== 主页面 ====================
export default function DiagnosisPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const projectId = params.projectId as string;

  const [reports, setReports] = React.useState<DiagnosisReportListItem[]>([]);
  const [selectedReport, setSelectedReport] = React.useState<DiagnosisReport | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [loadingReport, setLoadingReport] = React.useState(false);
  const [page, setPage] = React.useState(1);
  const [total, setTotal] = React.useState(0);
  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [statsOpen, setStatsOpen] = React.useState(false);
  const [assistant, setAssistant] = React.useState<Assistant | null>(null);
  const [aiChatOpen, setAiChatOpen] = React.useState(false);
  const [retryingReportId, setRetryingReportId] = React.useState<string | null>(null);
  const [diagnosisProgress, setDiagnosisProgress] = React.useState<WSDiagnosisProgressPayload | null>(null);
  const pageSize = 20;

  const urlReportId = searchParams.get("reportId");
  const selectedReportIdRef = React.useRef<string | null>(null);
  selectedReportIdRef.current = selectedReport?.report_id ?? null;

  // 初始化 LangGraph Assistant（优先连接日志分析 Agent）
  React.useEffect(() => {
    getDeploymentUrl();
    const initAssistant = async () => {
      try {
        const { Client } = await import("@langchain/langgraph-sdk");
        const { getAuthHeaders } = await import("@/lib/auth");
        const client = new Client({
          apiUrl: getDeploymentUrl(),
          defaultHeaders: getAuthHeaders(),
        });
        const assistants = await client.assistants.search();
        // 优先使用日志分析 Agent，fallback 到第一个
        const logAgent = assistants.find(
          (a) => a.assistant_id === "log_analysis_agent"
        );
        if (logAgent) {
          setAssistant(logAgent);
        } else if (assistants.length > 0) {
          setAssistant(assistants[0]);
        }
      } catch {}
    };
    initAssistant();
  }, []);

  const loadReports = React.useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await listDiagnosisReports(projectId, {
        page,
        page_size: pageSize,
        ...(statusFilter !== "all" ? { status: statusFilter } : {}),
      });
      if (res.success) {
        setReports(res.data.items);
        setTotal(res.data.total);
      }
    } catch (e) {
      console.error("加载诊断报告失败:", e);
    } finally {
      setLoading(false);
    }
  }, [projectId, page, statusFilter]);

  const handleSelectReport = React.useCallback(async (reportId: string) => {
    setLoadingReport(true);
    try {
      const res = await getDiagnosisReport(projectId, reportId);
      if (res.success) {
        setSelectedReport(res.data);
      }
    } catch (e) {
      console.error("加载诊断详情失败:", e);
    }
    setLoadingReport(false);
  }, [projectId]);

  const handleRetryReport = React.useCallback(async (reportId: string) => {
    setRetryingReportId(reportId);
    try {
      const res = await retryDiagnosisReport(projectId, reportId);
      if (res.success) {
        toast.success("已触发重新诊断");
        await loadReports();
        if (selectedReportIdRef.current === reportId) {
          await handleSelectReport(reportId);
        }
      }
    } catch (e) {
      console.error("重新诊断失败:", e);
      toast.error("重新诊断失败");
    } finally {
      setRetryingReportId(null);
    }
  }, [projectId, loadReports, handleSelectReport]);

  const handleDiagnosisCompleted = React.useCallback(
    (payload: WSDiagnosisCompletedPayload) => {
      loadReports();
      const viewingId = selectedReportIdRef.current;
      const urlId = urlReportId;
      if (
        payload.report_id === viewingId ||
        payload.report_id === urlId
      ) {
        handleSelectReport(payload.report_id);
      }
      if (diagnosisProgress?.report_id === payload.report_id) {
        setDiagnosisProgress(null);
      }
    },
    [loadReports, handleSelectReport, urlReportId, diagnosisProgress?.report_id]
  );

  const handleDiagnosisProgress = React.useCallback(
    (payload: WSDiagnosisProgressPayload) => {
      setDiagnosisProgress(payload);
    },
    []
  );

  useDiagnosisWebSocket({
    projectId,
    onDiagnosisCompleted: handleDiagnosisCompleted,
    onDiagnosisProgress: handleDiagnosisProgress,
    enabled: !!projectId,
  });

  React.useEffect(() => {
    loadReports();
  }, [loadReports]);

  React.useEffect(() => {
    if (urlReportId) {
      handleSelectReport(urlReportId);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlReportId]);

  const handleReloadRules = async () => {
    try {
      await reloadDiagnosisRules(projectId);
      toast.success("规则库刷新成功");
    } catch (e) {
      console.error("刷新规则失败:", e);
      toast.error("规则库刷新失败");
    }
  };

  // 详情视图
  if (selectedReport) {
    return (
      <MainLayout title="诊断详情">
        <div className="relative flex h-full">
          <div className="flex-1 overflow-auto p-4 max-w-4xl mx-auto">
            <ReportDetailView
              report={selectedReport}
              onBack={() => setSelectedReport(null)}
              onRetry={() => handleRetryReport(selectedReport.report_id)}
              retrying={retryingReportId === selectedReport.report_id}
              progress={diagnosisProgress}
            />
          </div>
          {assistant && (
            <div className={cn(
              "absolute right-0 top-0 z-50 h-full w-[600px] bg-background transition-transform duration-300",
              aiChatOpen ? "translate-x-0 border-l shadow-2xl" : "translate-x-full"
            )}>
              <ClientProvider deploymentUrl={getDeploymentUrl()} apiKey="">
                <AIChatContainer
                  assistant={assistant}
                  onClose={() => setAiChatOpen(false)}
                />
              </ClientProvider>
            </div>
          )}
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout title="智能诊断">
      <div className="relative flex h-full">
        <div className="flex-1 overflow-auto p-4 max-w-4xl mx-auto space-y-4">
        {/* 页面头部 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <Activity className="h-6 w-6 text-primary" />
              智能诊断
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              项目 {projectId} 的测试失败根因分析报告
            </p>
          </div>
          <div className="flex items-center gap-2">
            {assistant && (
              <Button
                variant={aiChatOpen ? "default" : "outline"}
                size="sm"
                onClick={() => setAiChatOpen(!aiChatOpen)}
              >
                <MessagesSquare className="mr-2 h-4 w-4" />
                {aiChatOpen ? "关闭对话" : "AI 对话"}
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setStatsOpen(true)}>
              <BarChart3 className="mr-2 h-4 w-4" />
              规则统计
            </Button>
            <Button variant="outline" size="sm" onClick={handleReloadRules}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新规则
            </Button>
            <Button variant="outline" size="sm" onClick={loadReports}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
          </div>
        </div>

        {/* 报告列表 */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-medium">
              诊断报告
              <span className="text-muted-foreground ml-1">({total})</span>
            </h2>
            <Select
              value={statusFilter}
              onValueChange={(v) => {
                setStatusFilter(v);
                setPage(1);
              }}
            >
              <SelectTrigger className="w-32 h-8 text-xs">
                <SelectValue placeholder="状态筛选" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部状态</SelectItem>
                <SelectItem value="completed">已完成</SelectItem>
                <SelectItem value="analyzing">分析中</SelectItem>
                <SelectItem value="failed">失败</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {loading ? (
            <div className="text-center py-8 text-sm text-muted-foreground">加载中...</div>
          ) : reports.length === 0 ? (
            <div className="text-center py-12 border rounded-lg bg-card">
              <Activity className="h-12 w-12 text-muted-foreground/50 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">暂无诊断报告</p>
              <p className="text-xs text-muted-foreground mt-1">
                运行测试并触发诊断后，报告会显示在这里
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <React.Fragment key={report.id}>
                  <ReportListItem
                    report={report}
                    onSelect={() => handleSelectReport(report.id)}
                    onRetry={() => handleRetryReport(report.id)}
                    retrying={retryingReportId === report.id}
                  />
                  {report.status === "analyzing" &&
                    diagnosisProgress?.report_id === report.id && (
                      <div className="rounded-lg border bg-card px-4 py-2 space-y-1 -mt-1">
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>{diagnosisProgress.message || diagnosisProgress.phase}</span>
                          {diagnosisProgress.progress != null && (
                            <span>{Math.round(diagnosisProgress.progress)}%</span>
                          )}
                        </div>
                        <Progress value={diagnosisProgress.progress ?? undefined} className="h-1.5" />
                      </div>
                    )}
                </React.Fragment>
              ))}
            </div>
          )}

          {/* 分页 */}
          {total > pageSize && (
            <div className="flex items-center justify-center gap-2 mt-4">
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 text-xs rounded border bg-card disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent transition-colors"
              >
                上一页
              </button>
              <span className="text-xs text-muted-foreground">
                第 {page} 页 / 共 {Math.ceil(total / pageSize)} 页
              </span>
              <button
                disabled={page >= Math.ceil(total / pageSize)}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 text-xs rounded border bg-card disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent transition-colors"
              >
                下一页
              </button>
            </div>
          )}
        </div>

        {assistant && (
          <div className={cn(
            "absolute right-0 top-0 z-50 h-full w-[600px] bg-background transition-transform duration-300",
            aiChatOpen ? "translate-x-0 border-l shadow-2xl" : "translate-x-full"
          )}>
            <ClientProvider deploymentUrl={getDeploymentUrl()} apiKey="">
              <AIChatContainer
                assistant={assistant}
                onClose={() => setAiChatOpen(false)}
              />
            </ClientProvider>
          </div>
        )}
      </div>
      </div>

      {/* 规则统计弹窗 */}
      <RuleStatsDialog
        open={statsOpen}
        onOpenChange={setStatsOpen}
        projectId={projectId}
      />

      {/* 加载遮罩 */}
      {loadingReport && (
        <div className="fixed inset-0 bg-background/80 flex items-center justify-center z-50">
          <p className="text-sm text-muted-foreground">加载诊断详情...</p>
        </div>
      )}
    </MainLayout>
  );
}
