"""
陈旧度检测

检测知识图谱是否相对于代码仓库已过期。
对标 GitNexus gitnexus/src/core/git-staleness.ts
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class StalenessReport:
    """陈旧度检测报告"""
    is_stale: bool
    indexed_commit: str
    current_head: str
    commits_behind: int
    hint: str


class StalenessDetector:
    """检测知识图谱是否过期

    原理：比较已索引的 commit hash 与当前仓库 HEAD。
    """

    def check(self, repo_path: str, indexed_commit: str) -> StalenessReport:
        """检查仓库是否过期

        Args:
            repo_path: 代码仓库路径
            indexed_commit: 已索引的 commit hash

        Returns:
            陈旧度检测报告
        """
        current_head = self._get_head(repo_path)
        if not current_head:
            return StalenessReport(
                is_stale=False,
                indexed_commit=indexed_commit,
                current_head="unknown",
                commits_behind=0,
                hint="无法读取仓库 HEAD，跳过陈旧度检测",
            )

        if current_head == indexed_commit:
            return StalenessReport(
                is_stale=False,
                indexed_commit=indexed_commit,
                current_head=current_head,
                commits_behind=0,
                hint="知识图谱是最新的",
            )

        behind = self._count_commits_behind(repo_path, indexed_commit)

        if behind == 0:
            # HEAD 和 indexed_commit 不同，但 behind 为 0
            # 说明它们在不同的分支上
            hint = (
                f"索引的 commit ({indexed_commit[:7]}) 与当前 HEAD "
                f"({current_head[:7]}) 不在同一分支"
            )
        elif behind <= 2:
            hint = f"知识图谱轻微过期：落后 {behind} 个 commit"
        elif behind <= 10:
            hint = f"知识图谱中度过期：落后 {behind} 个 commit，建议重新分析"
        else:
            hint = f"知识图谱严重过期：落后 {behind} 个 commit，必须重新分析"

        return StalenessReport(
            is_stale=True,
            indexed_commit=indexed_commit,
            current_head=current_head,
            commits_behind=behind,
            hint=hint,
        )

    def _get_head(self, repo_path: str) -> Optional[str]:
        """获取仓库当前 HEAD"""
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _count_commits_behind(self, repo_path: str, commit: str) -> int:
        """计算 indexed_commit 落后 HEAD 多少 commit"""
        result = subprocess.run(
            ["git", "-C", repo_path, "rev-list", f"{commit}..HEAD", "--count"],
            capture_output=True, text=True, timeout=10,
        )
        try:
            return int(result.stdout.strip()) if result.returncode == 0 else 0
        except ValueError:
            return 0
