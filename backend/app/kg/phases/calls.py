"""
调用关系分析管道阶段
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from app.kg.types import PhaseProgress, REL_CALLS
from app.kg.phases.call_processor import CallAnalyzer

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


def calls_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase 4: 函数调用关系分析"""
    _report(on_progress, "calls", 0, "分析函数调用关系...")

    analyzer = CallAnalyzer()
    total_calls = 0
    analyzable_count = 0
    total_files = len(output.scan_results)

    for idx, scan_result in enumerate(output.scan_results):
        ext = scan_result.extension
        if ext not in (".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs",
                       ".ts", ".tsx", ".mts", ".cts"):
            continue

        analyzable_count += 1

        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        # 分析调用
        calls = analyzer.analyze_file(
            scan_result.file_path, source, output.graph,
        )

        # 添加 CALLS 关系到图
        for item in calls:
            if len(item) == 4:
                caller_id, callee_id, props, confidence = item
            else:
                caller_id, callee_id, props = item
                confidence = "unknown"

            rel_id = f"calls:{caller_id}->{callee_id}"
            rel = output.graph.get_node(caller_id)
            if rel is None:
                continue  # 调用者不在图中，跳过

            if output.graph.get_node(callee_id) is None:
                continue  # 被调用者不在图中，跳过

            from app.kg.types import GraphRelationship
            output.graph.add_relationship(GraphRelationship(
                id=rel_id,
                source_id=caller_id,
                target_id=callee_id,
                type=REL_CALLS,
                properties={"call_site": props, "confidence": confidence},
            ))
            total_calls += 1

        if (idx + 1) % max(1, total_files // 10) == 0:
            pct = int((idx + 1) / total_files * 100)
            _report(on_progress, "calls", pct,
                    f"调用分析: {idx + 1}/{total_files} 文件")

    output.stats["calls_resolved"] = total_calls

    _report(on_progress, "calls", 100,
            f"调用关系: {total_calls} 条")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
