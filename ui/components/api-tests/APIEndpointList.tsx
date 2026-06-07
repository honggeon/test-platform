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
import {
  Search,
  FileCode,
  Globe,
  Zap,
  Play,
  Clock,
  Trash2,
  MoreVertical,
  Pencil,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLanguage } from "@/providers/LanguageProvider";
import type { APIEndpoint } from "@/lib/api/api-endpoints";

interface APIEndpointListProps {
  endpoints: APIEndpoint[];
  loading: boolean;
  selectedEndpointId?: string | null;
  actualTestCasesCounts?: Record<string, number>;
  onSelectEndpoint: (endpointId: string) => void;
  onSearch: (query: string) => void;
  onDeleteEndpoint?: (endpoint: APIEndpoint) => void;
  onBulkDelete?: (endpointIds: string[]) => void;
  folderName?: string;
}

// HTTP 方法颜色映射
const methodColors: Record<string, string> = {
  GET: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  POST: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  PUT: "bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300",
  PATCH: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300",
  DELETE: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

export function APIEndpointList({
  endpoints,
  loading,
  selectedEndpointId,
  actualTestCasesCounts = {},
  onSelectEndpoint,
  onSearch,
  onDeleteEndpoint,
  onBulkDelete,
  folderName,
}: APIEndpointListProps) {
  const { t } = useLanguage();
  const [searchQuery, setSearchQuery] = React.useState("");
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    onSearch(value);
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(endpoints.map((ep) => ep.id)));
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

  const handleBulkDelete = () => {
    if (onBulkDelete && selectedIds.size > 0) {
      onBulkDelete(Array.from(selectedIds));
      setSelectedIds(new Set());
    }
  };

  const isAllSelected =
    endpoints.length > 0 && selectedIds.size === endpoints.length;

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  if (endpoints.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <FileCode className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
          <p className="text-lg font-medium mb-2">{t("apiTests.noEndpointData")}</p>
          <p className="text-sm text-muted-foreground mb-4">
            {t("apiTests.noEndpointsInFolder")}
          </p>
          <p className="text-xs text-muted-foreground">
            {t("apiTests.clickToImportAPI")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 搜索栏 */}
      <div className="p-3 border-b">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t("apiTests.searchEndpoints") || "搜索接口..."}
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* 全选标题 + 批量操作栏 */}
      <div className="px-4 py-2 border-b flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Checkbox
            checked={isAllSelected}
            onCheckedChange={handleSelectAll}
            aria-label="全选"
          />
          <span className="text-xs text-muted-foreground">
            {selectedIds.size > 0 ? `已选择 ${selectedIds.size} / ${endpoints.length} 个接口` : `${endpoints.length} 个接口`}
          </span>
        </div>
        {selectedIds.size > 0 && onBulkDelete && (
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
            onClick={handleBulkDelete}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            批量删除
          </Button>
        )}
      </div>

      {/* 接口列表 */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          <div className="space-y-2">
            {endpoints.map((endpoint) => (
              <div
                key={endpoint.id}
                className={cn(
                  "group rounded-lg border p-4 hover:bg-accent/50 cursor-pointer transition-all",
                  selectedEndpointId === endpoint.id && "bg-accent border-primary"
                )}
                onClick={() => onSelectEndpoint(endpoint.id)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3 flex-1 min-w-0">
                    {/* 复选框 */}
                    <div
                      className="shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Checkbox
                        checked={selectedIds.has(endpoint.id)}
                        onCheckedChange={(checked) =>
                          handleSelect(endpoint.id, checked as boolean)
                        }
                        aria-label={`选择 ${endpoint.display_name}`}
                      />
                    </div>

                    {/* HTTP 方法标签 */}
                    <Badge
                      className={cn(
                        "shrink-0 font-mono text-xs",
                        methodColors[endpoint.method] || "bg-gray-100 text-gray-700"
                      )}
                    >
                      {endpoint.method}
                    </Badge>

                    {/* 接口名称 */}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-sm truncate">
                        {endpoint.display_name}
                      </h3>
                      <p className="text-xs text-muted-foreground truncate font-mono mt-1">
                        {endpoint.path}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* 状态指示器 */}
                    {endpoint.last_run_status && (
                      <Badge
                        variant="outline"
                        className={cn(
                          "shrink-0",
                          endpoint.last_run_status === "passed" && "border-green-500 text-green-700",
                          endpoint.last_run_status === "failed" && "border-red-500 text-red-700",
                          endpoint.last_run_status === "running" && "border-blue-500 text-blue-700"
                        )}
                      >
                        {endpoint.last_run_status === "passed" && "✓ " + t("status.passed")}
                        {endpoint.last_run_status === "failed" && "✗ " + t("status.failed")}
                        {endpoint.last_run_status === "running" && "⟳ " + t("status.running")}
                      </Badge>
                    )}

                    {/* 操作菜单 */}
                    {onDeleteEndpoint && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 opacity-0 group-hover:opacity-100"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteEndpoint(endpoint);
                            }}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            {t("common.delete")}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </div>

                {/* 描述 */}
                {endpoint.summary && (
                  <p className="text-xs text-muted-foreground line-clamp-2 mb-3">
                    {endpoint.summary}
                  </p>
                )}

                {/* 统计信息 */}
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <FileCode className="h-3.5 w-3.5" />
                    <span>
                      {actualTestCasesCounts[endpoint.id] || endpoint.total_test_cases} {t("apiTests.testCasesCount")}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Play className="h-3.5 w-3.5" />
                    <span>{endpoint.total_test_runs} {t("testRuns.title")}</span>
                  </div>
                  {endpoint.tag_group && (
                    <div className="flex items-center gap-1">
                      <Globe className="h-3.5 w-3.5" />
                      <span>{endpoint.tag_group}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
