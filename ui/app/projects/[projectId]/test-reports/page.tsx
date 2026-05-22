"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { MainLayout } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Activity } from "lucide-react";
import { listTestReports, getTestReport, type TestReportListInfo, type TestReportInfo, type TestReportTestInfo } from "@/lib/api/test-reports";
import { getDashboard, type DashboardData, type DashboardSummary } from "@/lib/api/reports";
import { createDiagnosisReport, listDiagnosisReports } from "@/lib/api/diagnosis";

const defaultSummary: DashboardSummary = {
  total_endpoints: 0,
  endpoints_passed: 0,
  endpoints_failed: 0,
  total_executions: 0,
  executions_passed: 0,
  executions_failed: 0,
  avg_duration_ms: 0,
  pass_rate: 0,
};

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

function formatTime(iso: string): string {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    passed: "bg-green-100 text-green-800 border-green-300",
    failed: "bg-red-100 text-red-800 border-red-300",
    skipped: "bg-yellow-100 text-yellow-800 border-yellow-300",
    timedOut: "bg-orange-100 text-orange-800 border-orange-300",
    interrupted: "bg-gray-100 text-gray-800 border-gray-300",
  };
  const cls = colors[status] || "bg-gray-100 text-gray-800 border-gray-300";
  const labels: Record<string, string> = {
    passed: "通过",
    failed: "失败",
    skipped: "跳过",
    timedOut: "超时",
    interrupted: "中断",
  };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {labels[status] || status}
    </span>
  );
}

