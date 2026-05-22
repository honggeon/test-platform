"""
增量分析器（骨架 — P2 完整实现）

需求背景：
- 每次全量分析在大项目上耗时 5-30 分钟
- 增量分析只重新解析变更文件，目标缩短到 <1 分钟

策略：
1. git diff HEAD~1 — 获取变更文件列表
2. 从数据库中删除变更文件相关的旧节点和关系
3. 只重新扫描变更文件
4. 更新受影响的符号和关系
5. 检查受影响的执行流是否需要重算

依赖：
- P0 完成后（解析准确度高）增量分析才有意义
- 需要 pipeline 支持部分扫描（当前不支持，需扩展）

当前状态：骨架设计，核心逻辑待实现
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional

from app.kg.graph import KnowledgeGraph
from app.kg.persistence import GraphPersistence


@dataclass
class IncrementalPlan:
    """增量分析计划"""
    changed_files: list[str]
    deleted_files: list[str]
    added_files: list[str]
    affected_nodes_estimate: int
    needs_full_rebuild: bool


class IncrementalAnalyzer:
    """增量分析器

    使用方式：
        analyzer = IncrementalAnalyzer()
        plan = analyzer.plan(repo_path, old_commit, new_commit)
        if plan.needs_full_rebuild:
            # 变更太大，回退到全量分析
            run_full_pipeline(repo_path)
        else:
            analyzer.execute(plan, repo_path, new_commit)
    """

    def plan(
        self, repo_path: str,
        old_commit: str, new_commit: str,
    ) -> IncrementalPlan:
        """制定增量分析计划"""
        changed = self._git_diff_files(repo_path, old_commit, new_commit)

        # 启发式：如果变更文件数超过阈值，建议全量重建
        needs_full_rebuild = len(changed) > 50

        # 分类变更
        added = [f for f in changed if self._is_new_file(repo_path, f, old_commit)]
        deleted = [f for f in changed if self._is_deleted_file(repo_path, f, new_commit)]
        modified = [f for f in changed if f not in added and f not in deleted]

        # 估算受影响的节点数（粗略）
        affected_estimate = len(modified) * 5 + len(added) * 3 + len(deleted) * 3

        return IncrementalPlan(
            changed_files=modified,
            deleted_files=deleted,
            added_files=added,
            affected_nodes_estimate=affected_estimate,
            needs_full_rebuild=needs_full_rebuild,
        )

    def execute(
        self, plan: IncrementalPlan,
        repo_path: str, new_commit: str,
        graph: KnowledgeGraph,
    ) -> dict:
        """执行增量分析

        TODO: 当前为骨架，需扩展以下能力：
        1. 从数据库删除变更文件相关的旧节点和关系
        2. 调用 symbol_extractor / call_processor 只处理变更文件
        3. 合并新节点到现有图谱（避免重复）
        4. 重新计算受影响的 communities 和 processes
        """
        raise NotImplementedError(
            "增量分析尚未实现。当前请使用全量分析: "
            "python -m app.kg.cli analyze <repo_path>"
        )

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    def _git_diff_files(
        self, repo_path: str, old_commit: str, new_commit: str,
    ) -> list[str]:
        """获取两个 commit 之间的变更文件列表"""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "diff", "--name-only", f"{old_commit}..{new_commit}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        except Exception:
            pass
        return []

    def _is_new_file(
        self, repo_path: str, file_path: str, old_commit: str,
    ) -> bool:
        """检查文件是否是在 old_commit 之后新增的"""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "cat-file", "-e", f"{old_commit}:{file_path}"],
                capture_output=True, timeout=10,
            )
            return result.returncode != 0
        except Exception:
            return False

    def _is_deleted_file(
        self, repo_path: str, file_path: str, new_commit: str,
    ) -> bool:
        """检查文件是否在 new_commit 中已删除"""
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "cat-file", "-e", f"{new_commit}:{file_path}"],
                capture_output=True, timeout=10,
            )
            return result.returncode != 0
        except Exception:
            return False
