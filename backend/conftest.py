"""
HAT 测试框架 conftest — 注册自定义命令行参数 --type / --cases / --keyDir
"""
import sys
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from HAT.core.globalContext import g_context
from HAT.parse.CaseParser import case_parser
from HAT.utils.key_dir import init_key_dirs_from_cli
from app.utils.test_environment_url import apply_hat_runtime_urls


def pytest_addoption(parser):
    """注册 HAT 自定义命令行参数"""
    parser.addoption("--type", action="store", help="测试用例类型 (yaml/excel)")
    parser.addoption("--cases", action="store", help="测试用例目录路径")
    parser.addoption("--keyDir", action="store", help="扩展关键字目录路径")


def pytest_generate_tests(metafunc):
    """参数化测试：从 YAML/Excel 用例目录加载测试数据"""
    case_type = metafunc.config.getoption("type")
    case_dir = metafunc.config.getoption("cases")
    key_dir = metafunc.config.getoption("keyDir")

    if not case_type or not case_dir:
        return  # 没有 HAT 参数时跳过，不影响普通 pytest 运行

    init_key_dirs_from_cli(key_dir)

    data = case_parser(case_type, case_dir)
    apply_hat_runtime_urls()

    if "caseinfo" in metafunc.fixturenames:
        metafunc.parametrize("caseinfo", data["case_infos"], ids=data["case_names"])


def pytest_collection_modifyitems(items):
    """解决中文显示乱码"""
    for item in items:
        item.name = item.name.encode("utf-8").decode("unicode_escape")
        item._nodeid = item.nodeid.encode("utf-8").decode("unicode_escape")
