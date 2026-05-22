"""
代码分析 Agent 工具集

为 code_analysis_agent 提供代码知识图谱查询能力。
9个工具覆盖搜索、上下文、影响分析、图谱数据、变更分析、版本管理和文件读取。
"""

from langchain_core.tools import tool

from app.config.database import async_session_factory
from app.services.code_repo_service import CodeRepoService
from app.services.analyze_service import AnalyzeService
from app.kg.search import CodeSearcher
from app.kg.persistence import GraphPersistence


# ── 辅助函数 ────────────────────────────────────────────────────────────


async def _get_repo_path(project_identifier: str) -> str:
    """获取项目代码仓库路径"""
    async with async_session_factory() as session:
        repo_service = CodeRepoService(session)
        project = await repo_service.get_project(project_identifier)
        if not project.code_repo_path:
            raise ValueError(f"项目 {project_identifier} 未配置代码仓库路径")
        return project.code_repo_path


# ── Tool 1: 代码搜索 ───────────────────────────────────────────────────


@tool
async def kg_search_code(
    project_identifier: str,
    query: str,
    node_type: str = "",
    limit: int = 10,
    commit_hash: str = "",
) -> str:
    """搜索代码知识图谱，查找匹配的代码符号

    在项目的代码知识图谱中搜索类、函数、变量等符号。
    支持 BM25 + FTS 混合搜索，可指定 commit 版本。

    Args:
        project_identifier: 项目标识符 (如 "PR-1")
        query: 搜索关键词（类名、函数名、概念名）
        node_type: 过滤类型（class/function/method/variable/file/route/tool，留空搜索全部）
        limit: 最大返回数（默认 10，最大 30）
        commit_hash: 可选，指定 commit 版本（不传则取最新）

    Returns:
        格式化的搜索结果列表
    """
    repo_path = await _get_repo_path(project_identifier)
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search(
            repo_path,
            query,
            node_type=node_type if node_type else None,
            limit=min(limit, 30),
            commit_hash=commit_hash if commit_hash else None,
        )

        if not results:
            return f"未找到匹配 '{query}' 的符号"

        lines = [f"找到 {len(results)} 个匹配 '{query}' 的符号:\n"]
        for r in results:
            loc = f"{r.file_path}" if r.file_path else "?"
            if r.start_line:
                loc += f"#{r.start_line}"
            score = f" (score: {r.score:.1f})" if r.score > 0 else ""
            lines.append(f"  [{r.type:10}] {r.name:40} {loc}{score}")

        return "\n".join(lines)


# ── Tool 2: 符号上下文 ──────────────────────────────────────────────────


