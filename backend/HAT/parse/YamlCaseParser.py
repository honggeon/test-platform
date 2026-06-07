import copy
import os.path
import uuid

import yaml

from HAT.core.globalContext import g_context
from HAT.utils.key_dir import merge_case_key_dir


def readYaml(file_path):
    case_info=[]
    with open(file_path,'r',encoding='utf-8') as f:
        # yaml.load读取   Loader=yaml.FullLoader 安全读取
        data=yaml.load(f,Loader=yaml.FullLoader)
    case_info.append(data)
    return case_info


# 专门读取context.yaml文件数据
def load_context_from_yaml(file_path):
    """
    :param file_path: 目录文件夹
    :return:
    """
    yaml_file_path=os.path.join(file_path, 'context.yaml')
    with open(yaml_file_path, 'r', encoding='utf-8') as file:
        data = yaml.load(file, Loader=yaml.FullLoader)
        if data:
            local_key_dir = data.pop("key_dir", None)
            g_context().set_by_dict(data)
            merge_case_key_dir(file_path, local_key_dir)
        # print("全局变量", g_context().show_dict())


# 读取文件夹下的yaml文件
def load_yaml_files(file_path):
    yaml_caseInfos=[]
    # 扫描用例文件夹
    suite_folder=os.path.join(file_path)
    # context.yaml放到全局变量中，后续用例可能用到全局变量的值
    load_context_from_yaml(suite_folder)
    file_names= [(int(f.split("_")[0]), f) for f in os.listdir(suite_folder)
                 if f.endswith('.yaml') and f.split("_")[0].isdigit()]
    # print("符合规则的文件读取出来",file_names)
    file_names.sort()#排序
    file_names=[f[-1] for f in file_names]
    print("排序后的文件列表",file_names)
    # 读取符合规则的文件数据
    for file_name in file_names:
        file_path=os.path.join(suite_folder, file_name)
        with open(file_path, 'r', encoding='utf-8')as file:
            caseinfo=yaml.full_load(file)
            yaml_caseInfos.append(caseinfo)
    return yaml_caseInfos

# 解析yaml文件中的ddt数据驱动，有几个ddt就分解成几条用例
def yaml_case_parser(file_path):
    case_infos=[]
    case_names=[]
    # 符合规则的yaml文件数据都读取出来
    yaml_caseInfos=load_yaml_files(file_path)
    # print("符合规则的yaml数据",yaml_caseInfos)

    for caseinfo in yaml_caseInfos:
        # print("用例数据",caseinfo)
        # 拿到文件中的数据驱动数据
        ddts=caseinfo.get("数据驱动",[])

        # 如果用例中有ddts数据驱动  模板  拿到数据驱动数据
        # 如果用例中没有ddts数据驱动  正常的把用例数据放在列表中，用例名称放在列表中
        if len(ddts)==0:
            case_name=caseinfo.get("基础配置").get("用例标题",uuid.uuid4().__str__())
            case_names.append(case_name)#用例名称放在列表中
            case_infos.append(caseinfo)#用例数据放在列表中  购物车的用例正常的放名称和用例数据
        else:
            caseinfo.pop("数据驱动")#只剩下用例模板  理解1   不理解2
            for ddt in ddts:
                new_case=copy.deepcopy(caseinfo)#复制用例模板
                new_case.update({"local_context":ddt})
                # print("用例数据", new_case)  登录用例标题-正确用户名和密码  登录用例标题-错误用户名和密码
                case_name = caseinfo.get("基础配置").get("用例标题", uuid.uuid4().__str__())
                case_name = f'{case_name}-{ddt.get("描述标题", uuid.uuid4().__str__())}'
                case_names.append(case_name)#用例名称放在列表中
                case_infos.append(new_case)#用例数据放在列表中
    return {
        "case_infos":case_infos,
        "case_names":case_names
    }

if __name__ == '__main__':
    # ./当前目录  ../上一级目录  ../../上上级目录  /n /t  r防止转义
    # data=readYaml(r'../../examples/api-cases-yaml/login.yaml')
    # print('返回结果',data)

    # load_context_from_yaml(r'../../examples/api-cases-yaml/')

    # c=load_yaml_files(r'../../examples/api-cases-yaml/')
    # print("符合规则的yaml数据",c)

    d=yaml_case_parser(r'../../examples/api-cases-yaml/')
    print("解析后的数据",d)
