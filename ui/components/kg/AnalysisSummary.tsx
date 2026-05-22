"use client";

import * as React from "react";
import {
  BarChart3,
  FileText,
  Code2,
  Network,
  FolderTree,
  Loader2,
  GitCommit,
  CheckCircle,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { getGraphData } from "@/lib/api/code-analysis";

interface AnalysisSummaryProps {
  projectId: string;
  analysisStats: Record<string, number> | null;
  exploringGraph: boolean;
  onExploreGraph: () => void;
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className={`h-4 w-4 ${color}`} />
        {label}
      </div>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}

export function AnalysisSummary({
  projectId,
  analysisStats,
  exploringGraph,
  onExploreGraph,
}: AnalysisSummaryProps) {
  const [typeCounts, setTypeCounts] = React.useState<Record<string, number>>({});
  const [callStats, setCallStats] = React.useState<{ high: number; low: number; total: number } | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!projectId || !analysisStats?.node) return;
    const load = async () => {
      setLoading(true);
      try {
        const res = await getGraphData(projectId, 2000, 2000);
        if (res.success && res.data) {
          const counts: Record<string, number> = {};
          for (const n of res.data.nodes) {
            counts[n.type] = (counts[n.type] || 0) + 1;
          }
          setTypeCounts(counts);

          // 统计 CALLS 边数量
          const calls = res.data.edges.filter((e) => e.type === "CALLS");
          setCallStats({ high: 0, low: 0, total: calls.length });
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [projectId, analysisStats?.node]);

  const topTypes = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  const maxCount = topTypes[0]?.[1] || 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <BarChart3 className="h-5 w-5 text-muted-foreground" />
        <h2 className="text-lg font-semibold">代码分析摘要</h2>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="文件"
          value={analysisStats ? String(analysisStats.file || 0) : "—"}
          icon={FileText}
          color="text-blue-500"
        />
        <StatCard
          label="节点"
          value={analysisStats ? String(analysisStats.node || 0) : "—"}
          icon={Code2}
          color="text-purple-500"
        />
        <StatCard
          label="关系"
          value={analysisStats ? String(analysisStats.relationship || 0) : "—"}
          icon={Network}
          color="text-green-500"
        />
        <StatCard
          label="目录"
          value={analysisStats ? String(analysisStats.folder || 0) : "—"}
          icon={FolderTree}
          color="text-orange-500"
        />
      </div>

      {topTypes.length > 0 && (
        <div className="rounded-lg border p-4 space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">节点类型分布</h3>
          <div className="space-y-2">
            {topTypes.map(([type, count]) => (
              <div key={type} className="flex items-center gap-3">
                <span className="w-20 text-xs text-muted-foreground capitalize">{type}</span>
                <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary rounded-full"
                    style={{ width: `${(count / maxCount) * 100}%` }}
                  />
                </div>
                <span className="w-10 text-xs text-right tabular-nums">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {callStats && callStats.total > 0 && (
        <div className="rounded-lg border p-4 flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="text-muted-foreground">调用关系:</span>
            <span className="font-medium">{callStats.total} 条 CALLS 边</span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          onClick={onExploreGraph}
          disabled={exploringGraph || loading}
        >
          {exploringGraph || loading ? (
            <><Loader2 className="mr-1 h-3 w-3 animate-spin" />加载中</>
          ) : (
            <><Network className="mr-1 h-3 w-3" />探索完整图谱</>
          )}
        </Button>
        <p className="text-sm text-muted-foreground">
          或前往「搜索」标签页搜索代码符号查看详情和调用关系
        </p>
      </div>
    </div>
  );
}
