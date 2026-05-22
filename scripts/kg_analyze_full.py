#!/usr/bin/env python3
"""分析代码仓库并持久化到数据库。用法: python kg_analyze_full.py /path/to/repo"""
import asyncio, sys
from pathlib import Path

# 确保 backend 在路径中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.kg.pipeline import run_pipeline_from_repo
from app.kg.persistence import GraphPersistence, ensure_indexes
from app.config.database import async_session_factory


async def main(repo_path: str) -> None:
    output = run_pipeline_from_repo(repo_path)
    print(f"Graph: {output.graph.node_count} nodes, {output.graph.relationship_count} rels")
    async with async_session_factory() as s:
        await ensure_indexes(s)
        p = GraphPersistence(s)
        import subprocess, os
        try:
            result = subprocess.run(
                ["git", "-C", repo_path, "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            commit_hash = result.stdout.strip()
        except Exception:
            commit_hash = "unknown"
        stats = await p.save_graph(repo_path, commit_hash, output.graph)
        print(f"OK: {stats['nodes_written']} nodes written, {stats['relationships_written']} rels written")


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    asyncio.run(main(repo))
