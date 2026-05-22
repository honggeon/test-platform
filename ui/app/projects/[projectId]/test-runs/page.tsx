/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Plus,
  Search,
  PlayCircle,
  CheckCircle2,
  XCircle,
  Clock,
  MoreHorizontal,
  Pencil,
  Trash2,
  Eye,
  Activity,
} from "lucide-react";
import { MainLayout } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { createDiagnosisReport, listDiagnosisReports } from "@/lib/api/diagnosis";

// 模拟数据
const mockTestRuns = [
  {
    id: "1",
    name: "回归测试 - Sprint 23",
    description: "Sprint 23 版本回归测试",
    state: "in_progress",
    created_at: "2024-01-15T10:00:00Z",
    total_tests: 50,
    passed_tests: 30,
    failed_tests: 5,
    skipped_tests: 2,
    blocked_tests: 0,
  },
  {
    id: "2",
    name: "冒烟测试 - v2.1.0",
    description: "v2.1.0 版本冒烟测试",
    state: "completed",
    created_at: "2024-01-10T09:00:00Z",
    total_tests: 20,
    passed_tests: 18,
    failed_tests: 2,
    skipped_tests: 0,
    blocked_tests: 0,
  },
  {
    id: "3",
    name: "功能测试 - 用户模块",
    description: "用户模块功能测试",
    state: "not_started",
    created_at: "2024-01-08T14:00:00Z",
    total_tests: 35,
    passed_tests: 0,
    failed_tests: 0,
    skipped_tests: 0,
    blocked_tests: 0,
  },
];

const stateLabels: Record<string, { label: string; color: string }> = {
  not_started: { label: "未开始", color: "secondary" },
  in_progress: { label: "进行中", color: "default" },
  completed: { label: "已完成", color: "success" },
  aborted: { label: "已中止", color: "destructive" },
};

export default function TestRunsPage() {
  const params = useParams();
  const projectId = params.projectId as string;
  const router = useRouter();

  const [testRuns, setTestRuns] = React.useState(mockTestRuns);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [createDialogOpen, setCreateDialogOpen] = React.useState(false);
  const [formData, setFormData] = React.useState({
    name: "",
    description: "",
  });
  const [diagnosingRunId, setDiagnosingRunId] = React.useState<string | null>(null);

  const handleDiagnose = async (runId: string) => {
    setDiagnosingRunId(runId);
    try {
      const listRes = await listDiagnosisReports(projectId, { run_id: runId });
      if (listRes.success && listRes.data.items.length > 0) {
        router.push(`/projects/${projectId}/diagnosis`);
        return;
      }
      const res = await createDiagnosisReport(projectId, runId);
      if (res.success) {
        toast.success("诊断已触发", {
          description: `报告 ID: ${res.data.report_id}，正在分析中...`,
        });
      }
    } catch (e) {
      toast.error("触发诊断失败", { description: String(e) });
    } finally {
      setDiagnosingRunId(null);
    }
  };

  const filteredRuns = React.useMemo(() => {
    if (!searchQuery) return testRuns;
    const query = searchQuery.toLowerCase();
    return testRuns.filter(
      (run) =>
        run.name.toLowerCase().includes(query) ||
        run.description?.toLowerCase().includes(query)
    );
  }, [testRuns, searchQuery]);

  const getProgress = (run: (typeof mockTestRuns)[0]) => {
    if (run.total_tests === 0) return 0;
    return Math.round(
      ((run.passed_tests + run.failed_tests + run.skipped_tests + run.blocked_tests) /
        run.total_tests) *
        100
    );
  };

  return (
    <MainLayout title="测试运行">
      <div className="space-y-6">
        {/* 工具栏 */}
        <div className="flex items-center justify-between">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索测试运行..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-64 pl-9"
            />
          </div>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            新建测试运行
          </Button>
        </div>

        {/* 测试运行列表 */}
        <div className="rounded-lg border bg-card">
          {filteredRuns.length === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2">
              <PlayCircle className="h-12 w-12 text-muted-foreground/50" />
              <p className="text-muted-foreground">
                {searchQuery ? "没有找到匹配的测试运行" : "暂无测试运行"}
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {filteredRuns.map((run) => (
                <div
                  key={run.id}
                  className="flex items-center justify-between p-4 hover:bg-muted/50"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <PlayCircle className="h-5 w-5 text-primary" />
                      <h3 className="font-medium">{run.name}</h3>
                      <Badge
                        variant={
                          stateLabels[run.state]?.color as
                            | "default"
                            | "secondary"
                            | "destructive"
                        }
                      >
                        {stateLabels[run.state]?.label}
                      </Badge>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {run.description}
                    </p>
                    <div className="mt-3 flex items-center gap-6">
                      <div className="flex items-center gap-4 text-sm">
                        <span className="flex items-center gap-1 text-green-600">
                          <CheckCircle2 className="h-4 w-4" />
                          {run.passed_tests} 通过
                        </span>
                        <span className="flex items-center gap-1 text-red-600">
                          <XCircle className="h-4 w-4" />
                          {run.failed_tests} 失败
                        </span>
                        <span className="flex items-center gap-1 text-muted-foreground">
                          <Clock className="h-4 w-4" />
                          {run.total_tests - run.passed_tests - run.failed_tests - run.skipped_tests - run.blocked_tests} 待执行
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Progress value={getProgress(run)} className="w-32" />
                        <span className="text-sm text-muted-foreground">
                          {getProgress(run)}%
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {run.failed_tests > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDiagnose(run.id)}
                        disabled={diagnosingRunId === run.id}
                      >
                        <Activity className="mr-2 h-4 w-4" />
                        {diagnosingRunId === run.id ? "诊断中..." : "诊断"}
                      </Button>
                    )}
                    <Button variant="outline" size="sm">
                      <Eye className="mr-2 h-4 w-4" />
                      查看
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem>
                          <Pencil className="mr-2 h-4 w-4" />
                          编辑
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive">
                          <Trash2 className="mr-2 h-4 w-4" />
                          删除
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 创建对话框 */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建测试运行</DialogTitle>
            <DialogDescription>创建一个新的测试运行</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">名称</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="请输入测试运行名称"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">描述</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="请输入描述（可选）"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={() => setCreateDialogOpen(false)}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </MainLayout>
  );
}

