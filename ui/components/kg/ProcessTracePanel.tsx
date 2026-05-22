"use client";

import * as React from "react";
import { Network, ArrowRight, ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getProcessTrace, type ProcessTraceResult } from "@/lib/api/code-analysis";

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

interface ProcessTracePanelProps {
  projectId: string;
  processId: string;
  onBack?: () => void;
}

export function ProcessTracePanel({ projectId, processId, onBack }: ProcessTracePanelProps) {
  const [trace, setTrace] = React.useState<ProcessTraceResult | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (!projectId || !processId) return;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const res = await getProcessTrace(projectId, processId);
        if (res.success && res.data) {
          setTrace(res.data);
        } else {
          setError("未找到执行流数据");
        }
      } catch {
        setError("加载失败");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [projectId, processId]);

  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !trace) {
    return (
      <div className="text-sm text-muted-foreground text-center py-8">
        {error || "选择执行流以查看调用链"}
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* 头部 */}
      <div>
        <Button
          size="sm"
          variant="ghost"
          className="mb-2 -ml-2 text-xs text-muted-foreground hover:text-foreground"
          onClick={onBack}
        >
          <ArrowLeft className="mr-1 h-3 w-3" /> 返回执行流列表
        </Button>
        <div className="flex items-center gap-3 mb-2">
          <Badge className={TYPE_COLORS.process || ""}>
            process
          </Badge>
          <h2 className="text-xl font-bold">{trace.name}</h2>
        </div>
        <div className="text-xs text-muted-foreground space-y-1">
          {trace.entry_point && (
            <div>
              入口: <span className="font-mono text-foreground">{trace.entry_point.split("::").pop()}</span>
            </div>
          )}
          <div>
            步骤数: <span className="text-foreground">{trace.step_count}</span> |
            调用链长度: <span className="text-foreground">{trace.chain.length}</span>
          </div>
        </div>
      </div>

      {/* 调用链 */}
      <div className="rounded-lg border bg-white">
        <div className="px-4 py-3 border-b bg-muted/30">
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <Network className="h-4 w-4 text-rose-500" />
            函数调用链
          </h3>
        </div>
        <div className="p-4 space-y-1">
          {trace.chain.length === 0 ? (
            <p className="text-sm text-muted-foreground">未找到调用链</p>
          ) : (
            trace.chain.map((step, idx) => {
              const indent = step.depth * 20;
              const isLast = idx === trace.chain.length - 1;
              return (
                <div
                  key={step.node_id}
                  className="flex items-start gap-2 py-1.5 rounded-md hover:bg-muted/40 transition-colors"
                  style={{ paddingLeft: `${indent + 12}px` }}
                >
                  <div className="mt-0.5 shrink-0">
                    {step.depth > 0 ? (
                      <ArrowRight className="h-3 w-3 text-muted-foreground" />
                    ) : (
                      <Network className="h-3 w-3 text-rose-500" />
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge className={`text-[10px] px-1 py-0 ${TYPE_COLORS[step.type] || ""}`}>
                        {step.type}
                      </Badge>
                      <span className="text-sm font-medium">{step.name}</span>
                    </div>
                    {step.file_path && (
                      <p className="text-[11px] text-muted-foreground truncate">
                        {step.file_path}
                      </p>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
