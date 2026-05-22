import { MainLayout } from "@/components/layout";

async function getDashboard(projectId: string) {
  try {
    const res = await fetch(
      `http://localhost:8000/api/v2/projects/${projectId}/reports/dashboard?date_range=all`,
      { next: { revalidate: 30 } }
    );
    const json = await res.json();
    return json?.data || null;
  } catch {
    return null;
  }
}

export default async function DashboardPage({
  params,
}: {
  params: { projectId: string };
}) {
  const data = await getDashboard(params.projectId);
  const s = data?.summary || {};
  const users = data?.users || [];
  const recent = data?.recent_executions || [];

  return (
    <MainLayout title="报告">
      <div className="space-y-6">
        <h2 className="text-lg font-semibold">测试报告</h2>

        {!data ? (
          <p className="text-sm text-muted-foreground">暂无报告数据</p>
        ) : (
          <>
            {/* 概览卡片 */}
            <div className="grid gap-4 md:grid-cols-4">
              <div className="rounded-lg border bg-card p-4">
                <p className="text-sm text-muted-foreground">API 端点</p>
                <p className="text-2xl font-bold">{s.total_endpoints}</p>
              </div>
              <div className="rounded-lg border bg-card p-4">
                <p className="text-sm text-muted-foreground">通过率</p>
                <p className="text-2xl font-bold">{s.pass_rate ?? 0}%</p>
              </div>
              <div className="rounded-lg border bg-card p-4">
                <p className="text-sm text-muted-foreground">测试执行</p>
                <p className="text-2xl font-bold">{s.total_executions}</p>
              </div>
              <div className="rounded-lg border bg-card p-4">
                <p className="text-sm text-muted-foreground">平均耗时</p>
                <p className="text-2xl font-bold">
                  {s.avg_duration_ms > 1000
                    ? `${(s.avg_duration_ms / 1000).toFixed(1)}s`
                    : `${Math.round(s.avg_duration_ms || 0)}ms`}
                </p>
              </div>
            </div>

            {/* 最近执行记录 */}
            <div className="rounded-lg border bg-card">
              <div className="border-b px-4 py-3">
                <h3 className="font-medium">最近执行记录</h3>
              </div>
              {recent.length > 0 ? (
                <div className="divide-y text-sm">
                  {recent.map((log: any, i: number) => (
                    <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                      <span className={log.status === "success" ? "text-green-600" : "text-red-600"}>
                        {log.status === "success" ? "✓" : "✗"}
                      </span>
                      <span className="flex-1 truncate">{log.script_name || "未知"}</span>
                      <span className="text-muted-foreground">{log.user_id}</span>
                      <span className="text-muted-foreground">
                        {log.duration_ms ? `${(log.duration_ms / 1000).toFixed(1)}s` : "-"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  暂无执行记录。运行 AI 测试后，结果将在这里展示。
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </MainLayout>
  );
}
