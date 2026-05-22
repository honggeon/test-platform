"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { MainLayout } from "@/components/layout";
import { listTestReports } from "@/lib/api/test-reports";

export default function AllureReportsPage() {
  const params = useParams();
  const projectId = params.projectId as string;

  const [reports, setReports] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    setLoading(true);
    listTestReports(projectId, 1, 50)
      .then((res: any) => {
        // 过滤出 Allure 报告
        const allureOnes = (res.data || []).filter((r: any) =>
          r.id && r.id.startsWith("allure_")
        );
        setReports(allureOnes);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [projectId]);

  return (
    <MainLayout title="Allure 报告">
      <div className="space-y-4 p-4">
        <div>
          <h1 className="text-xl font-bold">Allure 测试报告</h1>
          <p className="text-sm text-muted-foreground mt-1">
            项目 {projectId} 的 Allure 可视化测试报告
          </p>
        </div>

        {loading ? (
          <div className="text-center py-12 text-muted-foreground text-sm">
            加载中...
          </div>
        ) : reports.length === 0 ? (
          <div className="text-center py-12 border rounded-lg bg-card">
            <p className="text-muted-foreground text-sm">暂无 Allure 报告</p>
            <p className="text-xs text-muted-foreground mt-1">
              运行测试后，Allure 报告会显示在这里
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {reports.map((report: any) => {
              const passRate =
                report.summary?.total > 0
                  ? Math.round(
                      (report.summary.passed / report.summary.total) * 100
                    )
                  : 0;

              return (
                <div
                  key={report.id}
                  className="rounded-lg border bg-card p-4 hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm font-medium">
                        {report.generated_at
                          ? new Date(report.generated_at).toLocaleString(
                              "zh-CN"
                            )
                          : report.id}
                      </span>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                        <span>通过: {report.summary?.passed || 0}</span>
                        <span>失败: {report.summary?.failed || 0}</span>
                        <span>跳过: {report.summary?.skipped || 0}</span>
                        <span>总计: {report.summary?.total || 0}</span>
                        <span
                          className={
                            passRate >= 80
                              ? "text-green-600 font-medium"
                              : passRate >= 50
                              ? "text-yellow-600 font-medium"
                              : "text-red-600 font-medium"
                          }
                        >
                          {passRate}%
                        </span>
                      </div>
                    </div>
                    <a
                      href={`/api/v2/projects/${report.project_identifier}/test-reports/${report.id}/view`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 rounded-md bg-purple-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-700 transition-colors"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                      查看 Allure 报告
                    </a>
                  </div>
                  {report.summary?.total > 0 && (
                    <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-purple-500 transition-all"
                        style={{ width: `${passRate}%` }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
