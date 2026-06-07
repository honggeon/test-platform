/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * 场景列表面板
 * 显示项目中的所有测试场景
 */

"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Clock,
  CheckCircle2,
  XCircle,
  MoreVertical,
  Trash2,
  Edit,
  Play,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { listScenarios, deleteScenario, bulkDeleteScenarios, bulkRunScenarios } from "@/lib/api/scenarios";
import { useLanguage } from "@/providers/LanguageProvider";
import type { Scenario } from "@/types/scenario";

interface ScenarioListPanelProps {
  projectId: string;
  selectedScenarioId: string | null;
  onSelectScenario: (scenarioId: string) => void;
  refreshTrigger?: number;
  onRefresh?: () => void;
}

export function ScenarioListPanel({
  projectId,
  selectedScenarioId,
  onSelectScenario,
  refreshTrigger,
  onRefresh,
}: ScenarioListPanelProps) {
  const { t } = useLanguage();
  const [scenarios, setScenarios] = React.useState<Scenario[]>([]);
  const [filteredScenarios, setFilteredScenarios] = React.useState<Scenario[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [deletingScenario, setDeletingScenario] = React.useState<Scenario | null>(null);
  const [bulkDeleteDialogOpen, setBulkDeleteDialogOpen] = React.useState(false);

  // 加载场景列表
  React.useEffect(() => {
    loadScenarios();
  }, [projectId, refreshTrigger]);

  // 搜索过滤
  React.useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredScenarios(scenarios);
      return;
    }
    const query = searchQuery.toLowerCase();
    const filtered = scenarios.filter(
      (s) =>
        s.name.toLowerCase().includes(query) ||
        s.identifier.toLowerCase().includes(query) ||
        (s.description && s.description.toLowerCase().includes(query))
    );
    setFilteredScenarios(filtered);
  }, [searchQuery, scenarios]);

  const loadScenarios = async () => {
    try {
      setLoading(true);
      const result = await listScenarios(projectId, { page: 1, page_size: 100 });
      setScenarios(result.items);
      setFilteredScenarios(result.items);
    } catch (error) {
      console.error("Failed to load scenarios:", error);
      toast.error(t("scenarioTests.scenarioListLoadFailed"));
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deletingScenario) return;

    try {
      await deleteScenario(deletingScenario.id);
      toast.success(t("scenarioTests.scenarioDeleted"));
      setScenarios(scenarios.filter((s) => s.id !== deletingScenario.id));
      setDeleteDialogOpen(false);
      setDeletingScenario(null);
      if (onRefresh) onRefresh();
    } catch (error) {
      console.error("Failed to delete scenario:", error);
      toast.error(t("scenarioTests.scenarioDeleteFailed"));
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(filteredScenarios.map((s) => s.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelect = (id: string, checked: boolean) => {
    const newIds = new Set(selectedIds);
    if (checked) {
      newIds.add(id);
    } else {
      newIds.delete(id);
    }
    setSelectedIds(newIds);
  };

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    try {
      await bulkDeleteScenarios(Array.from(selectedIds));
      toast.success(`已删除 ${selectedIds.size} 个场景`);
      setSelectedIds(new Set());
      loadScenarios();
      if (onRefresh) onRefresh();
    } catch (error) {
      console.error("Failed to bulk delete scenarios:", error);
      toast.error("批量删除失败");
    }
    setBulkDeleteDialogOpen(false);
  };

  const handleBulkRun = async () => {
    if (selectedIds.size === 0) return;
    try {
      await bulkRunScenarios(Array.from(selectedIds));
      toast.success(`已启动 ${selectedIds.size} 个场景的执行`);
      setSelectedIds(new Set());
      if (onRefresh) onRefresh();
    } catch (error) {
      console.error("Failed to bulk run scenarios:", error);
      toast.error("批量执行失败");
    }
  };

  const getStatusBadge = (scenario: Scenario) => {
    switch (scenario.status) {
      case "active":
        return <Badge className="bg-green-100 text-green-700">{t("apiTests.active")}</Badge>;
      case "draft":
        return <Badge variant="secondary">{t("apiTests.draft")}</Badge>;
      case "archived":
        return <Badge variant="outline">{t("status.archived")}</Badge>;
      default:
        return <Badge variant="secondary">{scenario.status}</Badge>;
    }
  };

  const getLastRunBadge = (scenario: Scenario) => {
    if (!scenario.last_run_status) {
      return null;
    }

    switch (scenario.last_run_status) {
      case "completed":
        return (
          <div className="flex items-center gap-1 text-xs text-green-600">
            <CheckCircle2 className="h-3 w-3" />
            <span>{t("scenarioTests.lastRunSuccess")}</span>
          </div>
        );
      case "failed":
        return (
          <div className="flex items-center gap-1 text-xs text-red-600">
            <XCircle className="h-3 w-3" />
            <span>{t("scenarioTests.lastRunFailed")}</span>
          </div>
        );
      default:
        return (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>{t("scenarioTests.lastRunRunning")}</span>
          </div>
        );
    }
  };

  const isAllSelected =
    filteredScenarios.length > 0 && selectedIds.size === filteredScenarios.length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full p-4">
        <div className="text-center text-sm text-muted-foreground">{t("scenarioTests.loadingScenarios")}</div>
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center">
        <Workflow className="h-12 w-12 text-muted-foreground mb-3" />
        <p className="text-sm font-medium mb-1">暂无测试场景</p>
        <p className="text-xs text-muted-foreground">
          点击"新建"按钮创建第一个场景
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="h-full flex flex-col">
        {/* 搜索栏 */}
        <div className="p-3 border-b">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索场景..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* 批量操作栏 */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-3 border-b bg-muted/50 px-4 py-2">
            <span className="text-sm text-muted-foreground">
              已选择 {selectedIds.size} 项
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={handleBulkRun}
            >
              <Play className="mr-2 h-4 w-4" />
              批量运行
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
              onClick={() => setBulkDeleteDialogOpen(true)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              批量删除
            </Button>
          </div>
        )}

        {/* 全选标题 */}
        <div className="px-4 py-2 border-b flex items-center gap-2">
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={handleSelectAll}
            aria-label="全选"
          />
          <span className="text-xs text-muted-foreground">
            {filteredScenarios.length} 个场景
          </span>
        </div>

        {/* 场景列表 */}
        <div className="flex-1 overflow-y-auto">
          <div className="divide-y">
            {filteredScenarios.map((scenario) => (
              <div
                key={scenario.id}
                className={`p-4 hover:bg-muted/50 cursor-pointer transition-colors ${
                  selectedScenarioId === scenario.id ? "bg-muted" : ""
                }`}
                onClick={() => onSelectScenario(scenario.id)}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <div
                      className="mt-0.5 shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Checkbox
                        checked={selectedIds.has(scenario.id)}
                        onCheckedChange={(checked) =>
                          handleSelect(scenario.id, checked as boolean)
                        }
                        aria-label={`选择 ${scenario.name}`}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-muted-foreground">
                          {scenario.identifier}
                        </span>
                        {getStatusBadge(scenario)}
                      </div>
                      <h4 className="font-medium text-sm truncate">{scenario.name}</h4>
                      {scenario.description && (
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                          {scenario.description}
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        <span>{scenario.total_steps}{t("scenarioTests.stepsCount")}</span>
                        {scenario.last_run_at && (
                          <span>
                            {new Date(scenario.last_run_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                      {getLastRunBadge(scenario)}
                    </div>
                  </div>

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreVertical className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectScenario(scenario.id);
                        }}
                      >
                        <Edit className="mr-2 h-4 w-4" />
                        {t("scenarioTests.edit")}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingScenario(scenario);
                          setDeleteDialogOpen(true);
                        }}
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        {t("scenarioTests.delete")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 删除确认对话框 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("scenarioTests.confirmDeleteScenario")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("scenarioTests.confirmDeleteScenarioMessage", { name: deletingScenario?.name || "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive">
              {t("scenarioTests.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 批量删除确认对话框 */}
      <AlertDialog open={bulkDeleteDialogOpen} onOpenChange={setBulkDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认批量删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除选中的 {selectedIds.size} 个场景吗？此操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setBulkDeleteDialogOpen(false)}>
              {t("common.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleBulkDelete} className="bg-destructive">
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// 导入 Workflow 图标（临时解决，实际应该在顶部导入）
function Workflow({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <rect width="8" height="8" x="3" y="3" rx="2" />
      <path d="M7 11v4a2 2 0 0 0 2 2h4" />
      <rect width="8" height="8" x="13" y="13" rx="2" />
    </svg>
  );
}
