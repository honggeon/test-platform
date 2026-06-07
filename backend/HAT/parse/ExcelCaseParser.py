import ast
import json
import os
import re
import uuid

import pandas as pd
import yaml

from HAT.core.globalContext import g_context


# 专门处理数据库数据的数据
def load_dbinfo(name, all_sheets):
    #数据库配置的数据转成字典列表的数据
    db_config=all_sheets.fillna("").to_dict(orient='records')
    # print("数据库配置的数据转成字典列表的数据",db_config)

    config_dict={}
    # {"mysql001:{xxxx}","mysql002:{xxxx}","dsw:{xxxx}"}
    for item in db_config:
        db_info={}
        db_name=item.get('别名')# mysql001   mysql002   dsw_mysql
        host=item.get('服务器IP')
        port=item.get('端口号')
        user=item.get('用户名')
        password=item.get('密码')
        db=item.get('数据库名称')
        # print("数据库配置的数据",db_name,host,port,user,password,db)

        db_info.update({"host":host})
        db_info.update({"port":port})
        db_info.update({"user":user})
        db_info.update({"password":password})
        db_info.update({"db":db})
        # print("数据库信息",db_info)
        config_dict[db_name]=db_info
    # print("数据库配置的数据",config_dict)
    return config_dict

# 专门读取通用配置
def load_configuration(name, all_sheets):
    config_dict={row['配置名']:row['配置值']for _,row in all_sheets.iterrows()}
    # print("通用配置的数据",config_dict)

    for key,value in config_dict.items():
        config_dict[key]=safe_convert_value(value)
    # print("通用配置的数据",config_dict)
    return config_dict
# 专门读取context.xlsx文件数据
def load_context_from_excel(file_path):
    """
    :param file_path: 目录文件夹
    :return:
    """
    try:
        context_data={}

        excel_file_path=os.path.join(file_path, 'context.xlsx')
        # print('读取excel路径',excel_file_path)

        #读取数据  先处理数据库的数据设置成和yaml一样的格式
        all_sheets=pd.read_excel(excel_file_path,sheet_name='数据库配置')
        config_dict=load_dbinfo("数据库配置",all_sheets)
        context_data.update({"_数据库":config_dict})
        # print("数据库配置的数据",context_data)

        all_sheets = pd.read_excel(excel_file_path, sheet_name='通用配置')
        config_dict = load_configuration("通用配置", all_sheets)
        context_data.update(config_dict)
        # print("通用配置的数据",context_data)

        # 把数据放在全局变量中
        if context_data:g_context().set_by_dict(context_data)
    except Exception as e:
        print("读取context.xlsx文件数据异常",e)
        raise  e

def group_cases_by_title(data):
    result=[]#最终所有的用例返回在这个列表
    current_case = None #当前正在处理的用例
    # 循环用例数据
    for row in data:
        tilte=row.get("用例标题")
        module_1=row.get("模块")
        module_2=row.get("功能")
        case_type = row.get("用例类型")
        step_desc=row.get("测试步骤")
        action_type=row.get("操作类型")
        data_content=row.get("数据内容")
        # 需要进行处理  请求地址="http://shop-xo.hctestedu.com"  改成{"请求地址":"http://shop-xo.hctestedu.com"}

        data_content_dict = {}#空字典
        if data_content is not None and data_content!="":
            # 正则表达式
            pattern = r'(\w+)=(?:"([^"]*)"|(\S+))'
            matches = re.findall(pattern, data_content)
            # print("匹配结果",matches)
            #[('请求地址', 'http://shop-xo.hctestedu.com', ''), ('请求数据', '', '{"accounts":"youyi","pwd":"123456","type":"username"}'), ('URL参数', '', '{"s":"/api/user/login","application":"app"}')]

            # key 字段名  请求地址  请求数据
            # quoted_value 带引号的值 "http://shop-xo.hctestedu.com"
            # unquted_value 不带引号的值 {"accounts":"youyi","pwd":"123456","type":"username"}
            for key,quoted_value,unquoted_value in matches:
                value = quoted_value if quoted_value else unquoted_value
                if value is not None:
                    # {'请求地址': http://shop-xo.hctestedu.com}
                    data_content_dict[key]=safe_convert_value(value)
                else:
                    data_content_dict[key]=None


        if tilte is not None and tilte !="":
            if current_case is not None:
                result.append(current_case)
            current_case={"基础配置":{},"用例步骤":[]}
            current_case["基础配置"].update({"用例类型":case_type})
            current_case["基础配置"].update({"用例标题":tilte})
            current_case["基础配置"].update({"一级模块":module_1})
            current_case["基础配置"].update({"二级模块":module_2})
        if current_case is not None:
            current_case["用例步骤"].append({
                step_desc:{
                    "操作类型":action_type,
                    **data_content_dict
                }
            })
        # print("正在处理的用例",current_case)
    if current_case is not None:
        result.append(current_case)
    # print("最终结果",result)
    return result
