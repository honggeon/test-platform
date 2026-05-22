"""
代码仓库服务

管理项目关联的代码目录，使用原生 Python 知识图谱引擎进行分析。
支持：
- Git 仓库地址（自动 clone + analyze）
- 本地目录路径（直接 analyze）
- 查询分析状态（含进度）
"""

import asyncio
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.code_repo import CodeRepoInfo, CodeRepoStatus
from app.kg.pipeline import run_pipeline_from_repo
from app.kg.persistence import GraphPersistence
from app.kg.types import PhaseProgress


# 代码仓库默认存储根目录（仅 Git URL 用）
DEFAULT_REPOS_ROOT = os.path.expanduser("~/analysis-repos")

# 分析进度缓存
_analysis_progress: dict[str, dict] = {}


def _is_local_path(path: str) -> bool:
    return path.startswith("/") or path.startswith("~") or path.startswith(".")


def _is_git_url(path: str) -> bool:
    return (
        path.startswith("http://")
        or path.startswith("https://")
        or path.startswith("git@")
        or path.startswith("ssh://")
    )


class CodeRepoService:
    """代码仓库服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_project(self, identifier: str) -> Project:
        result = await self.session.execute(
            select(Project).where(Project.identifier == identifier)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"项目不存在: {identifier}")
        return project

    async def get_status(self, identifier: str) -> CodeRepoStatus:
        """获取项目代码分析状态（含进度）"""
        project = await self.get_project(identifier)
        repo_path = project.code_repo_path

        status = CodeRepoStatus(
            repo_url=project.code_repo_url,
            repo_path=repo_path,
            repo_branch=project.code_repo_branch or "main",
        )

        if project.code_repo_url:
            status.configured = True

        if repo_path and os.path.isdir(repo_path):
            status.cloned = True

        # 检查分析结果是否存在于数据库中
        if repo_path:
            persister = GraphPersistence(self.session)
            count = await persister.get_node_count(repo_path)
            if count > 0:
                status.analyzed = True

        # 检查进度
        key = str(project.id)
        if key in _analysis_progress:
            info = _analysis_progress[key]
            status.analyzing = True
            status.progress = info.get("progress", 0)
            status.current_step = info.get("step", "")
            status.message = info.get("message", "")
        elif status.analyzed and not status.message:
            # 进度已过期但数据仍在数据库中，重建摘要
            persister = GraphPersistence(self.session)
            type_counts = await persister.get_type_counts(repo_path)
            rel_count = await persister.get_relationship_count(repo_path)
            files = type_counts.get("file", 0)
            folders = type_counts.get("folder", 0)
            nodes = sum(type_counts.values())
            status.message = (
                f"分析完成: {files} 文件, "
                f"{folders} 目录, "
                f"{nodes} 节点, "
                f"{rel_count} 关系"
            )

        return status

    async def configure_repo(
        self, identifier: str, repo_url: str, repo_branch: str = "main"
    ) -> CodeRepoInfo:
        project = await self.get_project(identifier)
        # 解析本地路径
        if _is_local_path(repo_url):
            local_path = os.path.expanduser(repo_url)
        else:
            name = repo_url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            local_path = os.path.join(DEFAULT_REPOS_ROOT, name)

        project.code_repo_url = repo_url
        project.code_repo_path = local_path
        project.code_repo_branch = repo_branch
        await self.session.commit()

        # 检查是否已有分析结果
        count = await GraphPersistence(self.session).get_node_count(local_path)

        return CodeRepoInfo(
            repo_url=repo_url,
            repo_path=local_path,
            repo_branch=repo_branch,
            analyzed=count > 0,
            is_local=_is_local_path(repo_url),
        )

    async def clone_and_analyze(self, identifier: str) -> CodeRepoStatus:
        """启动后台代码分析"""
        project = await self.get_project(identifier)

        if not project.code_repo_url:
            raise ValueError("请先配置代码仓库地址或本地路径")

        input_path = project.code_repo_url
        repo_path = project.code_repo_path

        key = str(project.id)
        if key in _analysis_progress:
            raise ValueError("该项目正在分析中，请稍后再试")

        # 验证路径
        if _is_local_path(input_path):
            repo_path = os.path.expanduser(input_path)
            if not os.path.isdir(repo_path):
                raise ValueError(f"本地路径不存在: {repo_path}")
        elif not _is_git_url(input_path):
            raise ValueError(
                "无法识别的路径格式，请输入 Git 仓库地址 (https://...) 或本地路径 (/home/...)"
            )

        project.code_repo_path = repo_path
        await self.session.commit()

        # 初始化进度
        _analysis_progress[key] = {"progress": 0, "step": "准备中", "message": "初始化分析..."}
        asyncio.create_task(self._run_analysis(key, input_path, repo_path))

        return await self.get_status(identifier)

    async def _run_analysis(
        self, key: str, input_path: str, repo_path: str
    ) -> None:
        """后台执行分析任务——使用原生 Python 知识图谱引擎"""
        # 后台任务使用独立的数据库会话（避免并发冲突）
        from app.config.database import async_session_factory
        async with async_session_factory() as bg_session:
            try:
                self._set_progress(key, 0, "准备分析", "初始化知识图谱引擎...")

                # ── 第 1 步：Git 克隆（如果是远程仓库）───────────────
                if _is_git_url(input_path):
                    os.makedirs(DEFAULT_REPOS_ROOT, exist_ok=True)
                    self._set_progress(key, 3, "克隆代码", "正在克隆远程仓库...")

                    if os.path.isdir(os.path.join(repo_path, ".git")):
                        await self._run_cmd(
                            ["git", "-C", repo_path, "fetch", "origin"],
                            desc="拉取最新代码",
                        )
                        branch = os.path.basename(repo_path.replace(".git", ""))
                        await self._run_cmd(
                            ["git", "-C", repo_path, "checkout", branch or "main"],
                            desc="切换分支",
                        )
                        await self._run_cmd(
                            ["git", "-C", repo_path, "merge", f"origin/{branch or 'main'}"],
                            desc="合并更新",
                        )
                    else:
                        await self._run_cmd(
                            ["git", "clone", input_path, repo_path],
                            cwd=DEFAULT_REPOS_ROOT,
                            desc="克隆代码仓库",
                        )

                # ── 第 2 步：获取 commit 信息 ──────────────────────
                commit_hash = "UNKNOWN"
                commit_message = None
                commit_author = None
                commit_timestamp = None
                if _is_git_url(input_path) or os.path.isdir(os.path.join(repo_path, ".git")):
                    try:
                        commit_hash = (await self._run_cmd(
                            ["git", "-C", repo_path, "rev-parse", "HEAD"],
                            desc="获取 commit hash",
                        )).strip()
                        commit_message = (await self._run_cmd(
                            ["git", "-C", repo_path, "log", "-1", "--pretty=format:%s"],
                            desc="获取 commit 信息",
                        )).strip() or None
                        commit_author = (await self._run_cmd(
                            ["git", "-C", repo_path, "log", "-1", "--pretty=format:%an"],
                            desc="获取 commit 作者",
                        )).strip() or None
                        commit_timestamp = (await self._run_cmd(
                            ["git", "-C", repo_path, "log", "-1", "--pretty=format:%cI"],
                            desc="获取 commit 时间",
                        )).strip() or None
                    except Exception:
                        pass  # 非 git 仓库或命令失败，使用 UNKNOWN

                # ── 第 3 步：运行 Python 分析管道 ────────────────────
                self._set_progress(key, 10, "分析代码", "运行代码分析管道...")

                def on_progress(p: PhaseProgress):
                    pct = 10 + int(p.percent * 0.85)
                    self._set_progress(key, min(pct, 95), p.phase, p.message)

                output = run_pipeline_from_repo(
                    repo_path=repo_path,
                    on_progress=on_progress,
                )

                stats = output.stats

                # ── 第 4 步：持久化到 PostgreSQL（多版本）───────────
                self._set_progress(key, 95, "持久化", f"写入知识图谱到数据库 (commit: {commit_hash[:8]})...")

                persister = GraphPersistence(bg_session)
                persist_stats = await persister.save_graph(
                    repo_path=repo_path,
                    commit_hash=commit_hash,
                    graph=output.graph,
                    commit_message=commit_message,
                    commit_author=commit_author,
                    commit_timestamp=commit_timestamp,
                )

                # 确保数据库索引存在
                from app.kg.persistence import ensure_indexes
                await ensure_indexes(bg_session)

                # 更新 project.last_commit（使用 bg_session）
                try:
                    from sqlalchemy import select
                    from app.models.project import Project
                    result = await bg_session.execute(
                        select(Project).where(Project.identifier == identifier)
                    )
                    proj = result.scalar_one_or_none()
                    if proj:
                        proj.last_commit = commit_hash
                        await bg_session.commit()
                except Exception:
                    pass

                # ── 完成 ────────────────────────────────────────────
                self._set_progress(
                    key, 100, "完成",
                    f"分析完成: {stats.get('files', 0)} 文件, "
                    f"{stats.get('folders', 0)} 目录, "
                    f"{output.graph.node_count} 节点, "
                    f"{output.graph.relationship_count} 关系 "
                    f"(commit: {commit_hash[:8]})",
                )

                await asyncio.sleep(1)

            except Exception as e:
                _analysis_progress[key] = {
                    "progress": -1,
                    "step": "失败",
                    "message": str(e),
                }
                print(f"[分析引擎] 分析失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                await asyncio.sleep(3)
                _analysis_progress.pop(key, None)

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _set_progress(key: str, progress: int, step: str, message: str = ""):
        _analysis_progress[key] = {
            "progress": progress,
            "step": step,
            "message": message,
        }

    @staticmethod
    async def _run_cmd(
        cmd: list[str], cwd: Optional[str] = None, desc: str = ""
    ) -> str:
        """执行 shell 命令"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"{desc} 失败 (exit={process.returncode}): {error_msg}"
            )
        return stdout.decode("utf-8", errors="replace")
