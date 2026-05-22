/**
 * 执行流面板组件
 *
 * 展示检测到的 Process 执行流列表，支持点击高亮调用链。
 */

"use client";

import * as React from "react";
import { Network, ArrowRight } from "lucide-react";

export interface ProcessInfo {
  id: string;
  name: string;
  process_type: string;
  step_count: number;
  entry_point?: string;
}

interface ProcessPanelProps {
  processes: ProcessInfo[];
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
}

export function ProcessPanel({ processes, selectedId, onSelect }: ProcessPanelProps) {
  if (processes.length === 0) {
    return (
      <div className="text-xs text-muted-foreground text-center py-4">
        未检测到执行流
      </div>
    );
  }

  const typeLabels: Record<string, string> = {
    api_handler: "API 处理器",
    cli: "CLI 命令",
    background_job: "后台任务",
    function: "函数链",
  };

  return (
    <div className="space-y-2">
      {processes.map((proc) => (
        <button
          key={proc.id}
          onClick={() => onSelect?.(proc.id === selectedId ? null : proc.id)}
          className={`w-full text-left rounded-lg border p-2.5 transition-colors ${
            proc.id === selectedId
              ? "bg-primary/5 border-primary ring-1 ring-primary"
              : "hover:bg-muted/50"
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Network className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-medium truncate">{proc.name}</span>
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground">
              {typeLabels[proc.process_type] || proc.process_type}
            </span>
          </div>
          <div className="mt-1.5 flex items-center gap-3 text-[10px] text-muted-foreground">
            <span className="flex items-center gap-1">
              <ArrowRight className="h-3 w-3" />
              {proc.step_count} 步
            </span>
            {proc.entry_point && (
              <span className="truncate">入口: {proc.entry_point.split("::").pop()}</span>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}
