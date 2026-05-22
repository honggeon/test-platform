"use client";

import * as React from "react";
import {
  AlertTriangle,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type {
  ChangeImpactResult,
  CommitInfo,
} from "@/lib/api/code-analysis";
import { analyzeChangeImpact, listCommits } from "@/lib/api/code-analysis";

interface ChangeImpactAnalyzerProps {
  projectId: string;
  hasAnalysis: boolean;
}

type ChangeImpactMode = "manual" | "git_diff" | "compare_commits";

export function ChangeImpactAnalyzer({
  projectId,
  hasAnalysis,
}: ChangeImpactAnalyzerProps) {
  const [changeImpactMode, setChangeImpactMode] = React.useState<ChangeImpactMode>("manual");
  const [ciFilePath, setCiFilePath] = React.useState("");
  const [ciStartLine, setCiStartLine] = React.useState("");
  const [ciEndLine, setCiEndLine] = React.useState("");
  const [ciBaseCommit, setCiBaseCommit] = React.useState("HEAD~1");
  const [ciTargetCommit, setCiTargetCommit] = React.useState("HEAD");
  const [ciBaseCommitSelect, setCiBaseCommitSelect] = React.useState("");
  const [ciTargetCommitSelect, setCiTargetCommitSelect] = React.useState("");
  const [ciMaxDepth, setCiMaxDepth] = React.useState("3");
  const [ciLoading, setCiLoading] = React.useState(false);
  const [ciResult, setCiResult] = React.useState<ChangeImpactResult | null>(null);
  const [commits, setCommits] = React.useState<CommitInfo[]>([]);
  const [commitsError, setCommitsError] = React.useState("");
  const [error, setError] = React.useState("");

  // 加载 commit 列表
  const loadCommits = React.useCallback(async () => {
    if (!projectId || !hasAnalysis) return;
    setCommitsError("");
    try {
      const res = await listCommits(projectId, 20);
      if (res.success && res.data) {
        setCommits(res.data);
        if (res.data.length >= 2) {
          setCiBaseCommitSelect(res.data[1].commit_hash);
          setCiTargetCommitSelect(res.data[0].commit_hash);
        } else if (res.data.length >= 1) {
          setCiTargetCommitSelect(res.data[0].commit_hash);
        }
      } else {
        setCommitsError("API 返回异常: " + JSON.stringify(res));
      }
    } catch (e: unknown) {
      setCommitsError(e instanceof Error ? e.message : "加载 commit 列表失败");
    }
  }, [projectId, hasAnalysis]);

  React.useEffect(() => {
    if (hasAnalysis) loadCommits();
  }, [hasAnalysis, loadCommits]);

  const handleAnalyze = async () => {
    setCiLoading(true);
    setCiResult(null);
    setError("");
    try {
      const req: Parameters<typeof analyzeChangeImpact>[1] = {
        mode: changeImpactMode,
        max_depth: parseInt(ciMaxDepth || "3"),
      };
      if (changeImpactMode === "manual") {
        req.file_path = ciFilePath || undefined;
        req.start_line = parseInt(ciStartLine || "0");
        req.end_line = parseInt(ciEndLine || "0");
      } else if (changeImpactMode === "git_diff") {
        req.base_commit = ciBaseCommit || undefined;
        req.target_commit = ciTargetCommit || undefined;
      } else if (changeImpactMode === "compare_commits") {
        req.base_commit = ciBaseCommitSelect || undefined;
        req.target_commit = ciTargetCommitSelect || undefined;
      }
      const res = await analyzeChangeImpact(projectId, req);
      if (res.success && res.data) {
        setCiResult(res.data);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "分析失败");
    }
    setCiLoading(false);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-500" />
        <h3 className="text-base font-medium">变更影响分析</h3>
      </div>

      {/* 模式切换 */}
      <div className="flex gap-2 flex-wrap">
        {[
          { key: "manual" as const, label: "手动输入" },
          { key: "git_diff" as const, label: "Git Diff" },
          { key: "compare_commits" as const, label: "版本对比" },
        ].map((m) => (
          <button
            key={m.key}
            onClick={() => setChangeImpactMode(m.key)}
            className={`px-2 py-0.5 text-xs rounded-full border transition-colors ${
              changeImpactMode === m.key
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border hover:bg-muted"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {/* manual 模式 */}
      {changeImpactMode === "manual" && (
        <div className="space-y-2">
          <Input
            placeholder="文件路径 (如: app/api/users.py)"
            value={ciFilePath}
            onChange={(e) => setCiFilePath(e.target.value)}
            className="text-xs"
          />
          <div className="flex gap-2">
            <Input
              placeholder="起始行"
              value={ciStartLine}
              onChange={(e) => setCiStartLine(e.target.value)}
              className="text-xs flex-1"
              type="number"
            />
            <Input
              placeholder="结束行"
              value={ciEndLine}
              onChange={(e) => setCiEndLine(e.target.value)}
              className="text-xs flex-1"
              type="number"
            />
          </div>
        </div>
      )}

      {/* git_diff 模式 */}
      {changeImpactMode === "git_diff" && (
        <div className="space-y-2">
          <Input
            placeholder="基准 commit (如: HEAD~1)"
            value={ciBaseCommit}
            onChange={(e) => setCiBaseCommit(e.target.value)}
            className="text-xs"
          />
          <Input
            placeholder="目标 commit (默认 HEAD)"
            value={ciTargetCommit}
            onChange={(e) => setCiTargetCommit(e.target.value)}
            className="text-xs"
          />
        </div>
      )}

      {/* compare_commits 模式 */}
      {changeImpactMode === "compare_commits" && (
        <div className="space-y-2">
          {commitsError && (
            <p className="text-xs text-red-500">{commitsError}</p>
          )}
          {commits.length < 2 ? (
            <p className="text-xs text-muted-foreground">
              {commits.length === 0
                ? "暂无已分析的 commit 版本，请先运行代码分析"
                : "至少需要 2 个版本才能对比"}
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-muted-foreground block mb-0.5">
                    基准版本
                  </label>
                  <select
                    value={ciBaseCommitSelect}
                    onChange={(e) => setCiBaseCommitSelect(e.target.value)}
                    className="w-full text-xs border rounded px-2 py-1"
                  >
                    {commits.map((c) => (
                      <option key={c.commit_hash} value={c.commit_hash}>
                        {c.short_hash} {c.commit_message?.slice(0, 30) || "无提交信息"}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground block mb-0.5">
                    目标版本
                  </label>
                  <select
                    value={ciTargetCommitSelect}
                    onChange={(e) => setCiTargetCommitSelect(e.target.value)}
                    className="w-full text-xs border rounded px-2 py-1"
                  >
                    {commits.map((c) => (
                      <option key={c.commit_hash} value={c.commit_hash}>
                        {c.short_hash} {c.commit_message?.slice(0, 30) || "无提交信息"}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground">
                共 {commits.length} 个已分析版本（最多保留 10 个）
              </p>
            </>
          )}
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">遍历深度:</span>
        <select
          value={ciMaxDepth}
          onChange={(e) => setCiMaxDepth(e.target.value)}
          className="text-xs border rounded px-1 py-0.5"
        >
          {["1", "2", "3", "5"].map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      </div>

      <Button
        size="sm"
        className="w-full"
        onClick={handleAnalyze}
        disabled={
          ciLoading ||
          (changeImpactMode === "manual" ? !ciFilePath :
           changeImpactMode === "git_diff" ? !ciBaseCommit :
           commits.length < 2)
        }
      >
        {ciLoading ? (
          <><Loader2 className="mr-1 h-3 w-3 animate-spin" />分析中</>
        ) : (
          <><AlertTriangle className="mr-1 h-3 w-3" />分析变更影响</>
        )}
      </Button>

      {error && <p className="text-xs text-red-500">{error}</p>}

      {/* 结果展示 */}
      {ciResult && (
        <div className="space-y-2 pt-2 border-t">
          {/* 版本对比信息 */}
          {ciResult.version_diff && (
            <div className="bg-slate-50 rounded p-2 space-y-1.5">
              <p className="text-xs font-medium">版本差异</p>
              <div className="flex gap-3 text-[10px]">
                <span className="text-green-600">新增: {ciResult.version_diff.added_count}</span>
                <span className="text-red-600">删除: {ciResult.version_diff.removed_count}</span>
                <span className="text-amber-600">修改: {ciResult.version_diff.modified_count}</span>
              </div>
              {ciResult.version_diff.added.length > 0 && (
                <details className="text-[10px]">
                  <summary className="cursor-pointer text-green-600">新增符号 ({ciResult.version_diff.added_count})</summary>
                  <div className="flex flex-wrap gap-1 mt-1 pl-2">
                    {ciResult.version_diff.added.map((s) => (
                      <Badge key={s.id} variant="secondary" className="text-[9px] bg-green-50 text-green-700">{s.name}</Badge>
                    ))}
                  </div>
                </details>
              )}
              {ciResult.version_diff.removed.length > 0 && (
                <details className="text-[10px]">
                  <summary className="cursor-pointer text-red-600">删除符号 ({ciResult.version_diff.removed_count})</summary>
                  <div className="flex flex-wrap gap-1 mt-1 pl-2">
                    {ciResult.version_diff.removed.map((s) => (
                      <Badge key={s.id} variant="secondary" className="text-[9px] bg-red-50 text-red-700 line-through">{s.name}</Badge>
                    ))}
                  </div>
                </details>
              )}
              {ciResult.version_diff.modified.length > 0 && (
                <details className="text-[10px]">
                  <summary className="cursor-pointer text-amber-600">修改符号 ({ciResult.version_diff.modified_count})</summary>
                  <div className="flex flex-wrap gap-1 mt-1 pl-2">
                    {ciResult.version_diff.modified.map((s) => (
                      <Badge key={s.id} variant="secondary" className="text-[9px] bg-amber-50 text-amber-700">{s.name}</Badge>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}

          {/* commit hash 显示 */}
          {(ciResult.base_commit || ciResult.target_commit) && (
            <div className="text-[10px] text-muted-foreground font-mono">
              {ciResult.base_commit && <span>{ciResult.base_commit.slice(0, 8)}</span>}
              {ciResult.base_commit && ciResult.target_commit && <span className="mx-1">→</span>}
              {ciResult.target_commit && <span>{ciResult.target_commit.slice(0, 8)}</span>}
            </div>
          )}

          {/* 风险评级 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">风险:</span>
            <Badge className={
              ciResult.risk === "high" ? "bg-red-100 text-red-700" :
              ciResult.risk === "medium" ? "bg-yellow-100 text-yellow-700" :
              "bg-green-100 text-green-700"
            }>
              {ciResult.risk === "high" ? "高风险" : ciResult.risk === "medium" ? "中风险" : "低风险"}
            </Badge>
          </div>

          {/* 摘要 */}
          <p className="text-xs text-muted-foreground">{ciResult.summary}</p>

          {/* 改动符号 */}
          {ciResult.changed_symbols.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1">改动符号 ({ciResult.changed_symbols.length})</p>
              <div className="flex flex-wrap gap-1">
                {ciResult.changed_symbols.map((s) => (
                  <Badge key={s.id} variant="secondary" className="text-[10px]">{s.name}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* 受影响路由 */}
          {ciResult.impacted_routes.length > 0 && (
            <div>
              <p className="text-xs font-medium mb-1 text-red-500">受影响路由 ({ciResult.impacted_routes.length})</p>
              <div className="flex flex-wrap gap-1">
                {ciResult.impacted_routes.map((r) => (
                  <Badge key={r.id} variant="outline" className="text-[10px] text-red-600 border-red-300">{r.name}</Badge>
                ))}
              </div>
            </div>
          )}

          {/* 上游/下游 */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <p className="text-xs font-medium mb-1 text-blue-500">
                上游 ({ciResult.upstream.length})
                {ciResult.new_upstream && ciResult.new_upstream.length > 0 && (
                  <span className="text-green-600 ml-1">+{ciResult.new_upstream.length} 新增</span>
                )}
              </p>
              <div className="max-h-24 overflow-y-auto space-y-0.5">
                {ciResult.upstream.slice(0, 8).map((u) => (
                  <p key={u.id} className="text-[10px] text-muted-foreground truncate">
                    {ciResult.new_upstream?.some(nu => nu.id === u.id) ? "● " : "○ "}{u.name}
                  </p>
                ))}
                {ciResult.upstream.length > 8 && (
                  <p className="text-[10px] text-muted-foreground">...还有 {ciResult.upstream.length - 8} 个</p>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs font-medium mb-1 text-green-500">
                下游 ({ciResult.downstream.length})
                {ciResult.new_downstream && ciResult.new_downstream.length > 0 && (
                  <span className="text-green-600 ml-1">+{ciResult.new_downstream.length} 新增</span>
                )}
              </p>
              <div className="max-h-24 overflow-y-auto space-y-0.5">
                {ciResult.downstream.slice(0, 8).map((d) => (
                  <p key={d.id} className="text-[10px] text-muted-foreground truncate">
                    {ciResult.new_downstream?.some(nd => nd.id === d.id) ? "● " : "○ "}{d.name}
                  </p>
                ))}
                {ciResult.downstream.length > 8 && (
                  <p className="text-[10px] text-muted-foreground">...还有 {ciResult.downstream.length - 8} 个</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