@tool
async def kg_get_symbol_context(
    project_identifier: str,
    symbol_name: str,
    commit_hash: str = "",
) -> str:
    """获取代码符号的详细信息

    查询某个代码符号（类、函数、变量）的定义位置、调用关系和源码片段。
    Agent 需要了解某个函数/类的实现细节时使用。

    Args:
        project_identifier: 项目标识符
        symbol_name: 符号名称（精确匹配或模糊匹配）
        commit_hash: 可选，指定 commit 版本

    Returns:
        符号的详细信息（定义位置、调用者、被调用者、源码）
    """
    repo_path = await _get_repo_path(project_identifier)
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search(
            repo_path, symbol_name, limit=5,
            commit_hash=commit_hash if commit_hash else None,
        )
        exact = [r for r in results if r.name == symbol_name]
        target = exact[0] if exact else (results[0] if results else None)

        if not target:
            return f"未找到符号: {symbol_name}"

        ctx = await searcher.get_node_context(
            repo_path, target.node_id,
            commit_hash=commit_hash if commit_hash else None,
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

        # 调用者
        callers = [r for r in rels if r["type"] == "CALLS" and r["target"] == node["id"]]
        callees = [r for r in rels if r["type"] == "CALLS" and r["source"] == node["id"]]
        contains = [r for r in rels if r["type"] == "CONTAINS"]
        extends = [r for r in rels if r["type"] == "EXTENDS"]

        if callers:
            lines.append(f"\n调用者 ({len(callers)} 处):")
            for r in callers[:10]:
                name = r["source"].split("::")[-1] if "::" in r["source"] else r["source"]
                lines.append(f"  ← {name}")
            if len(callers) > 10:
                lines.append(f"  ... 还有 {len(callers) - 10} 个")

        if callees:
            lines.append(f"\n被调用 ({len(callees)} 处):")
            for r in callees[:10]:
                name = r["target"].split("::")[-1] if "::" in r["target"] else r["target"]
                lines.append(f"  → {name}")
            if len(callees) > 10:
                lines.append(f"  ... 还有 {len(callees) - 10} 个")

        if extends:
            lines.append(f"\n继承关系 ({len(extends)}):")
            for r in extends:
                if r["source"] == node["id"]:
                    lines.append(f"  extends → {r['target']}")
                else:
                    lines.append(f"  ← extends {r['source']}")

        # 源码片段
        if source:
            lines.append(f"\n源码片段 ({source['start_line']}-{source['end_line']} 行):")
            snippet_lines = source["content"].split("\n")
            for i, line in enumerate(snippet_lines[:25], start=source["start_line"]):
                lines.append(f"  {i:4}| {line}")
            if len(snippet_lines) > 25:
                lines.append("  ... (截断)")

        return "\n".join(lines)


# ── Tool 3: 影响分析 ───────────────────────────────────────────────────


@tool
async def kg_impact_analysis(
    project_identifier: str,
    symbol_name: str,
    direction: str = "both",
    max_depth: int = 3,
    commit_hash: str = "",
) -> str:
    """分析修改某代码符号的影响范围

    分析修改一个函数/类/变量会影响到哪些代码。
    支持指定遍历深度和 commit 版本。

    Args:
        project_identifier: 项目标识符
        symbol_name: 要分析的符号名称
        direction: 分析方向
                   "upstream" - 谁调用了它
                   "downstream" - 它调用了谁
                   "both" - 双向分析（默认）
        max_depth: BFS 遍历深度（1-5，默认 3）
        commit_hash: 可选，指定 commit 版本

    Returns:
        影响分析报告
    """
    repo_path = await _get_repo_path(project_identifier)
    async with async_session_factory() as session:
        service = AnalyzeService(session)
        searcher = CodeSearcher(session)

        # 定位符号
        results = await searcher.search(
            repo_path, symbol_name, limit=3,
            commit_hash=commit_hash if commit_hash else None,
        )
        exact = [r for r in results if r.name == symbol_name]
        target = exact[0] if exact else (results[0] if results else None)

        if not target:
            return f"未找到符号: {symbol_name}"

        # BFS 影响分析
        impacts = await service._bfs_impact(
            repo_path, target.node_id,
            max_depth=min(max_depth, 5),
            commit_hash=commit_hash if commit_hash else None,
        )

        upstream = [i for i in impacts if i["direction"] == "upstream"]
        downstream = [i for i in impacts if i["direction"] == "downstream"]
        routes = [i for i in impacts if i.get("type") == "route"]

        lines = [
            f"═ 影响分析: {target.name} ({target.type}) ═",
            f"位置: {target.file_path or '?'}#{target.start_line or '?'}",
            f"遍历深度: {max_depth}",
        ]

        if commit_hash:
            lines.append(f"版本: {commit_hash[:8]}")

        if direction in ("upstream", "both") and upstream:
            lines.append(f"\n■ 上游影响 (谁调用了 {target.name}): {len(upstream)} 处")
            for i in upstream[:15]:
                lines.append(f"  ● {i.get('name', i['node_id'])} ({i.get('type', 'unknown')})")
            if len(upstream) > 15:
                lines.append(f"  ... 还有 {len(upstream) - 15} 个")

        if direction in ("downstream", "both") and downstream:
            lines.append(f"\n■ 下游依赖 ({target.name} 调用的函数): {len(downstream)} 处")
            for i in downstream[:15]:
                lines.append(f"  → {i.get('name', i['node_id'])} ({i.get('type', 'unknown')})")
            if len(downstream) > 15:
                lines.append(f"  ... 还有 {len(downstream) - 15} 个")

        if routes:
            lines.append(f"\n⚠️ 受影响路由 ({len(routes)} 个):")
            for r in routes:
                lines.append(f"  🌐 {r.get('name', r['node_id'])}")

        total = len(upstream) + len(downstream)
        if total > 50:
            risk = "高风险"
        elif total > 10:
            risk = "中风险"
        elif total > 0:
            risk = "低风险"
        else:
            risk = "无风险"

        lines.append(f"\n■ 风险评级: {risk} (共影响 {total} 处)")
        return "\n".join(lines)


# ── Tool 4: 图谱数据 ───────────────────────────────────────────────────


@tool
async def kg_graph_data(
    project_identifier: str,
    node_limit: int = 200,
    commit_hash: str = "",
) -> str:
    """获取知识图谱的节点和关系数据

    获取知识图谱的可视化数据，包括节点列表和关系列表。
    用于了解项目整体代码结构。

    Args:
        project_identifier: 项目标识符
        node_limit: 最大节点数（默认 200）
        commit_hash: 可选，指定 commit 版本

    Returns:
        节点类型统计和代表性节点列表
    """
    repo_path = await _get_repo_path(project_identifier)
    async with async_session_factory() as session:
        persister = GraphPersistence(session)
        ch = commit_hash if commit_hash else None

        # 类型统计
        type_counts = await persister.get_type_counts(repo_path, ch)
        nodes = await persister.get_nodes_by_repo(repo_path, ch, limit=node_limit)
        rels = await persister.get_relationships_by_repo(repo_path, ch, limit=500)

        lines = [
            "═ 知识图谱概览 ═",
            f"节点: {len(nodes)} (limit: {node_limit})",
            f"关系: {len(rels)} (limit: 500)",
            "",
            "节点类型分布:",
        ]
        for typ, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {typ:12}: {count:5}")

        # 按类型展示代表性节点
        lines.append("\n代表性节点:")
        for typ in ["route", "tool", "process", "class", "function", "method"]:
            typed_nodes = [n for n in nodes if n.type == typ][:5]
            if typed_nodes:
                lines.append(f"\n  [{typ}]:")
                for n in typed_nodes:
                    loc = f"{n.file_path}#{n.start_line}" if n.file_path else ""
                    lines.append(f"    - {n.name} {loc}")

        return "\n".join(lines)


# ── Tool 5: 变更影响分析 ────────────────────────────────────────────────


@tool
async def kg_change_impact(
    project_identifier: str,
    mode: str = "manual",
    file_path: str = "",
    start_line: int = 0,
    end_line: int = 0,
    base_commit: str = "",
    target_commit: str = "HEAD",
    max_depth: int = 3,
) -> str:
    """变更影响分析：分析代码改动的影响范围

    支持三种模式：
    - manual: 手动输入文件路径+行号范围
    - git_diff: 基于 git diff 自动定位改动
    - compare_commits: 对比两个已分析 commit 版本的图谱差异

    Args:
        project_identifier: 项目标识符
        mode: 模式 (manual | git_diff | compare_commits)
        file_path: manual 模式下的文件路径
        start_line: manual 模式下的起始行
        end_line: manual 模式下的结束行
        base_commit: git_diff/compare_commits 的基准 commit
        target_commit: 目标 commit（默认 HEAD）
        max_depth: BFS 遍历深度

    Returns:
        变更影响分析报告
    """
    async with async_session_factory() as session:
        service = AnalyzeService(session)
        result = await service.change_impact_analysis(
            project_identifier,
            mode=mode,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            base_commit=base_commit,
            target_commit=target_commit,
            max_depth=max_depth,
        )

        if "error" in result:
            return f"❌ 分析失败: {result['error']}"

        lines = [
            "═ 变更影响分析报告 ═",
            f"模式: {result['mode']}",
        ]

        if result.get("base_commit"):
            lines.append(f"基准: {result['base_commit'][:8]}")
        if result.get("target_commit"):
            lines.append(f"目标: {result['target_commit'][:8]}")

        # 版本差异
        vd = result.get("version_diff")
        if vd:
            lines.append(f"\n版本差异:")
            lines.append(f"  新增: {vd['added_count']}  删除: {vd['removed_count']}  修改: {vd['modified_count']}")

        # 改动符号
        changed = result.get("changed_symbols", [])
        if changed:
            lines.append(f"\n改动符号 ({len(changed)} 个):")
            for s in changed[:15]:
                lines.append(f"  • [{s['type']}] {s['name']}")
            if len(changed) > 15:
                lines.append(f"  ... 还有 {len(changed) - 15} 个")

        # 受影响路由
        routes = result.get("impacted_routes", [])
        if routes:
            lines.append(f"\n⚠️ 受影响路由 ({len(routes)} 个):")
            for r in routes:
                lines.append(f"  🌐 {r['name']}")

        # 上下游
        up = result.get("upstream", [])
        down = result.get("downstream", [])
        if up:
            lines.append(f"\n上游影响 ({len(up)} 处):")
            for u in up[:10]:
                lines.append(f"  ← [{u['type']}] {u['name']}")
        if down:
            lines.append(f"\n下游影响 ({len(down)} 处):")
            for d in down[:10]:
                lines.append(f"  → [{d['type']}] {d['name']}")

        lines.append(f"\n■ 风险评级: {result.get('risk', 'unknown').upper()}")
        lines.append(f"摘要: {result.get('summary', '')}")

        return "\n".join(lines)


# ── Tool 6: 版本列表 ───────────────────────────────────────────────────


@tool
async def kg_list_commits(
    project_identifier: str,
    limit: int = 20,
) -> str:
    """列出已分析的 commit 版本

    获取项目已分析的所有 commit 版本列表，按分析时间倒序。

    Args:
        project_identifier: 项目标识符
        limit: 最大返回数

    Returns:
        commit 版本列表
    """
    async with async_session_factory() as session:
        service = AnalyzeService(session)
        commits = await service.list_commits(project_identifier, limit)

        if not commits:
            return "暂无已分析的 commit 版本"

        lines = [f"共 {len(commits)} 个已分析版本:\n"]
        for i, c in enumerate(commits, 1):
            msg = c.get("commit_message", "无提交信息")[:40]
            author = c.get("commit_author", "?")
            nodes = c.get("node_count", 0)
            rels = c.get("rel_count", 0)
            short = c.get("short_hash", c["commit_hash"][:8])
            lines.append(
                f"  {i}. {short}  {msg}  "
                f"(作者: {author}, {nodes}节点/{rels}关系)"
            )

        return "\n".join(lines)


# ── Tool 7: 读取文件 ───────────────────────────────────────────────────


@tool
async def kg_read_file(
    project_identifier: str,
    file_path: str,
    start_line: int = 0,
    end_line: int = 0,
) -> str:
    """读取源代码文件内容

    读取项目代码仓库中的指定文件。

    Args:
        project_identifier: 项目标识符
        file_path: 文件路径（相对于仓库根目录）
        start_line: 起始行号（从1开始，0表示从头）
        end_line: 结束行号（0表示到文件末尾）

    Returns:
        文件内容
    """
    repo_path = await _get_repo_path(project_identifier)
    abs_path = f"{repo_path}/{file_path}"

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return f"文件不存在: {file_path}"
    except Exception as e:
        return f"读取文件失败: {e}"

    start = max(0, start_line - 1) if start_line > 0 else 0
    end = min(len(lines), end_line) if end_line > 0 else len(lines)

    if start >= len(lines):
        return f"起始行 {start_line} 超出文件范围（共 {len(lines)} 行）"

    content = "".join(lines[start:end])
    header = f"═══ {file_path} ({start + 1}-{end} / {len(lines)} 行) ═══\n"
    return header + content


# ── Tool 8: 按类型搜索 ─────────────────────────────────────────────────


@tool
async def kg_search_by_type(
    project_identifier: str,
    node_type: str,
    limit: int = 50,
    commit_hash: str = "",
) -> str:
    """按类型列出代码符号

    列出项目中指定类型的所有符号（如所有 route、所有 class）。

    Args:
        project_identifier: 项目标识符
        node_type: 节点类型（route/tool/process/class/function/method/file）
        limit: 最大返回数
        commit_hash: 可选，指定 commit 版本

    Returns:
        符号列表
    """
    repo_path = await _get_repo_path(project_identifier)
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search_by_type(
            repo_path, node_type, limit=limit,
            commit_hash=commit_hash if commit_hash else None,
        )

        if not results:
            return f"未找到类型为 '{node_type}' 的符号"

        lines = [f"类型 '{node_type}' 的符号 ({len(results)} 个):\n"]
        for r in results:
            loc = f"{r.file_path}" if r.file_path else "?"
            if r.start_line:
                loc += f"#{r.start_line}"
            lines.append(f"  - {r.name:40} {loc}")

        return "\n".join(lines)


# ── Tool 9: 执行流查询 ─────────────────────────────────────────────────


@tool
async def kg_get_processes(
    project_identifier: str,
    limit: int = 20,
    commit_hash: str = "",
) -> str:
    """获取项目的执行流（业务流程）列表

    执行流是由多个函数调用组成的完整业务流程。

    Args:
        project_identifier: 项目标识符
        limit: 最大返回数
        commit_hash: 可选，指定 commit 版本

    Returns:
        执行流列表
    """
    repo_path = await _get_repo_path(project_identifier)
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search_by_type(
            repo_path, "process", limit=limit,
            commit_hash=commit_hash if commit_hash else None,
        )

        if not results:
            return "未找到执行流（process 类型节点）"

        lines = [f"执行流列表 ({len(results)} 个):\n"]
        for r in results:
            props = r.properties or {}
            step_count = props.get("step_count", "?")
            entry = props.get("entry_point_id", "?")
            lines.append(f"  📋 {r.name}")
            lines.append(f"     步骤数: {step_count}  入口: {entry}")

        return "\n".join(lines)
