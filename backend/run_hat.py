#!/usr/bin/env python3
"""
HAT 框架测试执行入口脚本

用法:
    python run_hat.py --cases=<cases_dir> --type=yaml --keyDir=<key_dir> [pytest_args...]
"""
import sys
import os

# 确保 backend 在路径中
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import pytest


def main():
    args = sys.argv[1:]

    # 如果没有指定 TestRunner.py，自动添加
    has_testrunner = any("TestRunner.py" in arg for arg in args)
    if not has_testrunner:
        testrunner_path = os.path.join(backend_dir, "HAT", "core", "TestRunner.py")
        args.append(testrunner_path)

    # 确保有 allure 报告目录
    if "--alluredir" not in " ".join(args):
        args.extend(["--alluredir", "allure-results"])

    # 执行 pytest（backend/conftest.py 会自动加载 HAT 插件）
    exit_code = pytest.main(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
