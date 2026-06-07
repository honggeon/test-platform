'''
Author: hongge
Date: 2026-05-25 16:15:58
LastEditors: hongge
LastEditTime: 2026-06-04 22:40:00
FilePath: /ai-test-agent-system-platform/backend/HAT/utils/VarRender.py
Description
Version: 0.1
'''
from __future__ import annotations

import random
import re
import string
import uuid

from jinja2 import Template

_RANDOM_UUID_PATTERN = re.compile(r"\{\{\s*\$random_uuid\s*\}\}")
_RANDOM_ALPHABETIC_PATTERN = re.compile(
    r"\{\{\s*\$random\.alphabetic\((\d+)\)\s*\}\}"
)
_RANDOM_DIGITS_PATTERN = re.compile(r"\{\{\s*(\d+)_random_digits\s*\}\}")


def _random_alphabetic(length: int) -> str:
    return "".join(random.choices(string.ascii_letters, k=length))


def _random_digits(length: int) -> str:
    return "".join(random.choices(string.digits, k=length))


def preprocess_random_tokens(text: str) -> str:
    """将 Postman 风格随机占位符替换为字面量，避免 Jinja2 解析失败。"""
    updated = _RANDOM_UUID_PATTERN.sub(lambda _: str(uuid.uuid4()), text)
    updated = _RANDOM_ALPHABETIC_PATTERN.sub(
        lambda match: _random_alphabetic(int(match.group(1))),
        updated,
    )
    updated = _RANDOM_DIGITS_PATTERN.sub(
        lambda match: _random_digits(int(match.group(1))),
        updated,
    )
    return updated


def refresh(target, context):
    """
    原理：字符串模板和字典来进行字符串的替换操作
    :param target: 目标字符串  需要有个字符串模板{{变量名}}  {"name":"{{name}}","age":18}
    :param context:  源字典  {"name":"张三","age":18,"sex":"女","class":["哈哈哈"，‘嘻嘻’]}
    :return:
    """
    if target is None:
        return None
    rendered = preprocess_random_tokens(str(target))
    return Template(rendered).render(context)


if __name__ == '__main__':
    target = {"name": "{{name}}", "age": 18}
    context = {"name": "张三", "age": 18, "sex": "女", "class": ["哈哈哈", '嘻嘻']}
    r = refresh(target, context)
    print("新数据", r)