// ==================== 测试用例详情面板 ====================
function TestCaseDetail({ test }: { test: TestReportTestInfo }) {
  const [expanded, setExpanded] = React.useState(false);
  return (
    <div className="rounded-lg border bg-card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-accent/50 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={`flex-shrink-0 w-2 h-2 rounded-full ${test.ok ? "bg-green-500" : "bg-red-500"}`} />
          <span className="text-sm font-medium truncate">{test.name}</span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-muted-foreground">{formatDuration(test.duration_ms)}</span>
          <StatusBadge status={test.status} />
          <svg
            className={`w-4 h-4 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>
      {expanded && (
        <div className="border-t px-4 py-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-muted-foreground">状态: </span>
              <StatusBadge status={test.status} />
            </div>
            <div>
              <span className="text-muted-foreground">预期: </span>
              <StatusBadge status={test.expected_status} />
            </div>
            <div>
              <span className="text-muted-foreground">耗时: </span>
              <span className="font-mono text-xs">{formatDuration(test.duration_ms)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">项目: </span>
              <span className="font-mono text-xs">{test.project}</span>
            </div>
          </div>
          {test.error && (
            <div>
              <p className="text-xs font-medium text-red-600 mb-1">错误信息:</p>
              <pre className="rounded bg-red-50 border border-red-200 p-2 text-xs text-red-700 overflow-x-auto whitespace-pre-wrap">{test.error}</pre>
            </div>
          )}
          {test.stack && (
            <div>
              <p className="text-xs font-medium text-muted-foreground mb-1">堆栈跟踪:</p>
              <pre className="rounded bg-muted p-2 text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto">{test.stack}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ==================== 报告详情页 ====================
function ReportDetailView({ report, projectId, onBack }: { report: TestReportInfo; projectId: string; onBack: () => void }) {
  const router = useRouter();
  const [expandedAll, setExpandedAll] = React.useState(false);
  const [filterStatus, setFilterStatus] = React.useState<string | null>(null);
  const [diagnosing, setDiagnosing] = React.useState(false);

  const handleDiagnose = async () => {
    setDiagnosing(true);
    try {
      // 先检查是否已有诊断报告
      const listRes = await listDiagnosisReports(projectId, { run_id: report.id });
      if (listRes.success && listRes.data.items.length > 0) {
        const existing = listRes.data.items[0];
        router.push(`/projects/${projectId}/diagnosis`);
        return;
      }
      // 创建新的诊断
      const res = await createDiagnosisReport(projectId, report.id);
      if (res.success) {
        toast.success("诊断已触发", {
          description: `报告 ID: ${res.data.report_id}，正在分析中...`,
        });
      }
    } catch (e) {
      toast.error("触发诊断失败", { description: String(e) });
    } finally {
      setDiagnosing(false);
    }
  };

  let filteredTests = report.tests;
  if (filterStatus) {
    filteredTests = filteredTests.filter(t => t.status === filterStatus);
  }

  const passedCount = filteredTests.filter(t => t.status === "passed").length;
  const failedCount = filteredTests.filter(t => t.status === "failed").length;

  return (
    <div className="space-y-4">
      {/* 返回按钮 */}
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        返回报告列表
      </button>

      {/* 报告头部 */}
      <div className="rounded-lg border bg-card p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold">测试报告详情</h2>
            <p className="text-xs text-muted-foreground mt-1">
              执行时间: {formatTime(report.generated_at)} | 框架: {report.framework} | 退出码: {report.exit_code}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDiagnose}
              disabled={diagnosing}
            >
              <Activity className="mr-2 h-4 w-4" />
              {diagnosing ? "诊断中..." : "智能诊断"}
            </Button>
            {report.presigned_url && (
            <a
              href={report.presigned_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              原始 JSON
            </a>
          )}
        </div>
        </div>

        {/* 概要统计 */}
        <div className="grid grid-cols-5 gap-3">
          <div className="text-center rounded-md bg-muted p-2">
            <p className="text-2xl font-bold">{report.summary.total}</p>
            <p className="text-xs text-muted-foreground">总计</p>
          </div>
          <div className="text-center rounded-md bg-green-50 p-2">
            <p className="text-2xl font-bold text-green-700">{report.summary.passed}</p>
            <p className="text-xs text-green-600">通过</p>
          </div>
          <div className="text-center rounded-md bg-red-50 p-2">
            <p className="text-2xl font-bold text-red-700">{report.summary.failed}</p>
            <p className="text-xs text-red-600">失败</p>
          </div>
          <div className="text-center rounded-md bg-yellow-50 p-2">
            <p className="text-2xl font-bold text-yellow-700">{report.summary.skipped}</p>
            <p className="text-xs text-yellow-600">跳过</p>
          </div>
          <div className="text-center rounded-md bg-blue-50 p-2">
            <p className="text-2xl font-bold text-blue-700">{formatDuration(report.summary.total_duration_ms)}</p>
            <p className="text-xs text-blue-600">总耗时</p>
          </div>
        </div>

        {/* 通过率进度条 */}
        {report.summary.total > 0 && (
          <div className="mt-3">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>通过率</span>
              <span>{report.summary.total > 0 ? Math.round((report.summary.passed / report.summary.total) * 100) : 0}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-green-500 transition-all"
                style={{ width: `${report.summary.total > 0 ? (report.summary.passed / report.summary.total) * 100 : 0}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* 筛选和操作 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">筛选:</span>
          {[
            { key: null, label: "全部", count: report.tests.length },
            { key: "passed", label: "通过", count: report.summary.passed },
            { key: "failed", label: "失败", count: report.summary.failed },
            { key: "skipped", label: "跳过", count: report.summary.skipped },
          ].map((f) => (
            <button
              key={f.key || "all"}
              onClick={() => setFilterStatus(f.key)}
              className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
                filterStatus === f.key
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-card text-muted-foreground border-border hover:bg-accent"
              }`}
            >
              {f.label} ({f.count})
            </button>
          ))}
        </div>
        <button
          onClick={() => setExpandedAll(!expandedAll)}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {expandedAll ? "全部折叠" : "全部展开"}
        </button>
      </div>

      {/* 测试用例列表 */}
      <div className="space-y-2">
        {filteredTests.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground text-sm">暂无匹配的测试用例</div>
        ) : (
          filteredTests.map((test, idx) => (
            <TestCaseDetail key={`${test.name}-${idx}`} test={test} />
          ))
        )}
      </div>

      {/* 底部统计 */}
      <div className="text-xs text-muted-foreground text-center py-2">
        共 {filteredTests.length} 个测试用例 | 通过 {passedCount} | 失败 {failedCount}
      </div>
    </div>
  );
}

// ==================== 报告列表 ====================
function ReportListItem({ report, onSelect }: { report: TestReportListInfo; onSelect: () => void }) {
  const passRate = report.summary.total > 0
    ? Math.round((report.summary.passed / report.summary.total) * 100)
    : 0;
  const isAllure = report.report_type === "allure";
  return (
    <button
      onClick={onSelect}
      className="w-full rounded-lg border bg-card p-4 text-left hover:bg-accent/50 transition-colors"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">#{report.id}</span>
          <span className="text-xs text-muted-foreground">{formatTime(report.generated_at)}</span>
          {isAllure && (
            <span className="inline-flex items-center rounded-md bg-purple-100 text-purple-800 border border-purple-300 px-1.5 py-0.5 text-xs font-medium">
              Allure
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span>{report.summary.total} 用例</span>
          <span>·</span>
          <span className={passRate >= 80 ? "text-green-600" : passRate >= 50 ? "text-yellow-600" : "text-red-600"}>
            {passRate}%
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-xs text-green-700">{report.summary.passed}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-500" />
          <span className="text-xs text-red-700">{report.summary.failed}</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-yellow-500" />
          <span className="text-xs text-yellow-700">{report.summary.skipped}</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {report.presigned_url && isAllure && (
            <a
              href={`/api/v2/projects/${report.project_identifier}/test-reports/${report.id}/view`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 rounded-md bg-purple-600 px-2 py-1 text-xs font-medium text-white hover:bg-purple-700 transition-colors"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
              查看 Allure 报告
            </a>
          )}
          {report.presigned_url && !isAllure && (
            <span className="text-xs text-muted-foreground">{formatDuration(report.summary.total_duration_ms)}</span>
          )}
        </div>
      </div>
      {/* 进度条 */}
      {report.summary.total > 0 && (
        <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
          <div className={`h-full rounded-full transition-all ${isAllure ? "bg-purple-500" : "bg-green-500"}`} style={{ width: `${passRate}%` }} />
        </div>
      )}
    </button>
  );
}

// ==================== 主页面 ====================
export default function ReportsPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [dashboard, setDashboard] = React.useState<DashboardData | null>(null);
  const [reports, setReports] = React.useState<TestReportListInfo[]>([]);
  const [selectedReport, setSelectedReport] = React.useState<TestReportInfo | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [loadingReport, setLoadingReport] = React.useState(false);
  const [page, setPage] = React.useState(1);
  const [totalReports, setTotalReports] = React.useState(0);
  const pageSize = 20;

  // 加载 dashboard 概要和报告列表
  React.useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboard(projectId).catch(() => ({ data: { summary: defaultSummary, users: [], recent_executions: [] } })),
      listTestReports(projectId, page, pageSize).catch(() => ({ data: [], pagination: { total: 0, page: 1, page_size: 20 } })),
    ]).then(([dashResult, reportsResult]) => {
      setDashboard(dashResult.data);
      setReports(reportsResult.data);
      setTotalReports(reportsResult.pagination.total);
      setLoading(false);
    });
  }, [projectId, page]);

  // 选择一个报告查看详情
  const handleSelectReport = async (reportId: string) => {
    setLoadingReport(true);
    try {
      const result = await getTestReport(projectId, reportId);
      setSelectedReport(result.data);
    } catch (e) {
      console.error("加载报告详情失败:", e);
    }
    setLoadingReport(false);
  };

  const summary = dashboard?.summary || defaultSummary;

  // 如果已选中报告，显示详情视图
  if (selectedReport) {
    return (
      <MainLayout title={selectedReport.id}>
        <div className="p-4">
          <ReportDetailView report={selectedReport} projectId={projectId} onBack={() => setSelectedReport(null)} />
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout title="报告">
      <div className="space-y-4 p-4">
        {/* 页面标题 */}
        <div>
          <h1 className="text-xl font-bold">测试报告</h1>
          <p className="text-sm text-muted-foreground mt-1">项目 {projectId} 的测试执行报告</p>
        </div>

        {/* Dashboard 摘要卡片 */}
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-lg border bg-card p-3">
            <p className="text-xs text-muted-foreground">API 端点</p>
            <p className="text-xl font-bold">{summary.total_endpoints}</p>
          </div>
          <div className="rounded-lg border bg-card p-3">
            <p className="text-xs text-muted-foreground">通过率</p>
            <p className="text-xl font-bold">{summary.pass_rate}%</p>
          </div>
          <div className="rounded-lg border bg-card p-3">
            <p className="text-xs text-muted-foreground">测试执行</p>
            <p className="text-xl font-bold">{summary.total_executions}</p>
          </div>
          <div className="rounded-lg border bg-card p-3">
            <p className="text-xs text-muted-foreground">平均耗时</p>
            <p className="text-xl font-bold">
              {summary.avg_duration_ms > 1000
                ? `${(summary.avg_duration_ms / 1000).toFixed(1)}s`
                : `${Math.round(summary.avg_duration_ms)}ms`}
            </p>
          </div>
        </div>

        {/* 报告列表 */}
        <div>
          <h2 className="text-sm font-medium mb-2">
            执行历史
            <span className="text-muted-foreground ml-1">({totalReports})</span>
          </h2>
          {loading ? (
            <div className="text-center py-8 text-sm text-muted-foreground">加载中...</div>
          ) : reports.length === 0 ? (
            <div className="text-center py-12 border rounded-lg bg-card">
              <p className="text-sm text-muted-foreground">暂无测试报告</p>
              <p className="text-xs text-muted-foreground mt-1">运行测试后，报告会显示在这里</p>
            </div>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <ReportListItem
                  key={report.id}
                  report={report}
                  onSelect={() => handleSelectReport(report.id)}
                />
              ))}
            </div>
          )}

          {/* 分页 */}
          {totalReports > pageSize && (
            <div className="flex items-center justify-center gap-2 mt-4">
              <button
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1 text-xs rounded border bg-card disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent transition-colors"
              >
                上一页
              </button>
              <span className="text-xs text-muted-foreground">
                第 {page} 页 / 共 {Math.ceil(totalReports / pageSize)} 页
              </span>
              <button
                disabled={page >= Math.ceil(totalReports / pageSize)}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1 text-xs rounded border bg-card disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent transition-colors"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 报告加载遮罩 */}
      {loadingReport && (
        <div className="fixed inset-0 bg-background/80 flex items-center justify-center z-50">
          <p className="text-sm text-muted-foreground">加载报告详情...</p>
        </div>
      )}
    </MainLayout>
  );
}
