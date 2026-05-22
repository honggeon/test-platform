"use client";

import * as React from "react";
import { GitBranch, Loader2, AlertTriangle, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import type { CodeRepoStatus } from "@/lib/api/code-repo";
import type { StalenessReport } from "@/lib/api/code-analysis";

interface CodeRepoConfigProps {
  projectId: string;
  repoStatus: CodeRepoStatus | null;
  loading: boolean;
  repoUrl: string;
  repoBranch: string;
  analyzing: boolean;
  error: string;
  staleness: StalenessReport | null;
  onRepoUrlChange: (url: string) => void;
  onRepoBranchChange: (branch: string) => void;
  onSave: () => void;
  onAnalyze: () => void;
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-green-500" : "bg-gray-300"}`} />
      <span>{label}</span>
    </div>
  );
}

export function CodeRepoConfig({
  repoStatus,
  loading,
  repoUrl,
  repoBranch,
  analyzing,
  error,
  staleness,
  onRepoUrlChange,
  onRepoBranchChange,
  onSave,
  onAnalyze,
}: CodeRepoConfigProps) {
  return (
    <div className="border-b p-4 space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-medium">
        <GitBranch className="h-4 w-4" /> 代码仓库
      </h3>
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 加载中...
        </div>
      ) : (
        <>
          <Input
            placeholder="Git 地址或本地路径"
            value={repoUrl}
            onChange={(e) => onRepoUrlChange(e.target.value)}
            className="text-xs"
          />
          <Input
            placeholder="分支 (默认 main)"
            value={repoBranch}
            onChange={(e) => onRepoBranchChange(e.target.value)}
            className="text-xs"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              className="flex-1"
              onClick={onSave}
              disabled={!repoUrl.trim()}
            >
              保存
            </Button>
            <Button
              size="sm"
              className="flex-1"
              onClick={onAnalyze}
              disabled={analyzing || !repoUrl.trim()}
            >
              {analyzing ? (
                <><Loader2 className="mr-1 h-3 w-3 animate-spin" />分析中</>
              ) : (
                "分析"
              )}
            </Button>
          </div>
          {error && <p className="text-xs text-red-500">{error}</p>}
          {repoStatus && (
            <div className="space-y-1 text-xs text-muted-foreground">
              <StatusDot ok={repoStatus.configured} label="已配置" />
              <StatusDot ok={repoStatus.cloned} label="已克隆" />
              <StatusDot ok={repoStatus.analyzed} label="已分析" />
            </div>
          )}
          {staleness && repoStatus?.analyzed && (
            <div className={`rounded-md px-2.5 py-2 text-xs ${
              staleness.is_stale
                ? "bg-amber-50 text-amber-700 border border-amber-200"
                : "bg-green-50 text-green-700 border border-green-200"
            }`}>
              <div className="flex items-center gap-1.5 font-medium">
                {staleness.is_stale ? (
                  <><AlertTriangle className="h-3.5 w-3.5" /> 图谱已过期</>
                ) : (
                  <><CheckCircle className="h-3.5 w-3.5" /> 图谱是最新的</>
                )}
              </div>
              <div className="mt-1 space-y-0.5 text-[11px] opacity-90">
                <div>索引: {staleness.indexed_commit?.slice(0, 8) || "?"}</div>
                <div>HEAD: {staleness.current_head?.slice(0, 8) || "?"}</div>
                {staleness.commits_behind > 0 && (
                  <div>落后: {staleness.commits_behind} commits</div>
                )}
              </div>
            </div>
          )}
          {analyzing && repoStatus && (
            <div className="pt-1">
              <Progress value={Math.max(repoStatus.progress, 2)} className="h-1.5" />
              <p className="mt-1 text-xs text-muted-foreground">{repoStatus.current_step}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
