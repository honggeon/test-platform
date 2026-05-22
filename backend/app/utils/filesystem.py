"""
版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。

本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。

授权商业应用请联系微信：huice666
"""

from deepagents.backends import FilesystemBackend


class FixedFilesystemBackend(FilesystemBackend):
    """修复 Windows 路径分隔符问题的 FilesystemBackend

    在 Windows 上，ls_info 返回的路径可能混合了 / 和 \\ 分隔符。
    这个子类确保所有返回的路径都使用 POSIX 格式（只用 /）。
    """

    def ls_info(self, path: str) -> list:
        """列出目录内容，确保返回 POSIX 格式的路径"""
        results = super().ls_info(path)
        # 修复路径分隔符：将 \\ 替换为 /
        for item in results:
            if 'path' in item:
                # 将反斜杠替换为正斜杠，但保留开头的 /
                original = item['path']
                fixed = '/' + original.lstrip('/').replace('\\', '/')
                item['path'] = fixed
                # 调试日志
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[FixedFilesystemBackend] ls_info({path}): {repr(original)} -> {repr(fixed)}")
        return results
