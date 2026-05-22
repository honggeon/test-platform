"""
代码分析服务

提供搜索、符号上下文、影响分析、变更影响分析等业务逻辑。
支持多版本图谱查询（按 commit_hash）。
"""
from __future__ import annotations

import asyncio
import re
import subprocess
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.code_repo_service import CodeRepoService
from app.kg.search import CodeSearcher
from app.kg.persistence import KGNode, KGRelationship, GraphPersistence
from app.kg.staleness import StalenessDetector


class AnalyzeService:
    """代码分析服务

    包装 CodeSearcher，提供面向 API 的业务方法。
    支持按 commit_hash 查询指定版本的图谱。
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_repo_path(self, project_identifier: str) -> str:
        """获取项目的代码仓库路径"""
        repo_service = CodeRepoService(self._session)
        project = await repo_service.get_project(project_identifier)
        if not project.code_repo_path:
            raise ValueError("项目未配置代码仓库路径")
        return project.code_repo_path

    async def search(
        self, project_identifier: str, query: str,
        node_type: Optional[str] = None, limit: int = 20,
        mode: str = "hybrid",
        commit_hash: Optional[str] = None,
    ):
        """搜索代码"""
        repo_path = await self._get_repo_path(project_identifier)
        searcher = CodeSearcher(self._session)
        return await searcher.search(repo_path, query, node_type, limit, mode, commit_hash)

    async def get_symbol_context(
        self, project_identifier: str, symbol: str,
        commit_hash: Optional[str] = None,
    ) -> Optional[dict]:
        """获取符号上下文"""
        repo_path = await self._get_repo_path(project_identifier)
        searcher = CodeSearcher(self._session)

        results = await searcher.search(repo_path, symbol, limit=5, commit_hash=commit_hash)
        exact = [r for r in results if r.name == symbol]
        target = exact[0] if exact else (results[0] if results else None)

        if not target:
            return None

        ctx = await searcher.get_node_context(repo_path, target.node_id, commit_hash)
        if ctx:
            ctx["query_symbol"] = symbol
        return ctx

    async def impact_analysis(
        self, project_identifier: str, symbol: str,
        direction: str = "upstream",
        commit_hash: Optional[str] = None,
    ) -> dict:
        """影响分析"""
        repo_path = await self._get_repo_path(project_identifier)
        searcher = CodeSearcher(self._session)

        results = await searcher.search(repo_path, symbol, limit=5, commit_hash=commit_hash)
        exact = [r for r in results if r.name == symbol]
        target = exact[0] if exact else (results[0] if results else None)

        if not target:
            return {"error": f"未找到符号: {symbol}", "risk": "unknown"}

        ctx = await searcher.get_node_context(repo_path, target.node_id, commit_hash)
        if not ctx:
            return {"error": f"未找到符号详情: {symbol}", "risk": "unknown"}

        rels = ctx["relationships"]
        node = ctx["node"]

        callers = [
            r for r in rels
            if r["type"] == "CALLS" and r["target"] == node["id"]
        ]
        callees = [
            r for r in rels
            if r["type"] == "CALLS" and r["source"] == node["id"]
        ]
        overrides = [
            r for r in rels
            if r["type"] == "METHOD_OVERRIDES" and r["target"] == node["id"]
        ]

        total_callers = len(callers) + len(overrides)
        if total_callers > 20:
            risk = "high"
        elif total_callers > 5:
            risk = "medium"
        elif total_callers > 0:
            risk = "low"
        else:
            risk = "none"

        result = {
            "symbol": node["name"],
            "type": node["type"],
            "file_path": node.get("file_path"),
            "start_line": node.get("start_line"),
            "risk": risk,
        }

        if direction in ("upstream", "both"):
            result["upstream"] = sorted(set(
                r["source"].split("::")[-1] if "::" in r["source"] else r["source"]
                for r in callers
            ))

        if direction in ("downstream", "both"):
            result["downstream"] = sorted(set(
                r["target"].split("::")[-1] if "::" in r["target"] else r["target"]
                for r in callees
            ))

        return result

    # ── 变更影响分析 ──────────────────────────────────────────────────────

    async def change_impact_analysis(
        self, project_identifier: str,
        mode: str = "manual",
        file_path: str = "",
        start_line: int = 0, end_line: int = 0,
        base_commit: str = "", target_commit: str = "HEAD",
        max_depth: int = 3,
    ) -> dict:
        """变更影响分析：分析代码改动的影响范围

        支持三种模式：
        - manual: 手动输入文件路径+行号范围
        - git_diff: 基于 git diff 自动定位改动范围
        - compare_commits: 对比两个已分析 commit 版本的图谱差异
        """
        repo_path = await self._get_repo_path(project_identifier)

        # 解析 target_commit（如果是指令如 HEAD，转为真实 hash）
        resolved_target = await self._resolve_git_commit(repo_path, target_commit)

        if mode == "compare_commits":
            if not base_commit:
                return {"error": "compare_commits 模式需要 base_commit"}
            resolved_base = await self._resolve_git_commit(repo_path, base_commit)
            return await self._compare_commits_analysis(
                repo_path, resolved_base, resolved_target, max_depth
            )

        # ── Step 1: 收集改动范围 ──
        changed_ranges: list[dict] = []

        if mode == "git_diff" and base_commit:
            changed_ranges = await self._git_diff_ranges(repo_path, base_commit, target_commit)
        elif mode == "manual" and file_path:
            changed_ranges = [{"file": file_path, "ranges": [(start_line, end_line)]}]
        else:
            return {"error": "参数不足：git_diff 模式需要 base_commit，manual 模式需要 file_path"}

        if not changed_ranges:
            return {"error": "未检测到代码改动"}

        # ── Step 2: 查询改动范围内的符号（在 target commit 的图谱中）──
        changed_symbols = []
        for item in changed_ranges:
            for s, e in item["ranges"]:
                symbols = await self._find_symbols_in_range(
                    repo_path, item["file"], s, e, resolved_target
                )
                changed_symbols.extend(symbols)

        if not changed_symbols:
            return {
                "changed_ranges": changed_ranges,
                "changed_symbols": [],
                "message": "改动范围内未找到代码符号（可能是注释/空白改动）",
            }

        # ── Step 3: 对每个符号做 BFS 影响分析（基于 target commit）──
        upstream_set = set()
        downstream_set = set()
        impacted_routes = set()

        for sym in changed_symbols:
            impacts = await self._bfs_impact(repo_path, sym["node_id"], max_depth, resolved_target)
            for r in impacts:
                if r["direction"] == "upstream":
                    upstream_set.add((r["node_id"], r["name"], r["type"]))
                else:
                    downstream_set.add((r["node_id"], r["name"], r["type"]))
                if r["type"] == "route":
                    impacted_routes.add((r["node_id"], r["name"]))

        # ── Step 4: 风险评级 ──
        total_impact = len(upstream_set) + len(downstream_set)
        route_count = len(impacted_routes)
        if route_count > 5 or total_impact > 50:
            risk = "high"
        elif route_count > 0 or total_impact > 10:
            risk = "medium"
        else:
            risk = "low"

        return {
            "mode": mode,
            "target_commit": resolved_target,
            "changed_ranges": changed_ranges,
            "changed_symbols": [
                {"id": s["node_id"], "name": s["name"], "type": s["type"], "file_path": s["file_path"]}
                for s in changed_symbols
            ],
            "upstream": [{"id": uid, "name": name, "type": typ} for uid, name, typ in sorted(upstream_set)],
            "downstream": [{"id": uid, "name": name, "type": typ} for uid, name, typ in sorted(downstream_set)],
            "impacted_routes": [{"id": uid, "name": name} for uid, name in sorted(impacted_routes)],
            "risk": risk,
            "summary": f"改动涉及 {len(changed_symbols)} 个符号，影响上游 {len(upstream_set)} 处、下游 {len(downstream_set)} 处，触及 {route_count} 个路由，风险等级：{risk}",
        }

    async def _compare_commits_analysis(
        self, repo_path: str, base_commit: str, target_commit: str, max_depth: int
    ) -> dict:
        """对比两个已分析 commit 版本的图谱差异，并做影响分析"""
        persister = GraphPersistence(self._session)

        # 1. 检查两个 commit 是否都已分析
        commits = await persister.list_commits(repo_path)
        analyzed_hashes = {c.commit_hash for c in commits}

        missing = []
        if base_commit not in analyzed_hashes:
            missing.append(base_commit)
        if target_commit not in analyzed_hashes:
            missing.append(target_commit)
        if missing:
            return {
                "error": f"以下 commit 尚未分析，请先运行代码分析: {[h[:8] for h in missing]}",
                "missing_commits": missing,
            }

        # 2. 加载两个版本的节点
        base_nodes = await persister.get_all_nodes_for_commit(repo_path, base_commit)
        target_nodes = await persister.get_all_nodes_for_commit(repo_path, target_commit)

        base_node_map = {n.id: n for n in base_nodes}
        target_node_map = {n.id: n for n in target_nodes}

        # 3. 计算差异
        added = [n for nid, n in target_node_map.items() if nid not in base_node_map]
        removed = [n for nid, n in base_node_map.items() if nid not in target_node_map]
        modified = []
        for nid, tn in target_node_map.items():
            if nid in base_node_map:
                bn = base_node_map[nid]
                if (tn.name != bn.name or tn.type != bn.type or
                    tn.file_path != bn.file_path or
                    tn.start_line != bn.start_line or tn.end_line != bn.end_line):
                    modified.append(tn)

        changed_symbols = added + modified

        # 4. 对 target 版本的改动节点做 BFS 影响分析
        upstream_set = set()
        downstream_set = set()
        impacted_routes = set()

        for sym in changed_symbols:
            impacts = await self._bfs_impact(repo_path, sym.id, max_depth, target_commit)
            for r in impacts:
                if r["direction"] == "upstream":
                    upstream_set.add((r["node_id"], r["name"], r["type"]))
                else:
                    downstream_set.add((r["node_id"], r["name"], r["type"]))
                if r["type"] == "route":
                    impacted_routes.add((r["node_id"], r["name"]))

        # 5. 尝试在 base 版本上做同样的 BFS，标记"新增影响"
        #    只对 modified 的节点做（added 的节点在 base 中不存在，所有影响都是新增的）
        base_upstream_set = set()
        base_downstream_set = set()
        if modified:
            for sym in modified:
                if sym.id in base_node_map:
                    impacts = await self._bfs_impact(repo_path, sym.id, max_depth, base_commit)
                    for r in impacts:
                        if r["direction"] == "upstream":
                            base_upstream_set.add(r["node_id"])
                        else:
                            base_downstream_set.add(r["node_id"])

        new_upstream = [u for u in upstream_set if u[0] not in base_upstream_set]
        new_downstream = [d for d in downstream_set if d[0] not in base_downstream_set]

        # 6. 风险评级（考虑版本差异）
        total_impact = len(upstream_set) + len(downstream_set)
        route_count = len(impacted_routes)
        if route_count > 5 or total_impact > 50 or len(removed) > 0:
            risk = "high"
        elif route_count > 0 or total_impact > 10 or len(added) > 5:
            risk = "medium"
        else:
            risk = "low"

        return {
            "mode": "compare_commits",
            "base_commit": base_commit,
            "target_commit": target_commit,
            "version_diff": {
                "added_count": len(added),
                "removed_count": len(removed),
                "modified_count": len(modified),
                "added": [
                    {"id": n.id, "name": n.name, "type": n.type, "file_path": n.file_path}
                    for n in added[:20]
                ],
                "removed": [
                    {"id": n.id, "name": n.name, "type": n.type, "file_path": n.file_path}
                    for n in removed[:20]
                ],
                "modified": [
                    {"id": n.id, "name": n.name, "type": n.type, "file_path": n.file_path}
                    for n in modified[:20]
                ],
            },
            "changed_symbols": [
                {"id": s.id, "name": s.name, "type": s.type, "file_path": s.file_path}
                for s in changed_symbols
            ],
            "upstream": [{"id": uid, "name": name, "type": typ} for uid, name, typ in sorted(upstream_set)],
            "downstream": [{"id": uid, "name": name, "type": typ} for uid, name, typ in sorted(downstream_set)],
            "new_upstream": [{"id": uid, "name": name, "type": typ} for uid, name, typ in sorted(new_upstream)],
            "new_downstream": [{"id": uid, "name": name, "type": typ} for uid, name, typ in sorted(new_downstream)],
            "impacted_routes": [{"id": uid, "name": name} for uid, name in sorted(impacted_routes)],
            "risk": risk,
            "summary": (
                f"版本对比: {base_commit[:8]} → {target_commit[:8]}，"
                f"新增 {len(added)} 符号、删除 {len(removed)} 符号、修改 {len(modified)} 符号，"
                f"影响上游 {len(upstream_set)} 处（新增 {len(new_upstream)} 处）、"
                f"下游 {len(downstream_set)} 处（新增 {len(new_downstream)} 处），"
                f"触及 {route_count} 个路由，风险等级：{risk}"
            ),
        }

    # ── 辅助方法 ──────────────────────────────────────────────────────────

    async def _resolve_git_commit(self, repo_path: str, ref: str) -> str:
        """将 git 引用（如 HEAD, HEAD~1）解析为真实 commit hash"""
        if not ref:
            return ""
        # 如果已经是 40 位 hash，直接返回
        if len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower()):
            return ref.lower()
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "-C", repo_path, "rev-parse", ref],
                    capture_output=True, text=True, timeout=10,
                ),
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ref  # 解析失败，返回原值

    async def _git_diff_ranges(self, repo_path: str, base: str, target: str) -> list[dict]:
        """用 git diff 获取改动的文件和行号范围"""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["git", "diff", "-U0", base, target],
                    cwd=repo_path, capture_output=True, text=True, timeout=30,
                ),
            )
        except Exception:
            return []

        if result.returncode != 0:
            return []

        return self._parse_diff_output(result.stdout)

    @staticmethod
    def _parse_diff_output(diff_text: str) -> list[dict]:
        """解析 git diff -U0 的输出，提取文件和行号范围"""
        results = []
        current_file = None
        hunk_re = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")

        for line in diff_text.split("\n"):
            if line.startswith("diff --git "):
                parts = line.split(" ")
                if len(parts) >= 4:
                    current_file = parts[3][2:] if parts[3].startswith("b/") else parts[3]
            elif line.startswith("--- ") or line.startswith("+++ "):
                continue
            elif line.startswith("@@ ") and current_file:
                m = hunk_re.match(line)
                if m:
                    start = int(m.group(1))
                    count = int(m.group(2)) if m.group(2) else 1
                    end = start + count - 1
                    existing = next((r for r in results if r["file"] == current_file), None)
                    if existing:
                        existing["ranges"].append((start, end))
                    else:
                        results.append({"file": current_file, "ranges": [(start, end)]})

        return results

    async def _find_symbols_in_range(
        self, repo_path: str, file_path: str, start_line: int, end_line: int,
        commit_hash: Optional[str] = None,
    ) -> list[dict]:
        """查询指定文件+行号范围内的所有代码符号"""
        stmt = select(KGNode).where(
            KGNode.repo_path == repo_path,
            KGNode.file_path == file_path,
            KGNode.start_line != None,
            KGNode.end_line != None,
        )
        if commit_hash:
            stmt = stmt.where(KGNode.commit_hash == commit_hash)

        stmt = stmt.where(
            or_(
                (KGNode.start_line <= end_line) & (KGNode.end_line >= start_line),
            )
        )

        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "node_id": row.node_id,
                "name": row.name,
                "type": row.type,
                "file_path": row.file_path,
                "start_line": row.start_line,
                "end_line": row.end_line,
            }
            for row in rows
        ]

    async def _bfs_impact(
        self, repo_path: str, node_id: str, max_depth: int,
        commit_hash: Optional[str] = None,
    ) -> list[dict]:
        """BFS 图遍历：从指定节点出发，找上游调用者和下游被调用者"""
        impacts = []
        visited = set()
        queue = [(node_id, 0, "downstream")]

        while queue:
            current_id, depth, direction = queue.pop(0)
            if depth >= max_depth or current_id in visited:
                continue
            visited.add(current_id)

            rel_stmt = select(KGRelationship).where(
                KGRelationship.repo_path == repo_path,
            )
            if commit_hash:
                rel_stmt = rel_stmt.where(KGRelationship.commit_hash == commit_hash)

            rel_stmt = rel_stmt.where(
                or_(
                    KGRelationship.type.in_(["CALLS", "EXTENDS", "IMPORTS", "METHOD_OVERRIDES"]),
                ),
            ).where(
                or_(KGRelationship.source_node_id == current_id, KGRelationship.target_node_id == current_id)
            )

            rel_result = await self._session.execute(rel_stmt)
            rels = rel_result.scalars().all()

            for rel in rels:
                if rel.type == "CALLS":
                    if rel.source_node_id == current_id and rel.target_node_id not in visited:
                        impacts.append({"node_id": rel.target_node_id, "direction": "downstream", "rel_type": "CALLS"})
                        queue.append((rel.target_node_id, depth + 1, "downstream"))
                    if rel.target_node_id == current_id and rel.source_node_id not in visited:
                        impacts.append({"node_id": rel.source_node_id, "direction": "upstream", "rel_type": "CALLS"})
                        queue.append((rel.source_node_id, depth + 1, "upstream"))
                elif rel.type == "EXTENDS":
                    if rel.source_node_id == current_id and rel.target_node_id not in visited:
                        impacts.append({"node_id": rel.target_node_id, "direction": "downstream", "rel_type": "EXTENDS"})
                elif rel.type == "METHOD_OVERRIDES":
                    if rel.source_node_id == current_id and rel.target_node_id not in visited:
                        impacts.append({"node_id": rel.target_node_id, "direction": "downstream", "rel_type": "OVERRIDES"})
                    if rel.target_node_id == current_id and rel.source_node_id not in visited:
                        impacts.append({"node_id": rel.source_node_id, "direction": "upstream", "rel_type": "OVERRIDES"})

        # 补充节点信息
        node_ids = {i["node_id"] for i in impacts}
        if node_ids:
            node_stmt = select(KGNode.node_id, KGNode.name, KGNode.type).where(
                KGNode.repo_path == repo_path,
                KGNode.node_id.in_(list(node_ids)),
            )
            if commit_hash:
                node_stmt = node_stmt.where(KGNode.commit_hash == commit_hash)

            node_result = await self._session.execute(node_stmt)
            node_map = {row.node_id: {"name": row.name, "type": row.type} for row in node_result.all()}
            for i in impacts:
                info = node_map.get(i["node_id"], {})
                i["name"] = info.get("name", i["node_id"])
                i["type"] = info.get("type", "unknown")

        return impacts

    # ── 图谱数据 ──────────────────────────────────────────────────────────

    async def get_graph_data(
        self, project_identifier: str, node_limit: int = 200, rel_limit: int = 500,
        commit_hash: Optional[str] = None,
    ) -> dict:
        """获取知识图谱可视化数据（节点+关系子集）"""
        repo_path = await self._get_repo_path(project_identifier)
        persister = GraphPersistence(self._session)
        nodes = await persister.get_nodes_by_repo(repo_path, commit_hash, node_limit)
        rels = await persister.get_relationships_by_repo(repo_path, commit_hash, rel_limit)
        return {
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type,
                    "file_path": n.file_path,
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": r.id,
                    "source": r.source_id,
                    "target": r.target_id,
                    "type": r.type,
                }
                for r in rels
            ],
        }

    # ── Commit 列表 ───────────────────────────────────────────────────────

    async def _resolve_commit_for_repo(self, repo_path: str) -> Optional[str]:
        """获取仓库最新分析的 commit hash"""
        from app.kg.persistence import KGCommit
        result = await self._session.execute(
            select(KGCommit.commit_hash)
            .where(KGCommit.repo_path == repo_path)
            .order_by(KGCommit.analyzed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_commits(self, project_identifier: str, limit: int = 20) -> list[dict]:
        """列出该项目已分析的所有 commit 版本"""
        repo_path = await self._get_repo_path(project_identifier)
        persister = GraphPersistence(self._session)
        commits = await persister.list_commits(repo_path, limit)
        return [
            {
                "commit_hash": c.commit_hash,
                "short_hash": c.commit_hash[:8] if len(c.commit_hash) >= 8 else c.commit_hash,
                "commit_message": c.commit_message,
                "commit_author": c.commit_author,
                "commit_timestamp": c.commit_timestamp,
                "node_count": c.node_count,
                "rel_count": c.rel_count,
                "analyzed_at": c.analyzed_at,
            }
            for c in commits
        ]

    async def check_staleness(self, project_identifier: str) -> dict:
        """检查知识图谱是否相对于代码仓库已过期"""
        repo_path = await self._get_repo_path(project_identifier)
        persister = GraphPersistence(self._session)
        commits = await persister.list_commits(repo_path, limit=1)
        if not commits:
            return {
                "is_stale": False,
                "indexed_commit": None,
                "current_head": None,
                "commits_behind": 0,
                "hint": "尚未分析过此仓库",
                "status": "not_indexed",
            }

        indexed = commits[0]
        detector = StalenessDetector()
        report = detector.check(repo_path, indexed.commit_hash)

        return {
            "is_stale": report.is_stale,
            "indexed_commit": report.indexed_commit,
            "current_head": report.current_head,
            "commits_behind": report.commits_behind,
            "hint": report.hint,
            "status": "stale" if report.is_stale else "fresh",
        }

    async def get_process_trace(
        self, project_identifier: str, process_id: str,
        commit_hash: Optional[str] = None,
    ) -> dict:
        """获取执行流的调用链

        从 entry_point 开始，沿着 CALLS 边遍历，只包含属于该 process 的节点。
        """
        repo_path = await self._get_repo_path(project_identifier)
        ch = commit_hash or await self._resolve_commit_for_repo(repo_path)

        # 1. 获取 process 节点
        stmt = select(KGNode).where(
            KGNode.repo_path == repo_path,
            KGNode.node_id == process_id,
            KGNode.type == "process",
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        stmt = stmt.order_by(KGNode.start_line).limit(1)
        result = await self._session.execute(stmt)
        proc = result.scalar_one_or_none()
        if not proc:
            return {"error": f"未找到执行流: {process_id}"}

        entry_point_id = proc.properties.get("entry_point_id") if proc.properties else None

        # 2. 获取所有属于该 process 的节点（通过 STEP_IN_PROCESS 关系）
        step_stmt = select(KGRelationship.source_node_id).where(
            KGRelationship.repo_path == repo_path,
            KGRelationship.type == "STEP_IN_PROCESS",
            KGRelationship.target_node_id == process_id,
        )
        if commit_hash:
            step_stmt = step_stmt.where(KGRelationship.commit_hash == commit_hash)
        step_result = await self._session.execute(step_stmt)
        step_node_ids = {row[0] for row in step_result.all()}

        # 3. 获取这些节点的详细信息
        if step_node_ids:
            node_stmt = select(KGNode).where(
                KGNode.repo_path == repo_path,
                KGNode.node_id.in_(list(step_node_ids)),
            )
            if commit_hash:
                node_stmt = node_stmt.where(KGNode.commit_hash == commit_hash)
            node_result = await self._session.execute(node_stmt)
            node_map = {n.node_id: n for n in node_result.scalars().all()}
        else:
            node_map = {}

        # 4. 获取这些节点之间的 CALLS 关系
        if step_node_ids:
            rel_stmt = select(KGRelationship).where(
                KGRelationship.repo_path == repo_path,
                KGRelationship.type == "CALLS",
                KGRelationship.source_node_id.in_(list(step_node_ids)),
                KGRelationship.target_node_id.in_(list(step_node_ids)),
            )
            if commit_hash:
                rel_stmt = rel_stmt.where(KGRelationship.commit_hash == commit_hash)
            rel_result = await self._session.execute(rel_stmt)
            calls = rel_result.scalars().all()
        else:
            calls = []

        # 5. 构建调用链（从 entry_point 开始 BFS）
        call_map: dict[str, list[str]] = {}
        for rel in calls:
            call_map.setdefault(rel.source_node_id, []).append(rel.target_node_id)

        visited: set[str] = set()
        chain: list[dict] = []

        def dfs(node_id: str, depth: int):
            if node_id in visited or depth > 20:
                return
            visited.add(node_id)
            node = node_map.get(node_id)
            if node:
                chain.append({
                    "node_id": node_id,
                    "name": node.name,
                    "type": node.type,
                    "file_path": node.file_path,
                    "depth": depth,
                })
            for child_id in call_map.get(node_id, []):
                dfs(child_id, depth + 1)

        # 如果有 entry_point，从 entry_point 开始；否则从任意节点开始
        if entry_point_id and entry_point_id in step_node_ids:
            dfs(entry_point_id, 0)
        elif step_node_ids:
            for nid in sorted(step_node_ids):
                if nid not in visited:
                    dfs(nid, 0)

        return {
            "process_id": process_id,
            "name": proc.name,
            "entry_point": entry_point_id,
            "step_count": len(step_node_ids),
            "chain": chain,
        }
