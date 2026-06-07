"""代码仓库路径识别（跨平台）"""

from app.services.code_repo_service import _is_local_path, _is_git_url, _normalize_local_path


def test_is_git_url():
    assert _is_git_url("https://github.com/org/repo.git")
    assert _is_git_url("git@github.com:org/repo.git")
    assert not _is_git_url("D:\\projects\\repo")


def test_is_local_path_unix():
    assert _is_local_path("/home/user/project")
    assert _is_local_path("~/projects/repo")
    assert _is_local_path("./relative/path")


def test_is_local_path_windows():
    assert _is_local_path(r"D:\D\test-platform")
    assert _is_local_path("D:/D/test-platform")
    assert _is_local_path(r"C:\Users\Administrator\project")
    assert _is_local_path(r"\\server\share\repo")


def test_is_local_path_rejects_git_urls():
    assert not _is_local_path("https://github.com/org/repo.git")


def test_normalize_local_path_windows():
    normalized = _normalize_local_path(r"D:\D\test-platform")
    assert normalized == _normalize_local_path("D:/D/test-platform")
    assert normalized.endswith("test-platform")
