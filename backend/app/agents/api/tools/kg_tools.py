"""
知识图谱 Agent 工具

为 AI Agent 提供代码搜索、符号上下文查询、影响分析能力。
这些工具让 Agent 在生成测试用例时能理解被测代码的结构。
"""

import json
from langchain_core.tools import tool

from app.config.database import async_session_factory
from app.services.code_repo_service import CodeRepoService
from app.kg.search import CodeSearcher


@tool
async def kg_search_code(
    project_identifier: str,
    query: str,
    node_type: str = "",
    limit: int = 10,
) -> str:
    """搜索代码知识图谱，查找匹配的代码符号

    在项目的代码知识图谱中搜索类、函数、变量等符号。
    Agent 在需要了解被测项目代码结构时使用此工具。

    Args:
        project_identifier: 项目标识符 (如 "PR-1")
        query: 搜索关键词（类名、函数名、概念名）
        node_type: 过滤类型（class/function/method/variable/file，留空搜索全部）
        limit: 最大返回数（默认 10，最大 30）

    Returns:
        格式化的搜索结果列表
    """
    async with async_session_factory() as session:
        # 获取仓库路径
        repo_service = CodeRepoService(session)
        project = await repo_service.get_project(project_identifier)
        if not project.code_repo_path:
            return f"项目 {project_identifier} 未配置代码仓库路径"

        # 搜索
        searcher = CodeSearcher(session)
        results = await searcher.search(
            project.code_repo_path,
            query,
            node_type=node_type if node_type else None,
            limit=min(limit, 30),
        )

        if not results:
            return f"未找到匹配 '{query}' 的符号"

        lines = [f"找到 {len(results)} 个匹配 '{query}' 的符号:\n"]
        for r in results:
            loc = f"{r.file_path}" if r.file_path else "?"
            if r.start_line:
                loc += f"#{r.start_line}"
            lines.append(f"  [{r.type:8}] {r.name:40} ({loc})")

        return "\n".join(lines)


@tool
async def kg_get_symbol_context(
    project_identifier: str,
    symbol_name: str,
) -> str:
    """获取代码符号的详细信息

    查询某个代码符号（类、函数、变量）的定义位置、调用关系和源码片段。
    Agent 需要了解某个函数/类的实现细节时使用。

    Args:
        project_identifier: 项目标识符
        symbol_name: 符号名称（精确匹配或模糊匹配）

    Returns:
        符号的详细信息（定义位置、调用者、被调用者、源码）
    """
    async with async_session_factory() as session:
        repo_service = CodeRepoService(session)
        project = await repo_service.get_project(project_identifier)
        if not project.code_repo_path:
            return "项目未配置代码仓库路径"

        searcher = CodeSearcher(session)

        # 搜索符号
        results = await searcher.search(
            project.code_repo_path, symbol_name, limit=5
        )
        exact = [r for r in results if r.name == symbol_name]
        target = exact[0] if exact else (results[0] if results else None)

        if not target:
            return f"未找到符号: {symbol_name}"

        ctx = await searcher.get_node_context(
            project.code_repo_path, target.node_id
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

        if callers:
            lines.append(f"\n调用者 ({len(callers)} 处):")
            for r in callers[:8]:
                name = r["source"].split("::")[-1] if "::" in r["source"] else r["source"]
                lines.append(f"  ← {name}")
            if len(callers) > 8:
                lines.append(f"  ... 还有 {len(callers) - 8} 个")

        if callees:
            lines.append(f"\n依赖的函数 ({len(callees)} 处):")
            for r in callees[:8]:
                name = r["target"].split("::")[-1] if "::" in r["target"] else r["target"]
                lines.append(f"  → {name}")
            if len(callees) > 8:
                lines.append(f"  ... 还有 {len(callees) - 8} 个")

        # 源码片段
        if source:
            lines.append(f"\n源码片段 ({source['start_line']}-{source['end_line']} 行):")
            snippet_lines = source["content"].split("\n")
            for i, line in enumerate(snippet_lines[:20],
                                     start=source["start_line"]):
                lines.append(f"  {i:4}| {line}")
            if len(snippet_lines) > 20:
                lines.append("  ... (截断)")

        return "\n".join(lines)


@tool
async def kg_impact_analysis(
    project_identifier: str,
    symbol_name: str,
    direction: str = "upstream",
) -> str:
    """分析修改某代码符号的影响范围

    分析修改一个函数/类/变量会影响到哪些代码。
    Agent 在需要评估修改影响时使用此工具。

    Args:
        project_identifier: 项目标识符
        symbol_name: 要分析的符号名称
        direction: 分析方向
                   "upstream" - 谁调用了它（修改会影响调用者）
                   "downstream" - 它调用了谁（修改受被调用者影响）
                   "both" - 双向分析

    Returns:
        影响分析报告
    """
    async with async_session_factory() as session:
        repo_service = CodeRepoService(session)
        project = await repo_service.get_project(project_identifier)
        if not project.code_repo_path:
            return "项目未配置代码仓库路径"

        searcher = CodeSearcher(session)
        results = await searcher.search(
            project.code_repo_path, symbol_name, limit=3
        )
        exact = [r for r in results if r.name == symbol_name]
        target = exact[0] if exact else (results[0] if results else None)

        if not target:
            return f"未找到符号: {symbol_name}"

        ctx = await searcher.get_node_context(
            project.code_repo_path, target.node_id
        )
        if not ctx:
            return f"未找到符号 '{symbol_name}' 的详情"

        rels = ctx["relationships"]
        node = ctx["node"]

        lines = [
            f"═ 影响分析: {node['name']} ═",
            f"位置: {node.get('file_path', '?')}#{node.get('start_line', '?')}",
        ]

        if direction in ("upstream", "both"):
            callers = [r for r in rels if r["type"] == "CALLS" and r["target"] == node["id"]]
            lines.append(f"\n■ 上游影响 (谁调用了 {node['name']}): {len(callers)} 处")
            for r in callers[:12]:
                name = r["source"].split("::")[-1]
                lines.append(f"  ● {name}")
            if len(callers) > 12:
                lines.append(f"  ... 还有 {len(callers) - 12} 个")

        if direction in ("downstream", "both"):
            callees = [r for r in rels if r["type"] == "CALLS" and r["source"] == node["id"]]
            lines.append(f"\n■ 下游依赖 ({node['name']} 调用了哪些): {len(callees)} 处")
            for r in callees[:12]:
                name = r["target"].split("::")[-1]
                lines.append(f"  → {name}")
            if len(callees) > 12:
                lines.append(f"  ... 还有 {len(callees) - 12} 个")

        total_callers = len([r for r in rels if r["type"] == "CALLS" and r["target"] == node["id"]])
        if total_callers > 20:
            risk = "高风险: 被大量代码引用，修改可能产生广泛影响"
        elif total_callers > 5:
            risk = "中风险: 有多个调用者，修改前建议审查"
        elif total_callers > 0:
            risk = "低风险: 引用较少"
        else:
            risk = "无风险: 没有直接调用者"

        lines.append(f"\n■ 风险评级: {risk}")
        return "\n".join(lines)