# 转换数据类型
def safe_convert_value(value_str):
    # 先检查输入类型，如果不是字符串就先转换成字符串
    if not isinstance(value_str, str):
        # 如果是数字、布尔值等非字符串类型，直接返回原值
        if isinstance(value_str, (int, float, bool)) or value_str is None:
            return value_str
        # 其他类型尝试转换成字符串处理
        value_str = str(value_str)

    # 使用 .strip() 方法去除字符串两端的空白字符
    value_str = value_str.strip()

    # 先尝试 JSON 解析（支持 true/false）
    try:
        return json.loads(value_str)
    except json.JSONDecodeError:
        pass

    # 再尝试 Python 字面量解析（支持单引号）
    try:
        return ast.literal_eval(value_str)
    except (SyntaxError, ValueError):
        return value_str

def load_excel_files(config_path):
    excel_caseInfos=[]
    # 扫描用例文件夹
    suite_folder = os.path.join(config_path)
    load_context_from_excel(suite_folder)
    file_names = [(int(f.split("_")[0]), f) for f in os.listdir(suite_folder)
                  if f.endswith('.xlsx') and f.split("_")[0].isdigit()]
    # print("符合规则的文件读取出来",file_names)
    file_names.sort()  # 排序
    file_names = [f[-1] for f in file_names]
    # print("排序后的文件列表", file_names)
    for file_name in file_names:
        file_path=os.path.join(suite_folder, file_name)
        # 读取excel  pandas openpyxl 读取excel
        data=pd.read_excel(file_path,sheet_name=0)
        # print("用例数据",data)
        data=data.where(data.notnull(),None)#Nan填充None
        # print("用例数据", data)
        data=data.to_dict(orient='records')
        # print("用例数据", data)
        group_cases=group_cases_by_title(data)#专门用例数据的
        for case in group_cases:
            excel_caseInfos.append(case)
    return excel_caseInfos

def excel_case_parser(config_path):
    case_names=[]
    case_infos=[]
    # 符合excel用例数据都拿到
    excel_caseInfos=load_excel_files(config_path)
    for caseinfo in excel_caseInfos:
        case_name = caseinfo.get("基础配置").get("用例标题", uuid.uuid4().__str__())
        case_names.append(case_name)  # 用例名称放在列表中
        case_infos.append(caseinfo)  # 用例数据放在列表中  购物车的用例正常的放名称和用例数据
    return {
        "case_infos":case_infos,
        "case_names":case_names
    }


if __name__ == '__main__':
    load_context_from_excel(r'../../examples/api-cases-excel/')
    context_excel=g_context().show_dict()
    with open(r"./写入context数据.yaml",'w',encoding='utf-8')as file:
        yaml.dump(context_excel,file,allow_unicode=True,sort_keys= False)

    # all_excel_data=load_excel_files(r'../../examples/api-cases-excel/')
    # print("解析后的数据",all_excel_data)
    # # 确认  数据读取成和我们的yaml格式一致的  把数据写在yaml,看格式是不是一致 是一致就没问题  不是一致 就改
    # with open(r"./写入excel数据.yaml",'w',encoding='utf-8')as file:
    #     yaml.dump(all_excel_data,file,allow_unicode=True,sort_keys= False)
