# -*- coding: utf-8 -*-
# @Author  : 柚一
# @File    : CaseParser.py
# https://pypi.tuna.tsinghua.edu.cn/simple/
# 项目地址可能发生变化，测试数据如果太多可能随时还原。 碰到地址打不开，报错等等情况，联系班主任老师及时反馈
import os.path

from HAT.parse.ExcelCaseParser import excel_case_parser
from HAT.parse.YamlCaseParser import yaml_case_parser


# 用例解析器
# if传过来的是yaml 调yaml_case_parser  if传过来的excel 调excel_case_parser

def case_parser(case_type,case_dir):
    """
    :param case_type: 用例类型 传yaml,excel
    :param case_dir: 用例路径
    :return:
    """
    # 用例路径
    config_path=os.path.abspath(case_dir)
    if case_type=='yaml':
        return yaml_case_parser(config_path)
    if case_type=='excel':
        return excel_case_parser(config_path)
    return {"case_name":[],"case_info":[]}

if __name__ == '__main__':
    print(case_parser('yaml',r'../../examples/api-cases-yaml/'))