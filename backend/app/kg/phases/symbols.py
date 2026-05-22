"""
符号提取 + Import 关系管道阶段

将符号提取器和 import 处理器整合为 pipeline phase。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from app.kg.types import PhaseProgress
from app.kg.phases.symbol_extractor import SymbolExtractor
from app.kg.phases.import_processor import ImportResolver

if TYPE_CHECKING:
    from app.kg.pipeline import PipelineOutput


def symbols_and_imports_phase(
    output: PipelineOutput,
    repo_path: str,
    on_progress: Optional[Callable[[PhaseProgress], None]] = None,
) -> None:
    """Phase 3: 符号提取 + Import 关系

    对每个可分析的文件：
    1. 读取源码
    2. 提取符号（类、函数、变量等）
    3. 生成 DEFINED_IN 关系
    4. 收集 import 信息

    然后：
    5. 跨文件解析 import → 生成 IMPORTS 关系
    """
    _report(on_progress, "symbols", 0, "提取代码符号...")

    extractor = SymbolExtractor()
    all_imports: list[tuple[str, list[tuple[str, str]]]] = []
    total_files = len(output.scan_results)

    for idx, scan_result in enumerate(output.scan_results):
        file_path = scan_result.file_path
        ext = scan_result.extension

        # 只分析可分析的文件
        if ext not in (".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs",
                       ".ts", ".tsx", ".mts", ".cts"):
            continue

        try:
            with open(scan_result.absolute_path, "r",
                      encoding="utf-8", errors="replace") as f:
                source = f.read()
        except (IOError, OSError):
            continue

        extraction = extractor.extract(file_path, source)

        # 添加符号节点到图
        for symbol in extraction.symbols:
            output.graph.add_node(symbol)

        # 添加 DEFINED_IN 关系
        for rel in extraction.relationships:
            output.graph.add_relationship(rel)

        # 收集 import 信息
        if extraction.imports:
            all_imports.append((file_path, extraction.imports))

        # 报告进度
        if (idx + 1) % max(1, total_files // 10) == 0:
            pct = int((idx + 1) / total_files * 80)
            _report(on_progress, "symbols", pct,
                    f"符号提取: {idx + 1}/{total_files} 文件")

    # ── 解析 import 关系 ─────────────────────────────────
    _report(on_progress, "symbols", 85, "解析 import 依赖关系...")

    # 收集所有文件路径
    all_files = {r.file_path for r in output.scan_results}
    resolver = ImportResolver(repo_path, all_files)

    import_count = 0
    for source_file, imports in all_imports:
        rels = resolver.resolve_imports(source_file, imports)
        for rel in rels:
            output.graph.add_relationship(rel)
            import_count += 1

    output.stats["symbols_extracted"] = output.graph.node_count - output.stats.get("files", 0) - output.stats.get("folders", 0)
    output.stats["imports_resolved"] = import_count

    _report(on_progress, "symbols", 100,
            f"符号: {output.stats['symbols_extracted']} 个, "
            f"import: {import_count} 条")


def _report(callback, phase, percent, message=""):
    if callback:
        callback(PhaseProgress(phase=phase, percent=percent, message=message))
