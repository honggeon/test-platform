"""
知识图谱 CLI

用法:
    python -m app.kg.cli status [--repo PATH]
    python -m app.kg.cli list
    python -m app.kg.cli query <KEYWORD> [--repo PATH] [--mode fts|bm25|hybrid]
    python -m app.kg.cli analyze <REPO_PATH>
    python -m app.kg.cli context <SYMBOL> [--repo PATH]
    python -m app.kg.cli impact <SYMBOL> [--repo PATH]
    python -m app.kg.cli clean [--repo PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 将 backend 加入路径（直接运行时）
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config.database import async_session_factory, engine
from app.kg.staleness import StalenessDetector
from app.kg.persistence import GraphPersistence, KGCommit
from app.kg.search import CodeSearcher
from app.kg.pipeline import run_pipeline_from_repo
from sqlalchemy import select, func


async def cmd_status(repo_path: str | None) -> int:
    """查看索引状态"""
    async with async_session_factory() as session:
        if repo_path:
            # 查询指定仓库
            result = await session.execute(
                select(KGCommit)
                .where(KGCommit.repo_path == repo_path)
                .order_by(KGCommit.analyzed_at.desc())
                .limit(1)
            )
            commit = result.scalar_one_or_none()
            if not commit:
                print(f"❌ 仓库未索引: {repo_path}")
                return 1

            detector = StalenessDetector()
            report = detector.check(repo_path, commit.commit_hash)
            print(f"仓库: {repo_path}")
            print(f"索引版本: {commit.commit_hash[:8]}")
            print(f"当前 HEAD: {report.current_head[:8] if report.current_head else 'unknown'}")
            print(f"节点数: {commit.node_count}")
            print(f"关系数: {commit.rel_count}")
            print(f"分析时间: {commit.analyzed_at}")
            if report.is_stale:
                print(f"状态: ⚠️  {report.hint}")
            else:
                print(f"状态: ✅ {report.hint}")
        else:
            # 列出所有仓库状态
            result = await session.execute(
                select(KGCommit.repo_path, func.count(KGCommit.commit_hash))
                .group_by(KGCommit.repo_path)
                .order_by(func.max(KGCommit.analyzed_at).desc())
            )
            repos = result.all()
            if not repos:
                print("暂无已索引的仓库")
                return 0

            print(f"共 {len(repos)} 个已索引仓库:\n")
            detector = StalenessDetector()
            for repo_path, count in repos:
                latest_result = await session.execute(
                    select(KGCommit)
                    .where(KGCommit.repo_path == repo_path)
                    .order_by(KGCommit.analyzed_at.desc())
                    .limit(1)
                )
                latest = latest_result.scalar_one_or_none()
                report = detector.check(repo_path, latest.commit_hash)
                status_icon = "✅" if not report.is_stale else "⚠️"
                print(f"{status_icon} {repo_path}")
                print(f"   最新: {latest.commit_hash[:8]}, {count} 个版本")
                print(f"   规模: {latest.node_count} 节点 / {latest.rel_count} 关系")
                if report.is_stale:
                    print(f"   落后: {report.commits_behind} commits")
                print()
    return 0


async def cmd_list() -> int:
    """列出所有已索引仓库"""
    async with async_session_factory() as session:
        result = await session.execute(
            select(KGCommit.repo_path, func.count(KGCommit.commit_hash))
            .group_by(KGCommit.repo_path)
            .order_by(func.max(KGCommit.analyzed_at).desc())
        )
        repos = result.all()
        if not repos:
            print("暂无已索引的仓库")
            return 0

        print(f"共 {len(repos)} 个已索引仓库:\n")
        for repo_path, count in repos:
            latest_result = await session.execute(
                select(KGCommit)
                .where(KGCommit.repo_path == repo_path)
                .order_by(KGCommit.analyzed_at.desc())
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            short = latest.commit_hash[:8] if latest else "?"
            print(
                f"  {repo_path}\n"
                f"    最新: {short} ({count} 个版本)\n"
                f"    规模: {latest.node_count} 节点 / {latest.rel_count} 关系\n"
                f"    时间: {latest.analyzed_at}\n"
            )
    return 0


async def cmd_query(repo_path: str, keyword: str, mode: str, node_type: str | None, limit: int) -> int:
    """搜索代码符号"""
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search(repo_path, keyword, node_type=node_type, limit=limit, mode=mode)
        if not results:
            print(f"未找到匹配 '{keyword}' 的结果")
            return 0

        print(f"找到 {len(results)} 个匹配 '{keyword}' 的结果 (mode={mode}):\n")
        for r in results:
            loc = f"{r.file_path}" if r.file_path else ""
            if r.start_line:
                loc += f"#{r.start_line}"
            print(f"  [{r.type:10}] {r.name:40} {loc} (score={r.score:.1f})")
    return 0


async def cmd_analyze(repo_path: str) -> int:
    """分析仓库并保存到数据库"""
    from app.kg.persistence import ensure_indexes

    print(f"🔍 分析仓库: {repo_path}")
    output = run_pipeline_from_repo(repo_path)
    print(f"📊 Graph: {output.graph.node_count} 节点, {output.graph.relationship_count} 关系")

    async with async_session_factory() as session:
        await ensure_indexes(session)
        persister = GraphPersistence(session)

        import subprocess
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            commit_hash = result.stdout.strip()
        except Exception:
            commit_hash = "unknown"

        stats = await persister.save_graph(repo_path, commit_hash, output.graph)
        print(f"💾 已保存: {stats['nodes_written']} 节点, {stats['relationships_written']} 关系")
    return 0


async def cmd_context(repo_path: str, symbol: str) -> int:
    """获取符号上下文"""
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search(repo_path, symbol, limit=5)
        exact = [r for r in results if r.name == symbol]
        if not exact:
            if results:
                print(f"未找到精确匹配 '{symbol}'，相似结果:")
                for r in results[:5]:
                    print(f"  [{r.type}] {r.name}")
            else:
                print(f"未找到符号: {symbol}")
            return 1

        target = exact[0]
        ctx = await searcher.get_node_context(repo_path, target.node_id)
        if not ctx:
            print(f"未找到符号详情: {symbol}")
            return 1

        node = ctx["node"]
        rels = ctx["relationships"]
        source = ctx.get("source")

        print(f"符号: {node['name']}")
        print(f"类型: {node['type']}")
        print(f"位置: {node.get('file_path', '?')}#{node.get('start_line', '?')}")

        callers = [r for r in rels if r["type"] == "CALLS" and r["target"] == node["id"]]
        callees = [r for r in rels if r["type"] == "CALLS" and r["source"] == node["id"]]

        if callers:
            print(f"\n调用者 ({len(callers)}):")
            for r in callers[:10]:
                print(f"  ← {r['source'].split('::')[-1]}")

        if callees:
            print(f"\n被调用 ({len(callees)}):")
            for r in callees[:10]:
                print(f"  → {r['target'].split('::')[-1]}")

        if source:
            print(f"\n源码 ({source['start_line']}-{source['end_line']}行):")
            for i, line in enumerate(source["content"].split("\n")[:15], start=source["start_line"]):
                print(f"  {i:4}| {line}")
    return 0


async def cmd_impact(repo_path: str, symbol: str, max_depth: int) -> int:
    """影响分析"""
    async with async_session_factory() as session:
        searcher = CodeSearcher(session)
        results = await searcher.search(repo_path, symbol, limit=3)
        exact = [r for r in results if r.name == symbol]
        if not exact:
            print(f"未找到符号: {symbol}")
            return 1

        target = exact[0]
        ctx = await searcher.get_node_context(repo_path, target.node_id)
        if not ctx:
            print(f"未找到符号详情: {symbol}")
            return 1

        rels = ctx["relationships"]
        node = ctx["node"]

        callers = [r for r in rels if r["type"] == "CALLS" and r["target"] == node["id"]]
        callees = [r for r in rels if r["type"] == "CALLS" and r["source"] == node["id"]]

        print(f"═ 影响分析: {node['name']} ═")
        print(f"\n上游影响: {len(callers)} 处")
        for r in callers[:12]:
            print(f"  ● {r['source'].split('::')[-1]}")

        print(f"\n下游依赖: {len(callees)} 处")
        for r in callees[:12]:
            print(f"  → {r['target'].split('::')[-1]}")

        total = len(callers) + len(callees)
        risk = "高风险" if total > 50 else "中风险" if total > 10 else "低风险" if total > 0 else "无风险"
        print(f"\n风险评级: {risk} (共影响 {total} 处)")
    return 0


async def cmd_clean(repo_path: str | None) -> int:
    """清除索引"""
    async with async_session_factory() as session:
        persister = GraphPersistence(session)
        if repo_path:
            # 只清除指定仓库
            nodes_deleted = await persister.delete_repo(repo_path)
            print(f"🗑️  已清除仓库 {repo_path}: {nodes_deleted} 个节点")
        else:
            # 清除所有
            result = await session.execute(select(KGCommit.repo_path).distinct())
            repos = [r[0] for r in result.all()]
            total = 0
            for rp in repos:
                nodes_deleted = await persister.delete_repo(rp)
                total += nodes_deleted
                print(f"🗑️  已清除仓库 {rp}: {nodes_deleted} 个节点")
            print(f"\n总计清除: {total} 个节点")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="kg",
        description="知识图谱 CLI — 代码仓库分析与查询",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    status_parser = subparsers.add_parser("status", help="查看索引状态")
    status_parser.add_argument("--repo", default=".", help="仓库路径 (默认: .)")

    # list
    subparsers.add_parser("list", help="列出所有已索引仓库")

    # query
    query_parser = subparsers.add_parser("query", help="搜索代码符号")
    query_parser.add_argument("keyword", help="搜索关键词")
    query_parser.add_argument("--repo", default=".", help="仓库路径 (默认: .)")
    query_parser.add_argument("--mode", default="hybrid", choices=["fts", "bm25", "hybrid"],
                              help="搜索模式 (默认: hybrid)")
    query_parser.add_argument("--type", default=None, help="节点类型过滤")
    query_parser.add_argument("--limit", type=int, default=20, help="最大结果数")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="分析仓库并保存到数据库")
    analyze_parser.add_argument("repo_path", help="代码仓库路径")

    # context
    context_parser = subparsers.add_parser("context", help="获取符号上下文")
    context_parser.add_argument("symbol", help="符号名称")
    context_parser.add_argument("--repo", default=".", help="仓库路径 (默认: .)")

    # impact
    impact_parser = subparsers.add_parser("impact", help="影响分析")
    impact_parser.add_argument("symbol", help="符号名称")
    impact_parser.add_argument("--repo", default=".", help="仓库路径 (默认: .)")
    impact_parser.add_argument("--depth", type=int, default=3, help="遍历深度")

    # clean
    clean_parser = subparsers.add_parser("clean", help="清除索引")
    clean_parser.add_argument("--repo", default=None, help="仓库路径 (默认: 全部)")

    args = parser.parse_args()

    commands = {
        "status": lambda: cmd_status(args.repo),
        "list": lambda: cmd_list(),
        "query": lambda: cmd_query(args.repo, args.keyword, args.mode, args.type, args.limit),
        "analyze": lambda: cmd_analyze(args.repo_path),
        "context": lambda: cmd_context(args.repo, args.symbol),
        "impact": lambda: cmd_impact(args.repo, args.symbol, args.depth),
        "clean": lambda: cmd_clean(args.repo),
    }

    return asyncio.run(commands[args.command]())


if __name__ == "__main__":
    sys.exit(main())
