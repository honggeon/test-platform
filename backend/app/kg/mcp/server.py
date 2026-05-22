"""
知识图谱 MCP 服务

通过 MCP 协议暴露知识图谱查询工具。
AI Agent（Cursor、Claude Code、Windsurf 等）通过 MCP 客户端连接后可使用这些工具
进行代码搜索、上下文查询、影响分析、变更检测等。

借鉴 GitNexus MCP 设计：
- 工具返回结果附带"下一步提示"（next-step hints），引导 Agent 工作流
- 统一的错误处理和结果格式化
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from app.config.database import async_session_factory
from app.services.analyze_service import AnalyzeService
from app.services.code_repo_service import CodeRepoService
from app.kg.search import CodeSearcher
from app.kg.persistence import GraphPersistence
from app.kg.staleness import StalenessDetector

logger = logging.getLogger(__name__)


# ── 工具实现 ──────────────────────────────────────────────────────────────


class KGTools:
    """知识图谱 MCP 工具集

    提供代码搜索、符号上下文查询、影响分析、图谱数据、变更分析、版本管理、文件读取。
    每个方法返回结果附带 next-step hints，引导 Agent 继续探索。
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    async def _get_searcher(self):
        """创建搜索器实例"""
        from sqlalchemy.ext.asyncio import AsyncSession

        session: AsyncSession = async_session_factory()
        return CodeSearcher(session), session

    def _hint(self, text: str) -> str:
        """添加下一步提示"""
        return f"\n\n💡 建议: {text}"

    # ── Tool 1: 代码搜索 ─────────────────────────────────────────────────

    async def search_code(
        self, query: str,
        node_type: Optional[str] = None,
        limit: int = 20,
        commit_hash: Optional[str] = None,
    ) -> str:
        """搜索代码知识图谱"""
        searcher, session = await self._get_searcher()
        try:
            results = await searcher.search(
                self.repo_path, query,
                node_type=node_type, limit=min(limit, 50),
                commit_hash=commit_hash,
            )
            if not results:
                return f"未找到匹配 '{query}' 的结果" + self._hint(
                    f"尝试更通用的关键词，或使用 list_commits 查看已分析的版本"
                )

            lines = [f"找到 {len(results)} 个匹配 '{query}' 的结果：\n"]
            for r in results:
                loc = f"{r.file_path}" if r.file_path else ""
                if r.start_line:
                    loc += f"#{r.start_line}"
                lines.append(f"  [{r.type:8}] {r.name:40} {loc}")

            hint = self._hint(
                f"使用 symbol_context(symbol_name='{results[0].name}') 查看第一个结果的详细信息"
            )
            return "\n".join(lines) + hint
        finally:
            await session.close()

    # ── Tool 2: 符号上下文 ───────────────────────────────────────────────

    async def symbol_context(
        self, symbol_name: str,
        commit_hash: Optional[str] = None,
    ) -> str:
        """获取符号上下文"""
        searcher, session = await self._get_searcher()
        try:
            results = await searcher.search(
                self.repo_path, symbol_name, limit=5,
                commit_hash=commit_hash,
            )
            exact = [r for r in results if r.name == symbol_name]
            if not exact:
                if results:
                    similar = "\n".join(f"  [{r.type}] {r.name}" for r in results[:5])
                    return f"未找到精确匹配 '{symbol_name}'，相似结果：\n{similar}"
                return f"未找到符号: {symbol_name}"

            target = exact[0]
            ctx = await searcher.get_node_context(
                self.repo_path, target.node_id, commit_hash=commit_hash
            )
            if not ctx:
                return f"未找到符号 '{symbol_name}' 的详情"

            node = ctx["node"]
            rels = ctx["relationships"]
            source = ctx.get("source")

            lines = [
                f"符号: {node['name']}",
                f"类型: {node['type']}",
                f"位置: {node.get('file_path', '?')}#{node.get('start_line', '?')}",
            ]

            callers = [r for r in rels if r["type"] == "CALLS" and r["target"] == node["id"]]
            callees = [r for r in rels if r["type"] == "CALLS" and r["source"] == node["id"]]

            if callers:
                lines.append(f"\n调用者 ({len(callers)}):")
                for r in callers[:10]:
                    lines.append(f"  ← {r['source'].split('::')[-1]}")

            if callees:
                lines.append(f"\n被调用 ({len(callees)}):")
                for r in callees[:10]:
                    lines.append(f"  → {r['target'].split('::')[-1]}")

            if source:
                lines.append(f"\n源码 ({source['start_line']}-{source['end_line']}行):")
                for i, line in enumerate(source["content"].split("\n")[:15], start=source["start_line"]):
                    lines.append(f"  {i:4}| {line}")

            hint = self._hint(
                f"使用 impact_analysis(symbol_name='{symbol_name}') 分析修改此符号的影响范围"
            )
            return "\n".join(lines) + hint
        finally:
            await session.close()

    # ── Tool 3: 影响分析 ─────────────────────────────────────────────────

    async def impact_analysis(
        self, symbol_name: str,
        direction: str = "upstream",
        max_depth: int = 3,
        commit_hash: Optional[str] = None,
    ) -> str:
        """影响分析"""
        async with async_session_factory() as session:
            service = AnalyzeService(session)
            searcher = CodeSearcher(session)

            results = await searcher.search(
                self.repo_path, symbol_name, limit=3,
                commit_hash=commit_hash,
            )
            exact = [r for r in results if r.name == symbol_name]
            if not exact:
                return f"未找到符号: {symbol_name}"

            target = exact[0]
            impacts = await service._bfs_impact(
                self.repo_path, target.node_id,
                max_depth=min(max_depth, 5),
                commit_hash=commit_hash,
            )

            upstream = [i for i in impacts if i["direction"] == "upstream"]
            downstream = [i for i in impacts if i["direction"] == "downstream"]
            routes = [i for i in impacts if i.get("type") == "route"]

            lines = [f"═ 影响分析: {target.name} ═"]

            if direction in ("upstream", "both") and upstream:
                lines.append(f"\n上游影响: {len(upstream)} 处")
                for i in upstream[:12]:
                    lines.append(f"  ● {i.get('name', i['node_id'])}")

            if direction in ("downstream", "both") and downstream:
                lines.append(f"\n下游依赖: {len(downstream)} 处")
                for i in downstream[:12]:
                    lines.append(f"  → {i.get('name', i['node_id'])}")

            if routes:
                lines.append(f"\n⚠️ 受影响路由 ({len(routes)} 个):")
                for r in routes:
                    lines.append(f"  🌐 {r.get('name', r['node_id'])}")

            total = len(upstream) + len(downstream)
            risk = "高风险" if total > 50 else "中风险" if total > 10 else "低风险" if total > 0 else "无风险"
            lines.append(f"\n风险评级: {risk} (共影响 {total} 处)")

            hint = self._hint("使用 change_impact 分析具体代码改动的完整影响范围")
            return "\n".join(lines) + hint

    # ── Tool 4: 图谱数据 ─────────────────────────────────────────────────

    async def graph_data(
        self,
        node_limit: int = 200,
        commit_hash: Optional[str] = None,
    ) -> str:
        """获取知识图谱数据"""
        async with async_session_factory() as session:
            persister = GraphPersistence(session)
            type_counts = await persister.get_type_counts(self.repo_path, commit_hash)
            nodes = await persister.get_nodes_by_repo(self.repo_path, commit_hash, limit=node_limit)
            rels = await persister.get_relationships_by_repo(self.repo_path, commit_hash, limit=500)

            lines = [
                "═ 知识图谱概览 ═",
                f"节点: {len(nodes)}  关系: {len(rels)}",
                "\n节点类型分布:",
            ]
            for typ, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                lines.append(f"  {typ:12}: {count}")

            lines.append("\n代表性节点:")
            for typ in ["route", "class", "function"]:
                typed = [n for n in nodes if n.type == typ][:5]
                if typed:
                    lines.append(f"  [{typ}]:")
                    for n in typed:
                        lines.append(f"    - {n.name}")

            hint = self._hint("使用 search_code(query='<关键词>') 搜索特定符号")
            return "\n".join(lines) + hint

    # ── Tool 5: 变更影响分析 ─────────────────────────────────────────────

    async def change_impact(
        self,
        mode: str = "manual",
        file_path: str = "",
        start_line: int = 0,
        end_line: int = 0,
        base_commit: str = "",
        target_commit: str = "HEAD",
        max_depth: int = 3,
    ) -> str:
        """变更影响分析"""
        async with async_session_factory() as session:
            # 需要通过 repo_path 反查 project_identifier
            from sqlalchemy import select
            from app.models.project import Project
            result = await session.execute(
                select(Project).where(Project.code_repo_path == self.repo_path)
            )
            project = result.scalar_one_or_none()
            if not project:
                return f"未找到仓库对应的项目: {self.repo_path}"

            service = AnalyzeService(session)
            data = await service.change_impact_analysis(
                project.identifier,
                mode=mode,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                base_commit=base_commit,
                target_commit=target_commit,
                max_depth=max_depth,
            )

            if "error" in data:
                return f"❌ {data['error']}"

            lines = [
                "═ 变更影响分析 ═",
                f"模式: {data['mode']}",
            ]
            if data.get("target_commit"):
                lines.append(f"目标版本: {data['target_commit'][:8]}")

            changed = data.get("changed_symbols", [])
            if changed:
                lines.append(f"\n改动符号 ({len(changed)}):")
                for s in changed[:10]:
                    lines.append(f"  • [{s['type']}] {s['name']}")

            routes = data.get("impacted_routes", [])
            if routes:
                lines.append(f"\n⚠️ 受影响路由 ({len(routes)}):")
                for r in routes:
                    lines.append(f"  🌐 {r['name']}")

            lines.append(f"\n风险: {data.get('risk', 'unknown').upper()}")

            vd = data.get("version_diff")
            if vd:
                lines.append(f"版本差异: +{vd['added_count']} -{vd['removed_count']} ~{vd['modified_count']}")

            hint = self._hint("使用 impact_analysis 深入分析单个符号的调用链")
            return "\n".join(lines) + hint

    # ── Tool 6: 版本列表 ─────────────────────────────────────────────────

    async def list_commits(self, limit: int = 20) -> str:
        """列出已分析的 commit 版本"""
        async with async_session_factory() as session:
            persister = GraphPersistence(session)
            commits = await persister.list_commits(self.repo_path, limit)

            if not commits:
                return "暂无已分析的 commit 版本"

            lines = [f"共 {len(commits)} 个已分析版本:\n"]
            for i, c in enumerate(commits, 1):
                short = c.commit_hash[:8] if len(c.commit_hash) >= 8 else c.commit_hash
                msg = (c.commit_message or "无提交信息")[:35]
                lines.append(f"  {i}. `{short}` {msg} ({c.node_count}节点/{c.rel_count}关系)")

            hint = self._hint(
                "使用 graph_data(commit_hash='<hash>') 查看指定版本的图谱数据"
            )
            return "\n".join(lines) + hint

    # ── Tool 7: 读取文件 ─────────────────────────────────────────────────

    async def read_file(
        self, file_path: str,
        start_line: int = 0,
        end_line: int = 0,
    ) -> str:
        """读取源代码文件"""
        abs_path = f"{self.repo_path}/{file_path}"
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except FileNotFoundError:
            return f"文件不存在: {file_path}"
        except Exception as e:
            return f"读取失败: {e}"

        start = max(0, start_line - 1) if start_line > 0 else 0
        end = min(len(lines), end_line) if end_line > 0 else len(lines)
        content = "".join(lines[start:end])

        hint = self._hint(f"使用 search_code(query='<函数名>') 查找此文件中的符号")
        return f"═══ {file_path} ({start+1}-{end}/{len(lines)}行) ═══\n{content}{hint}"

    # ── Tool 8: 检查陈旧度 ───────────────────────────────────────────────

    async def check_staleness(self) -> str:
        """检查知识图谱是否相对于代码仓库已过期"""
        async with async_session_factory() as session:
            persister = GraphPersistence(session)
            commits = await persister.list_commits(self.repo_path, limit=1)
            if not commits:
                return "尚未分析过此仓库，无陈旧度信息" + self._hint(
                    "使用 graph_data() 查看仓库是否已建立索引"
                )

            indexed = commits[0]
            detector = StalenessDetector()
            report = detector.check(self.repo_path, indexed.commit_hash)

            lines = [
                "═ 陈旧度检测 ═",
                f"索引版本: {report.indexed_commit[:8]}",
                f"当前 HEAD: {report.current_head[:8] if report.current_head != 'unknown' else 'unknown'}",
            ]
            if report.is_stale:
                lines.append(f"落后 commit: {report.commits_behind}")
                lines.append(f"状态: ⚠️ {report.hint}")
                hint = self._hint("建议重新运行代码分析以更新知识图谱")
            else:
                lines.append(f"状态: ✅ {report.hint}")
                hint = self._hint("知识图谱是最新的，可以放心使用")

            return "\n".join(lines) + hint

    # ── Tool 9: 列出已索引仓库 ───────────────────────────────────────────

    async def list_repos(self) -> str:
        """列出所有已索引的仓库"""
        async with async_session_factory() as session:
            # 从 kg_commits 获取所有唯一的 repo_path
            from sqlalchemy import select, func
            from app.kg.persistence import KGCommit

            result = await session.execute(
                select(KGCommit.repo_path, func.count(KGCommit.commit_hash))
                .group_by(KGCommit.repo_path)
                .order_by(func.max(KGCommit.analyzed_at).desc())
            )
            repos = result.all()

            if not repos:
                return "暂无已索引的仓库" + self._hint(
                    "使用 graph_data() 分析第一个仓库"
                )

            lines = [f"共 {len(repos)} 个已索引仓库:\n"]
            for repo_path, commit_count in repos:
                # 获取最新版本的信息
                latest_result = await session.execute(
                    select(KGCommit)
                    .where(KGCommit.repo_path == repo_path)
                    .order_by(KGCommit.analyzed_at.desc())
                    .limit(1)
                )
                latest = latest_result.scalar_one_or_none()
                short = latest.commit_hash[:8] if latest else "?"
                lines.append(
                    f"  • {repo_path} "
                    f"(最新: {short}, {commit_count} 个版本, "
                    f"{latest.node_count}节点/{latest.rel_count}关系)"
                )

            hint = self._hint("使用 check_staleness() 检查特定仓库的索引是否过期")
            return "\n".join(lines) + hint

    # ── Tool 10: 路由映射 ────────────────────────────────────────────────

    async def route_map(
        self, route: str = "",
        commit_hash: Optional[str] = None,
    ) -> str:
        """列出所有路由及其 handler"""
        async with async_session_factory() as session:
            from sqlalchemy import select
            from app.kg.persistence import KGNode, KGRelationship

            ch = await self._resolve_commit(session, commit_hash)

            stmt = select(KGNode).where(
                KGNode.repo_path == self.repo_path,
                KGNode.type == "route",
            )
            if ch:
                stmt = stmt.where(KGNode.commit_hash == ch)
            if route:
                stmt = stmt.where(KGNode.name.ilike(f"%{route}%"))
            stmt = stmt.order_by(KGNode.name).limit(100)

            result = await session.execute(stmt)
            routes = result.scalars().all()

            if not routes:
                msg = f"未找到路由" if not route else f"未找到匹配 '{route}' 的路由"
                return msg + self._hint("使用 search_code(query='route', node_type='route') 搜索路由")

            lines = [f"找到 {len(routes)} 个路由:\n"]
            for r in routes:
                method = r.properties.get("method", "?") if r.properties else "?"
                framework = r.properties.get("framework", "?") if r.properties else "?"
                loc = f"{r.file_path}" if r.file_path else "?"
                lines.append(f"  [{method:6}] {r.name:50} ({framework}) {loc}")

            hint = self._hint("使用 api_impact(route='<路由名>') 分析修改某路由的影响")
            return "\n".join(lines) + hint

    # ── Tool 11: 工具映射 ────────────────────────────────────────────────

    async def tool_map(
        self, tool: str = "",
        commit_hash: Optional[str] = None,
    ) -> str:
        """列出所有 Tool 定义"""
        async with async_session_factory() as session:
            from sqlalchemy import select
            from app.kg.persistence import KGNode

            ch = await self._resolve_commit(session, commit_hash)

            stmt = select(KGNode).where(
                KGNode.repo_path == self.repo_path,
                KGNode.type == "tool",
            )
            if ch:
                stmt = stmt.where(KGNode.commit_hash == ch)
            if tool:
                stmt = stmt.where(KGNode.name.ilike(f"%{tool}%"))
            stmt = stmt.order_by(KGNode.name).limit(100)

            result = await session.execute(stmt)
            tools = result.scalars().all()

            if not tools:
                msg = f"未找到 Tool" if not tool else f"未找到匹配 '{tool}' 的 Tool"
                return msg + self._hint("使用 search_code(query='tool', node_type='tool') 搜索 Tool")

            lines = [f"找到 {len(tools)} 个 Tool 定义:\n"]
            for t in tools:
                desc = ""
                if t.properties:
                    desc = t.properties.get("description", "")[:60]
                loc = f"{t.file_path}" if t.file_path else "?"
                lines.append(f"  {t.name:30} {loc}")
                if desc:
                    lines.append(f"    → {desc}")

            hint = self._hint("使用 symbol_context(symbol_name='<tool名>') 查看 Tool 的详细定义")
            return "\n".join(lines) + hint

    # ── Tool 12: 图查询 (Cypher-like) ────────────────────────────────────

    async def cypher(
        self, query: str,
        commit_hash: Optional[str] = None,
    ) -> str:
        """执行图查询（使用预定义 SQL 模板）

        支持的查询模式:
        - "find_callers of <symbol>"    → 查找调用某符号的所有节点
        - "find_callees of <symbol>"    → 查找某符号调用的所有节点
        - "find_methods of <class>"     → 查找类的所有方法
        - "trace_process <name>"        → 追踪执行流
        - "symbols_in_file <path>"      → 列出文件中的符号
        - "imports_of <file>"           → 查找文件的 import 关系
        """
        async with async_session_factory() as session:
            from sqlalchemy import select, text as sa_text
            from app.kg.persistence import KGNode, KGRelationship

            ch = await self._resolve_commit(session, commit_hash)

            q = query.strip().lower()
            parts = q.split()

            # 解析查询模式
            if len(parts) >= 3 and parts[0] == "find_callers" and parts[1] == "of":
                symbol = " ".join(parts[2:])
                return await self._cypher_find_callers(session, ch, symbol)

            elif len(parts) >= 3 and parts[0] == "find_callees" and parts[1] == "of":
                symbol = " ".join(parts[2:])
                return await self._cypher_find_callees(session, ch, symbol)

            elif len(parts) >= 3 and parts[0] == "find_methods" and parts[1] == "of":
                class_name = " ".join(parts[2:])
                return await self._cypher_find_methods(session, ch, class_name)

            elif len(parts) >= 2 and parts[0] == "trace_process":
                proc_name = " ".join(parts[1:])
                return await self._cypher_trace_process(session, ch, proc_name)

            elif len(parts) >= 2 and parts[0] == "symbols_in_file":
                file_path = " ".join(parts[1:])
                return await self._cypher_symbols_in_file(session, ch, file_path)

            elif len(parts) >= 2 and parts[0] == "imports_of":
                file_path = " ".join(parts[1:])
                return await self._cypher_imports_of(session, ch, file_path)

            return (
                f"不支持的查询: '{query}'\n\n"
                "支持的查询模式:\n"
                "  find_callers of <symbol>\n"
                "  find_callees of <symbol>\n"
                "  find_methods of <class>\n"
                "  trace_process <name>\n"
                "  symbols_in_file <path>\n"
                "  imports_of <file>\n"
            ) + self._hint("使用 search_code(query='<关键词>') 查找符号名")

    async def _cypher_find_callers(
        self, session, ch, symbol: str,
    ) -> str:
        from sqlalchemy import select
        from app.kg.persistence import KGNode, KGRelationship

        # 先找目标节点
        stmt = select(KGNode).where(
            KGNode.repo_path == self.repo_path,
            KGNode.name == symbol,
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        result = await session.execute(stmt)
        targets = result.scalars().all()
        if not targets:
            return f"未找到符号: {symbol}"

        target = targets[0]
        # 找 CALLS 关系中 target 是目标节点的
        rel_stmt = select(KGRelationship).where(
            KGRelationship.repo_path == self.repo_path,
            KGRelationship.type == "CALLS",
            KGRelationship.target_node_id == target.node_id,
        )
        if ch:
            rel_stmt = rel_stmt.where(KGRelationship.commit_hash == ch)
        rel_result = await session.execute(rel_stmt)
        rels = rel_result.scalars().all()

        if not rels:
            return f"符号 '{symbol}' 没有被任何节点调用"

        caller_ids = [r.source_node_id for r in rels]
        caller_stmt = select(KGNode).where(
            KGNode.node_id.in_(caller_ids),
            KGNode.repo_path == self.repo_path,
        )
        if ch:
            caller_stmt = caller_stmt.where(KGNode.commit_hash == ch)
        caller_result = await session.execute(caller_stmt)
        callers = {n.node_id: n for n in caller_result.scalars().all()}

        lines = [f"调用 '{symbol}' 的节点 ({len(rels)} 处):\n"]
        for r in rels[:50]:
            caller = callers.get(r.source_node_id)
            name = caller.name if caller else r.source_node_id
            loc = f"{caller.file_path}" if caller and caller.file_path else ""
            lines.append(f"  ← {name} {loc}")

        return "\n".join(lines) + self._hint(
            f"使用 impact_analysis(symbol_name='{symbol}') 查看完整影响链"
        )

    async def _cypher_find_callees(
        self, session, ch, symbol: str,
    ) -> str:
        from sqlalchemy import select
        from app.kg.persistence import KGNode, KGRelationship

        stmt = select(KGNode).where(
            KGNode.repo_path == self.repo_path,
            KGNode.name == symbol,
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        result = await session.execute(stmt)
        targets = result.scalars().all()
        if not targets:
            return f"未找到符号: {symbol}"

        target = targets[0]
        rel_stmt = select(KGRelationship).where(
            KGRelationship.repo_path == self.repo_path,
            KGRelationship.type == "CALLS",
            KGRelationship.source_node_id == target.node_id,
        )
        if ch:
            rel_stmt = rel_stmt.where(KGRelationship.commit_hash == ch)
        rel_result = await session.execute(rel_stmt)
        rels = rel_result.scalars().all()

        if not rels:
            return f"符号 '{symbol}' 没有调用任何节点"

        callee_ids = [r.target_node_id for r in rels]
        callee_stmt = select(KGNode).where(
            KGNode.node_id.in_(callee_ids),
            KGNode.repo_path == self.repo_path,
        )
        if ch:
            callee_stmt = callee_stmt.where(KGNode.commit_hash == ch)
        callee_result = await session.execute(callee_stmt)
        callees = {n.node_id: n for n in callee_result.scalars().all()}

        lines = [f"'{symbol}' 调用的节点 ({len(rels)} 处):\n"]
        for r in rels[:50]:
            callee = callees.get(r.target_node_id)
            name = callee.name if callee else r.target_node_id
            loc = f"{callee.file_path}" if callee and callee.file_path else ""
            lines.append(f"  → {name} {loc}")

        return "\n".join(lines)

    async def _cypher_find_methods(
        self, session, ch, class_name: str,
    ) -> str:
        from sqlalchemy import select
        from app.kg.persistence import KGNode

        # 查找类节点
        class_stmt = select(KGNode).where(
            KGNode.repo_path == self.repo_path,
            KGNode.type == "class",
            KGNode.name == class_name,
        )
        if ch:
            class_stmt = class_stmt.where(KGNode.commit_hash == ch)
        result = await session.execute(class_stmt)
        classes = result.scalars().all()
        if not classes:
            return f"未找到类: {class_name}"

        lines = []
        for cls in classes:
            # 查找该类的方法（通过 node_id 前缀匹配或 file_path + name）
            method_stmt = select(KGNode).where(
                KGNode.repo_path == self.repo_path,
                KGNode.type == "method",
                KGNode.file_path == cls.file_path,
            )
            if ch:
                method_stmt = method_stmt.where(KGNode.commit_hash == ch)
            m_result = await session.execute(method_stmt)
            methods = m_result.scalars().all()
            # 过滤属于该类的方法
            class_methods = [
                m for m in methods
                if f"::{class_name}." in m.node_id
            ]

            loc = f"{cls.file_path}" if cls.file_path else "?"
            lines.append(f"类: {class_name} ({loc})")
            lines.append(f"  方法 ({len(class_methods)} 个):")
            for m in class_methods:
                lines.append(f"    • {m.name}")
            lines.append("")

        return "\n".join(lines) + self._hint(
            f"使用 symbol_context(symbol_name='{class_name}') 查看类的完整上下文"
        )

    async def _cypher_trace_process(
        self, session, ch, proc_name: str,
    ) -> str:
        from sqlalchemy import select
        from app.kg.persistence import KGNode, KGRelationship

        # 查找 process 节点
        stmt = select(KGNode).where(
            KGNode.repo_path == self.repo_path,
            KGNode.type == "process",
            KGNode.name.ilike(f"%{proc_name}%"),
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        result = await session.execute(stmt)
        processes = result.scalars().all()
        if not processes:
            return f"未找到执行流: {proc_name}"

        lines = []
        for proc in processes:
            # 查找 PROCESS 关系
            rel_stmt = select(KGRelationship).where(
                KGRelationship.repo_path == self.repo_path,
                KGRelationship.type.in_(["PART_OF_PROCESS", "PROCESS"]),
            )
            if ch:
                rel_stmt = rel_stmt.where(KGRelationship.commit_hash == ch)
            rel_result = await session.execute(rel_stmt)
            rels = rel_result.scalars().all()

            # 找与 process 相关的节点
            related = []
            for r in rels:
                if proc.node_id in (r.source_node_id, r.target_node_id):
                    related.append(r)

            lines.append(f"执行流: {proc.name}")
            lines.append(f"  相关节点 ({len(related)} 个):")
            for r in related[:20]:
                lines.append(f"    {r.source_node_id} → {r.target_node_id}")
            lines.append("")

        return "\n".join(lines)

    async def _cypher_symbols_in_file(
        self, session, ch, file_path: str,
    ) -> str:
        from sqlalchemy import select
        from app.kg.persistence import KGNode

        stmt = select(KGNode).where(
            KGNode.repo_path == self.repo_path,
            KGNode.file_path.ilike(f"%{file_path}%"),
        )
        if ch:
            stmt = stmt.where(KGNode.commit_hash == ch)
        stmt = stmt.order_by(KGNode.type, KGNode.name).limit(100)
        result = await session.execute(stmt)
        nodes = result.scalars().all()

        if not nodes:
            return f"未找到文件: {file_path}"

        lines = [f"文件 '{file_path}' 中的符号 ({len(nodes)} 个):\n"]
        current_type = None
        for n in nodes:
            if n.type != current_type:
                current_type = n.type
                lines.append(f"\n[{current_type}]:")
            lines.append(f"  • {n.name}")

        return "\n".join(lines) + self._hint(
            f"使用 read_file(file_path='{nodes[0].file_path}') 查看源码"
        )

    async def _cypher_imports_of(
        self, session, ch, file_path: str,
    ) -> str:
        from sqlalchemy import select
        from app.kg.persistence import KGRelationship

        # 找 IMPORTS 关系中 source 是 file://{file_path} 的
        file_id = f"file://{file_path}"
        stmt = select(KGRelationship).where(
            KGRelationship.repo_path == self.repo_path,
            KGRelationship.type == "IMPORTS",
            KGRelationship.source_node_id == file_id,
        )
        if ch:
            stmt = stmt.where(KGRelationship.commit_hash == ch)
        stmt = stmt.limit(50)
        result = await session.execute(stmt)
        rels = result.scalars().all()

        if not rels:
            return f"文件 '{file_path}' 没有 import 关系"

        lines = [f"文件 '{file_path}' 的 import ({len(rels)} 条):\n"]
        for r in rels:
            target = r.target_node_id.replace("file://", "")
            lines.append(f"  → {target}")

        return "\n".join(lines)

    async def _resolve_commit(self, session, commit_hash: Optional[str]) -> Optional[str]:
        """解析 commit_hash（内部辅助）"""
        from sqlalchemy import select
        from app.kg.persistence import KGCommit
        if commit_hash:
            return commit_hash
        result = await session.execute(
            select(KGCommit.commit_hash)
            .where(KGCommit.repo_path == self.repo_path)
            .order_by(KGCommit.analyzed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ── Tool 13: API 影响分析 ────────────────────────────────────────────

    async def api_impact(
        self, route: str = "",
        file: str = "",
        commit_hash: Optional[str] = None,
    ) -> str:
        """API 变更影响报告

        分析修改某 API 路由的影响范围，包括：
        - 受影响的消费者数
        - 相关 handler 和 middleware
        - 风险评级
        """
        async with async_session_factory() as session:
            from sqlalchemy import select
            from app.kg.persistence import KGNode, KGRelationship

            ch = await self._resolve_commit(session, commit_hash)

            # 查找目标路由
            stmt = select(KGNode).where(
                KGNode.repo_path == self.repo_path,
                KGNode.type == "route",
            )
            if ch:
                stmt = stmt.where(KGNode.commit_hash == ch)
            if route:
                stmt = stmt.where(KGNode.name.ilike(f"%{route}%"))
            elif file:
                stmt = stmt.where(KGNode.file_path.ilike(f"%{file}%"))
            else:
                return "请提供 route 或 file 参数" + self._hint(
                    "使用 route_map() 查看所有路由"
                )

            result = await session.execute(stmt.limit(20))
            routes = result.scalars().all()

            if not routes:
                return f"未找到路由"

            lines = ["═ API 变更影响报告 ═\n"]
            for r in routes:
                method = r.properties.get("method", "?") if r.properties else "?"
                framework = r.properties.get("framework", "?") if r.properties else "?"
                lines.append(f"路由: {r.name} ({method}, {framework})")
                lines.append(f"位置: {r.file_path or '?'}")

                # 查找与路由相关的节点（通过关系或文件路径）
                rel_stmt = select(KGRelationship).where(
                    KGRelationship.repo_path == self.repo_path,
                    KGRelationship.type.in_(["CALLS", "IMPORTS", "DEFINED_IN"]),
                )
                if ch:
                    rel_stmt = rel_stmt.where(KGRelationship.commit_hash == ch)
                rel_result = await session.execute(rel_stmt)
                all_rels = rel_result.scalars().all()

                # 找与路由相关的
                related = [rel for rel in all_rels
                           if r.node_id in (rel.source_node_id, rel.target_node_id)]
                if related:
                    lines.append(f"关联关系 ({len(related)} 条):")
                    for rel in related[:10]:
                        lines.append(f"  {rel.type}: {rel.source_node_id} → {rel.target_node_id}")
                else:
                    lines.append("关联关系: 无")

                # 查找同目录下的 handler
                if r.file_path:
                    dir_path = r.file_path.rsplit("/", 1)[0] if "/" in r.file_path else ""
                    if dir_path:
                        handler_stmt = select(KGNode).where(
                            KGNode.repo_path == self.repo_path,
                            KGNode.file_path.ilike(f"{dir_path}%"),
                            KGNode.type.in_(["function", "method"]),
                        )
                        if ch:
                            handler_stmt = handler_stmt.where(KGNode.commit_hash == ch)
                        h_result = await session.execute(handler_stmt.limit(10))
                        handlers = h_result.scalars().all()
                        if handlers:
                            lines.append(f"同目录 Handler ({len(handlers)} 个):")
                            for h in handlers:
                                lines.append(f"  • {h.name}")

                lines.append("")

            return "\n".join(lines) + self._hint(
                "使用 impact_analysis(symbol_name='<handler名>') 深入分析影响链"
            )

    # ── Tool 14: 图谱辅助重命名 ───────────────────────────────────────────

    async def rename(
        self, symbol_name: str, new_name: str,
        file_path: str = "", dry_run: bool = True,
    ) -> str:
        """多文件协调重命名

        1. 在图中找到符号的所有引用（CALLS/IMPORTS/EXTENDS 等边）
        2. 标记每个引用的置信度：graph（高）vs text_match（中）
        3. dry_run=True 时只预览，不修改
        4. dry_run=False 时执行实际文件修改（带备份）
        """
        import re
        from pathlib import Path
        from sqlalchemy import select
        from app.kg.persistence import KGNode, KGRelationship

        async with async_session_factory() as session:
            ch = await self._resolve_commit(session, None)

            # 1. 查找符号节点
            stmt = select(KGNode).where(
                KGNode.repo_path == self.repo_path,
                KGNode.name == symbol_name,
            )
            if ch:
                stmt = stmt.where(KGNode.commit_hash == ch)
            if file_path:
                stmt = stmt.where(KGNode.file_path.ilike(f"%{file_path}%"))

            result = await session.execute(stmt)
            targets = result.scalars().all()

            if not targets:
                return f"未找到符号: {symbol_name}" + self._hint(
                    f"使用 search_code(query='{symbol_name}') 查找相似符号"
                )

            if len(targets) > 1 and not file_path:
                lines = [f"找到 {len(targets)} 个同名符号，请用 file_path 参数指定:\n"]
                for t in targets[:10]:
                    lines.append(f"  • {t.name} in {t.file_path} ({t.type})")
                return "\n".join(lines) + self._hint(
                    f"使用 rename(symbol_name='{symbol_name}', file_path='...') 指定文件"
                )

            target = targets[0]

            # 2. 收集相关边
            rel_stmt = select(KGRelationship).where(
                KGRelationship.repo_path == self.repo_path,
            )
            if ch:
                rel_stmt = rel_stmt.where(KGRelationship.commit_hash == ch)
            rel_stmt = rel_stmt.where(
                (KGRelationship.source_node_id == target.node_id)
                | (KGRelationship.target_node_id == target.node_id)
            )
            rel_result = await session.execute(rel_stmt)
            rels = rel_result.scalars().all()

            # 3. 解析涉及文件（graph 高置信度）
            graph_files: set[str] = set()
            if target.file_path:
                graph_files.add(target.file_path)

            for rel in rels:
                # 解析 source 和 target 的 node_id 提取文件路径
                for nid in (rel.source_node_id, rel.target_node_id):
                    # node_id 格式: type://file_path::name
                    if "//" in nid and "::" in nid:
                        fp = nid.split("//", 1)[1].split("::", 1)[0]
                        if fp:
                            graph_files.add(fp)

            # 4. 文本搜索：在 graph_files 和 repo 内其他可能文件中查找
            repo_path = Path(self.repo_path)
            all_matches: list[dict] = []

            # 先搜索高置信度文件
            for fp in sorted(graph_files):
                abs_path = repo_path / fp
                if not abs_path.exists():
                    continue
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                # 使用单词边界匹配
                pattern = re.compile(rf"\b{re.escape(symbol_name)}\b")
                for line_no, line in enumerate(content.splitlines(), 1):
                    for match in pattern.finditer(line):
                        all_matches.append({
                            "file": fp,
                            "line": line_no,
                            "column": match.start() + 1,
                            "context": line.strip(),
                            "confidence": "graph",
                        })

            # 5. 生成报告
            lines = [
                f"═ 重命名预览: {symbol_name} → {new_name} ═",
                f"目标符号: {target.name} ({target.type}) in {target.file_path or '?'}",
                f"图谱关联: {len(rels)} 条关系, {len(graph_files)} 个文件",
                f"发现匹配: {len(all_matches)} 处\n",
            ]

            # 按文件分组
            by_file: dict[str, list[dict]] = {}
            for m in all_matches:
                by_file.setdefault(m["file"], []).append(m)

            for fp, matches in sorted(by_file.items()):
                lines.append(f"📄 {fp}")
                for m in matches[:20]:
                    conf_icon = "🔵" if m["confidence"] == "graph" else "⚪"
                    lines.append(
                        f"  {conf_icon} L{m['line']:4}  {m['context']}"
                    )
                if len(matches) > 20:
                    lines.append(f"  ... 还有 {len(matches) - 20} 处")
                lines.append("")

            if dry_run:
                hint = self._hint(
                    f"确认无误后，使用 rename(symbol_name='{symbol_name}', "
                    f"new_name='{new_name}', file_path='{target.file_path or ''}', "
                    f"dry_run=False) 执行实际替换"
                )
                return "\n".join(lines) + hint

            # 6. 执行替换（dry_run=False）
            modified: list[str] = []
            errors: list[str] = []

            for fp in sorted(by_file.keys()):
                abs_path = repo_path / fp
                if not abs_path.exists():
                    continue
                try:
                    content = abs_path.read_text(encoding="utf-8", errors="replace")
                    # 备份
                    backup_path = abs_path.with_suffix(abs_path.suffix + ".rename-bak")
                    backup_path.write_text(content, encoding="utf-8")

                    # 替换（带单词边界）
                    pattern = re.compile(rf"\b{re.escape(symbol_name)}\b")
                    new_content, count = pattern.subn(new_name, content)

                    if count > 0:
                        abs_path.write_text(new_content, encoding="utf-8")
                        modified.append(f"{fp} ({count} 处)")
                except Exception as e:
                    errors.append(f"{fp}: {e}")

            lines.append("═ 执行结果 ═")
            if modified:
                lines.append(f"✅ 已修改 {len(modified)} 个文件:")
                for m in modified:
                    lines.append(f"  • {m}")
            if errors:
                lines.append(f"❌ 错误 ({len(errors)} 个):")
                for e in errors:
                    lines.append(f"  • {e}")
            if not modified and not errors:
                lines.append("没有文件被修改")

            hint = self._hint(
                "替换后请运行测试验证代码正确性，并使用 git diff 检查变更"
            )
            return "\n".join(lines) + hint

    # ── Tool 15: API 响应形状检查 ─────────────────────────────────────────

    async def shape_check(
        self, route: str = "", symbol: str = "",
        commit_hash: Optional[str] = None,
    ) -> str:
        """检查 API handler 的响应形状

        分析路由对应的 handler 函数的返回类型注解，检查常见的设计问题：
        - 缺少返回类型注解
        - 返回类型过于宽泛（Any / dict / object）
        - 返回裸 Response 而非具体的响应模型
        - 返回 None（GET 请求可能不合适）
        """
        from sqlalchemy import select
        from app.kg.persistence import KGNode, KGRelationship

        async with async_session_factory() as session:
            ch = await self._resolve_commit(session, commit_hash)

            # 确定目标 handler
            handlers: list[KGNode] = []

            if route:
                # 1. 查找路由节点
                route_stmt = select(KGNode).where(
                    KGNode.repo_path == self.repo_path,
                    KGNode.type == "route",
                    KGNode.name.ilike(f"%{route}%"),
                )
                if ch:
                    route_stmt = route_stmt.where(KGNode.commit_hash == ch)
                route_result = await session.execute(route_stmt.limit(5))
                routes = route_result.scalars().all()

                if not routes:
                    return f"未找到路由: {route}" + self._hint(
                        "使用 route_map() 查看所有路由"
                    )

                # 2. 查找同目录下的 handler 函数
                for r in routes:
                    if not r.file_path:
                        continue
                    dir_path = r.file_path.rsplit("/", 1)[0] if "/" in r.file_path else ""
                    if not dir_path:
                        continue
                    handler_stmt = select(KGNode).where(
                        KGNode.repo_path == self.repo_path,
                        KGNode.file_path.ilike(f"{dir_path}%"),
                        KGNode.type.in_(["function", "method"]),
                    )
                    if ch:
                        handler_stmt = handler_stmt.where(KGNode.commit_hash == ch)
                    h_result = await session.execute(handler_stmt.limit(20))
                    handlers.extend(h_result.scalars().all())

            elif symbol:
                # 直接查找函数/方法
                sym_stmt = select(KGNode).where(
                    KGNode.repo_path == self.repo_path,
                    KGNode.type.in_(["function", "method"]),
                    KGNode.name == symbol,
                )
                if ch:
                    sym_stmt = sym_stmt.where(KGNode.commit_hash == ch)
                sym_result = await session.execute(sym_stmt.limit(5))
                handlers = sym_result.scalars().all()

            if not handlers:
                return "未找到 handler，请提供 route 或 symbol 参数" + self._hint(
                    "使用 route_map() 查看路由，或 search_code() 查找函数"
                )

            lines = ["═ API 响应形状检查 ═\n"]
            issues_found = 0

            for h in handlers:
                returns = ""
                if h.properties:
                    returns = h.properties.get("returns", "")

                loc = f"{h.file_path}" if h.file_path else "?"
                lines.append(f"Handler: {h.name} ({loc})")
                lines.append(f"返回类型: {returns or '(未注解)'}")

                handler_issues = []

                # 检查 1: 缺少返回类型
                if not returns:
                    handler_issues.append("❌ 缺少返回类型注解 — 建议添加具体的响应模型")

                # 检查 2: 过于宽泛的类型
                if returns and returns.lower() in ("any", "dict", "object", "dict[str, any]", "mapping"):
                    handler_issues.append("⚠️  返回类型过于宽泛 — 建议使用具体的 Pydantic 模型")

                # 检查 3: 裸 Response
                if returns and returns.lower() in ("response", "jsonresponse", "httpresponse"):
                    handler_issues.append("⚠️  返回裸 Response — 建议使用强类型的响应模型，便于文档生成")

                # 检查 4: 返回 None
                if returns and returns.lower() == "none":
                    handler_issues.append("⚠️  返回 None — 如果是 GET 请求，客户端可能期望有返回数据")

                # 检查 5: 缺少 Union/Optional 错误类型
                if returns and returns.lower() not in ("none", ""):
                    if "union" not in returns.lower() and "optional" not in returns.lower() and "|" not in returns:
                        # 简单的启发式：如果返回类型不包含 Union/Optional，可能缺少错误响应
                        # 但这只是一个弱提示
                        pass

                # 检查 6: 返回 str/int/float 等原始类型
                if returns and returns.lower() in ("str", "int", "float", "bool", "bytes"):
                    handler_issues.append("⚠️  返回原始类型 — API 响应通常应返回结构化对象")

                if handler_issues:
                    lines.append("问题:")
                    for issue in handler_issues:
                        lines.append(f"  {issue}")
                    issues_found += len(handler_issues)
                else:
                    lines.append("✅ 返回类型看起来合理")

                lines.append("")

            if issues_found:
                lines.append(f"共发现 {issues_found} 个问题")
            else:
                lines.append("未发现明显问题")

            return "\n".join(lines) + self._hint(
                "使用 symbol_context(symbol_name='<handler名>') 查看 handler 的详细上下文"
            )


# ── MCP Server 启动 ──────────────────────────────────────────────────────


async def run_mcp_server(repo_path: str):
    """运行 MCP Server（stdio 模式）"""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("[MCP] 错误: 未安装 mcp 包，请运行: pip install mcp")
        return

    mcp = FastMCP("knowledge-graph")
    tools = KGTools(repo_path)

    @mcp.tool()
    async def search_code(query: str, node_type: Optional[str] = None,
                          limit: int = 20, commit_hash: Optional[str] = None) -> str:
        return await tools.search_code(query, node_type, limit, commit_hash)

    @mcp.tool()
    async def symbol_context(symbol_name: str, commit_hash: Optional[str] = None) -> str:
        return await tools.symbol_context(symbol_name, commit_hash)

    @mcp.tool()
    async def impact_analysis(symbol_name: str, direction: str = "upstream",
                              max_depth: int = 3, commit_hash: Optional[str] = None) -> str:
        return await tools.impact_analysis(symbol_name, direction, max_depth, commit_hash)

    @mcp.tool()
    async def graph_data(node_limit: int = 200, commit_hash: Optional[str] = None) -> str:
        return await tools.graph_data(node_limit, commit_hash)

    @mcp.tool()
    async def change_impact(mode: str = "manual", file_path: str = "",
                            start_line: int = 0, end_line: int = 0,
                            base_commit: str = "", target_commit: str = "HEAD",
                            max_depth: int = 3) -> str:
        return await tools.change_impact(mode, file_path, start_line, end_line,
                                         base_commit, target_commit, max_depth)

    @mcp.tool()
    async def list_commits(limit: int = 20) -> str:
        return await tools.list_commits(limit)

    @mcp.tool()
    async def read_file(file_path: str, start_line: int = 0, end_line: int = 0) -> str:
        return await tools.read_file(file_path, start_line, end_line)

    @mcp.tool()
    async def check_staleness() -> str:
        return await tools.check_staleness()

    @mcp.tool()
    async def list_repos() -> str:
        return await tools.list_repos()

    @mcp.tool()
    async def route_map(route: str = "", commit_hash: Optional[str] = None) -> str:
        return await tools.route_map(route, commit_hash)

    @mcp.tool()
    async def tool_map(tool: str = "", commit_hash: Optional[str] = None) -> str:
        return await tools.tool_map(tool, commit_hash)

    @mcp.tool()
    async def cypher(query: str, commit_hash: Optional[str] = None) -> str:
        return await tools.cypher(query, commit_hash)

    @mcp.tool()
    async def api_impact(route: str = "", file: str = "", commit_hash: Optional[str] = None) -> str:
        return await tools.api_impact(route, file, commit_hash)

    @mcp.tool()
    async def rename(symbol_name: str, new_name: str,
                     file_path: str = "", dry_run: bool = True) -> str:
        return await tools.rename(symbol_name, new_name, file_path, dry_run)

    @mcp.tool()
    async def shape_check(route: str = "", symbol: str = "", commit_hash: Optional[str] = None) -> str:
        return await tools.shape_check(route, symbol, commit_hash)

    tool_names = [
        "search_code", "symbol_context", "impact_analysis", "graph_data",
        "change_impact", "list_commits", "read_file",
        "check_staleness", "list_repos",
        "route_map", "tool_map", "cypher", "api_impact", "rename", "shape_check",
    ]
    print(f"[MCP] 知识图谱服务启动 (stdio)")
    print(f"[MCP] 仓库: {repo_path}")
    print(f"[MCP] 工具 ({len(tool_names)} 个): {', '.join(tool_names)}")
    await mcp.run_stdio_async()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="知识图谱 MCP 服务")
    parser.add_argument("--repo", required=True, help="代码仓库路径")
    args = parser.parse_args()
    asyncio.run(run_mcp_server(args.repo))


if __name__ == "__main__":
    main()
