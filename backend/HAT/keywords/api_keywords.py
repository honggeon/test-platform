import base64
import os
import sys

import allure
import jsonpath
import pymysql
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from deepdiff import DeepDiff
from loguru import logger

LOGGER_INFO = logger.info("开始发请求")
from pymysql import cursors

from HAT.core.globalContext import g_context
from HAT.utils.key_dir import ensure_key_dirs_on_syspath, get_key_dirs


def _drop_empty_query_params(params):
    """Remove empty query values so optional UUID params are omitted, not sent as \"\"."""
    if params is None or not isinstance(params, dict):
        return params
    cleaned = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        cleaned[key] = value
    return cleaned if cleaned else None


def _normalize_compare_text(value):
    """Normalize text for stable cross-environment string comparison."""
    import unicodedata

    return unicodedata.normalize("NFKC", str(value))


def _resolve_request_url(url):
    """将 /api/v1/... 相对路径拼接到 g_context 中的 base URL。"""
    if url is None:
        return None
    text = str(url).strip()
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        for key in ("URL", "API_BASE_URL", "base_url"):
            base = g_context().get_dict(key)
            if not base:
                continue
            base_text = str(base).strip()
            if base_text.startswith(("http://", "https://")) and "{{" not in base_text:
                return f"{base_text.rstrip('/')}{text}"
    return text


# 接口请求进行二次封装
class Keywords:

    def __init__(self,request):
        #  self.request =requests
        #  self.request=requests.session() 接受到底是创建的一次会话requests.session() ，还是多个会话？requests.session()
        self.request=request

    @allure.step("发送请求POST")
    def 发送请求POST(self,**kwargs):
        self.show_log("请求参数", kwargs)
        url=_resolve_request_url(kwargs.get('请求地址',None))
        params=_drop_empty_query_params(kwargs.get('URL参数',None))
        headers=kwargs.get('请求头',None)
        data=kwargs.get('请求数据',None)
        files=kwargs.get('文件列表',[])
        data_type=kwargs.get('请求类型',"data").lower()#默认请求类型
        request_data={
            "url":url,
            "params":params,
            "headers":headers,
            "files":files,
        }
        # 如果json   request_data['json']= data
        if data_type=="json":
            request_data["json"]=data
        elif data_type=="data":  #request_data['json']= data
            request_data["data"]=data
        elif data_type=="files": # files
            if isinstance(data, dict):#判断字典
                files={}#{'image': open('login1.csv', 'rb')}
                for key,file_path in data.items():#image: "login1.csv"
                    files[key]=open(file_path,"rb")
                request_data["files"] = files#files={'image': open('login1.csv', 'rb')}
            else:
                file=open(data,"rb")
                request_data["files"] = {"file":file}

        else:
            raise Exception("请求类型错误")
        try:
            # self.request  必须是什么值才能发请求？  requests.request()   requests.session().request()
            response=self.request.request("post",**request_data)
            print("登陆响应数据",response.json())
            g_context().set_dict("响应结果",response)
            g_context().set_dict("status_code", str(response.status_code))
            self.show_log("响应数据", response.json())
            return response
            # 保存数据的逻辑  xxx
        except Exception as e:
            logger.error("发送请求有问题")
            raise



    @allure.step("发送请求GET")
    def 发送请求GET(self,**kwargs):
        url = _resolve_request_url(kwargs.get('请求地址', None))
        params = _drop_empty_query_params(kwargs.get('URL参数', None))
        headers = kwargs.get('请求头', None)
        data = kwargs.get('请求数据', None)
        files = kwargs.get('文件列表', [])
        request_data = {
            "url": url,
            "params": params,
            "headers": headers,
            "files": files,
        }
        response = self.request.request("get", **request_data)
        g_context().set_dict("响应结果", response)
        g_context().set_dict("status_code", str(response.status_code))
        # return response

    @allure.step("发送请求DELETE")
    def 发送请求DELETE(self, **kwargs):
        self.show_log("请求参数", kwargs)
        url = _resolve_request_url(kwargs.get("请求地址", None))
        params = _drop_empty_query_params(kwargs.get("URL参数", None))
        headers = kwargs.get("请求头", None)
        data = kwargs.get("请求数据", None)
        data_type = kwargs.get("请求类型", "data").lower()
        request_data = {
            "url": url,
            "params": params,
            "headers": headers,
        }
        if data is not None:
            if data_type == "json":
                request_data["json"] = data
            else:
                request_data["data"] = data
        try:
            response = self.request.request("delete", **request_data)
            g_context().set_dict("响应结果", response)
            g_context().set_dict("status_code", str(response.status_code))
            self.show_log("响应数据", response.text[:500] if response.text else "")
            return response
        except Exception:
            logger.error("发送请求有问题")
            raise

    @allure.step("发送请求PUT")
    def 发送请求PUT(self, **kwargs):
        self.show_log("请求参数", kwargs)
        url = _resolve_request_url(kwargs.get("请求地址", None))
        params = _drop_empty_query_params(kwargs.get("URL参数", None))
        headers = kwargs.get("请求头", None)
        data = kwargs.get("请求数据", None)
        data_type = kwargs.get("请求类型", "data").lower()
        request_data = {
            "url": url,
            "params": params,
            "headers": headers,
        }
        if data is not None:
            if data_type == "json":
                request_data["json"] = data
            else:
                request_data["data"] = data
        try:
            response = self.request.request("put", **request_data)
            g_context().set_dict("响应结果", response)
            g_context().set_dict("status_code", str(response.status_code))
            self.show_log("响应数据", response.text[:500] if response.text else "")
            return response
        except Exception:
            logger.error("发送请求有问题")
            raise

    @allure.step("发送请求PATCH")
    def 发送请求PATCH(self, **kwargs):
        self.show_log("请求参数", kwargs)
        url = _resolve_request_url(kwargs.get("请求地址", None))
        params = _drop_empty_query_params(kwargs.get("URL参数", None))
        headers = kwargs.get("请求头", None)
        data = kwargs.get("请求数据", None)
        data_type = kwargs.get("请求类型", "data").lower()
        request_data = {
            "url": url,
            "params": params,
            "headers": headers,
        }
        if data is not None:
            if data_type == "json":
                request_data["json"] = data
            else:
                request_data["data"] = data
        try:
            response = self.request.request("patch", **request_data)
            g_context().set_dict("响应结果", response)
            g_context().set_dict("status_code", str(response.status_code))
            self.show_log("响应数据", response.text[:500] if response.text else "")
            return response
        except Exception:
            logger.error("发送请求有问题")
            raise

    @allure.step("下载接口get")
    def 下载接口get(self, **kwargs):
        url = _resolve_request_url(kwargs.get('请求地址', None))
        params = _drop_empty_query_params(kwargs.get('URL参数', None))
        headers = kwargs.get('请求头', None)
        data = kwargs.get('请求数据', None)
        files = kwargs.get('文件列表', [])
        save_path=kwargs.get("保存路径")
        stream=kwargs.get("流式下载",False)
        chunk_size=kwargs.get("块大小",1024)
        request_data = {
            "url": url,
            "params": params,
            "headers": headers,
            "files": files,
            "stream":stream if save_path else False #需要保存文件的时候启用
        }
        response = self.request.request("get", **request_data)

        if save_path:
            os.makedirs(os.path.dirname(save_path),exist_ok=True)
            if stream:
                # 如果是大文件，把文件切割成小文件进行保存
                with open(save_path,"wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
            else:
                # 不是大文件就正常保存
                with open(save_path,"wb") as f:
                    f.write(response.content)
        return response

    @allure.step("提取数据JSON")
    def 提取数据JSON(self,**kwargs):
        self.show_log("提取数据JSON", kwargs)
        # 获取jsonpath表达式  $..msg  $..token
        EXPRESSION=kwargs.get("表达式",None)
        # 获取下标 不填下标就给你0  默认取第一个数据
        INDEX=kwargs.get("下标",None)
        if INDEX is None:
            INDEX=0

        response=g_context().get_dict("响应结果").json()
        print("json提取器",g_context().show_dict())
        result=jsonpath.jsonpath(response,EXPRESSION)
        if not result:
            if EXPRESSION and (".length(" in EXPRESSION or ".count(" in EXPRESSION):
                raise Exception(
                    f"jsonpath 不支持函数式语法: {EXPRESSION}，"
                    "请改用 $[0].field 或 $..field"
                )
            raise Exception(f"没有找到对应的数据:{EXPRESSION}")
        ex_data=result[INDEX]
        # 设置到全局变量中去  {"msg_token": '1a8080e503afb6a24e23396aa654cccb'}
        g_context().set_dict(kwargs["变量名"],ex_data)
        self.show_log("全局变量",g_context().show_dict())


    # assert 期望结果==实际结果，"错误时显示信息"
    def 断言文本(self,**kwargs):
        self.show_log("断言文本", kwargs)
        #比较器  预期结果和实际结果真实对比的地方
        comparators={
            "==":lambda a,b:a==b,
            ">=":lambda a,b:a>=b,
            "<=":lambda a,b:a<=b,
            "!=":lambda a,b:a!=b,
            ">":lambda a,b:a>b,
            "<":lambda a,b:a<b,
            "in":lambda a,b:a in b,
        }

        message=kwargs.get("错误信息",None) #用例中有没有传错误信息
        operators=kwargs.get("比较符","==")#用例中有没有传比较符 没有就默认==   <>
        compare_type=kwargs.get("断言类型","文本")#用例中有没有传断言类型 没有就默认文本

        # 如果传过来的比较符不在比较器里面，就报错
        if operators not in comparators:
            raise Exception(f"没有对应的比较符:{operators}")

        # 对于期望结果，如果是数字，就转换成数字类型，否则就转换成字符串类型
        if compare_type=="数字":
            kwargs["期望结果"]=float(kwargs["期望结果"])
        else:
            kwargs["期望结果"]=_normalize_compare_text(kwargs["期望结果"])
            kwargs["实际结果"]=_normalize_compare_text(kwargs["实际结果"])

        # == sj_msg,登陆成功   sj_msg==登陆成功 相等 True  不相等 False
        # if not True: ==if false 不执行下面的内容,，没有提示
        # if not False: ==if true 执行下面的内容
        if not comparators[operators](kwargs["实际结果"],kwargs["期望结果"]):
            if message:#如果有传错误信息 就用自定义错误信息
                raise Exception(message)
            else:#没有传错误信息 就用默认错误信息
                raise AssertionError(f"{kwargs['实际结果']} {operators} {kwargs['期望结果']}")

    def 断言文本相等(self,**kwargs):
        self.show_log("断言文本相等", kwargs)
        kwargs.update({"比较符":"=="})
        self.断言文本(**kwargs)

    def 断言文本包含(self, **kwargs):
        """actual in expected（子串在容器中）。"""
        kwargs.update({"比较符": "in"})
        self.断言文本(**kwargs)

    def 断言文本被包含(self, **kwargs):
        """expected in actual（直觉语义：完整字符串包含子串）。"""
        actual = kwargs.get("实际结果")
        expected = kwargs.get("期望结果")
        swapped = dict(kwargs)
        swapped["实际结果"] = expected
        swapped["期望结果"] = actual
        swapped.update({"比较符": "in"})
        self.断言文本(**swapped)

    def 断言文本不相等(self, **kwargs):
        kwargs.update({"比较符": "!="})
        self.断言文本(**kwargs)

    def 断言数字大于等于(self, **kwargs):
        kwargs.update({"比较符": ">=", "断言类型": "数字"})
        self.断言文本(**kwargs)

    def 断言数字小于等于(self, **kwargs):
        kwargs.update({"比较符": "<=", "断言类型": "数字"})
        self.断言文本(**kwargs)

    def 断言数字小于(self, **kwargs):
        kwargs.update({"比较符": "<", "断言类型": "数字"})
        self.断言文本(**kwargs)

    def 断言数字大于(self, **kwargs):
        kwargs.update({"比较符": ">", "断言类型": "数字"})
        self.断言文本(**kwargs)

    def 断言数字不等于(self, **kwargs):
        kwargs.update({"比较符": "!=", "断言类型": "数字"})
        self.断言文本(**kwargs)


    def 批量断言(self,**kwargs):
        try:
            sjmsg=g_context().get_dict("响应结果").json()#实际结果
            exmsg=kwargs["期望结果"]#预期结果

            exclude_paths=kwargs.get("过滤字段",[])
            ignore_order=kwargs.get("忽略顺序",True)
            ignore_string_case=kwargs.get("忽略大小写",True)

            screen_data={
                "exclude_paths":exclude_paths,
                "ignore_order":ignore_order,
                "ignore_string_case":ignore_string_case
            }
            diff=DeepDiff(sjmsg,exmsg,**screen_data)
        except Exception as e:
            assert False,f"批量断言失败:{e}"
        assert not diff,f"批量断言失败:{diff.pretty()}"


    # 连接数据库 才能去获取数据库数据
    def 提取数据MYSQL(self,**kwargs):
        # 从全局变量中拿数据,拿哪个数据，用例中填写哪个数据
        db_config = g_context().get_dict("_数据库")[kwargs["数据库"]]
        config={"cursorclass":cursors.DictCursor}
        #数据库信息放到字典中
        config.update(db_config)
        # 连接数据库
        connect=pymysql.connect(**config)

        # 生成游标
        cursor = connect.cursor()

        # 执行sql
        sql = kwargs["SQL"]
        cursor.execute(sql)

        # (游标)获得结果
        rs = cursor.fetchall()
        print('数据库结果', rs)

        # 关闭游标
        cursor.close()
        # 关闭数据库
        connect.close()

        # 保存我要的数据保存在变量中
        var_names=kwargs.get("变量名",[])
        result={}

        # 没有写变量名 id_1: 2  username_1: youyi  id_2: 2  username_2: youyi
        # 写了变量名  uid_1: 2  uname_1: youyi  uid_2: 2  uname_2: youyi
        # rs=[{'id': 2, 'username': 'youyi'}]
        if not var_names:#没有变量名
            # i 下标1，2  item  [{'id': 2, 'username': 'youyi'}]
            for i,item in enumerate(rs,start=1):
                for key,value in item.items():
                    # {id_1:2,username_1:youyi}
                    result[f"{key}_{i}"]=value
        else:
            # var_names 数量
            field_length=len(rs[0])if rs else 0
            #var_names和rs的数量不一致就报错
            if len(var_names)!=field_length:
                raise Exception(f"变量名数量和结果数量不一致:{var_names}")
            for idx,item in enumerate(rs,start=1):
                for col_idx,key in enumerate(item):
                    result[f"{var_names[col_idx]}_{idx}"] = item[key]
        g_context().set_by_dict(result)
        print("数据库结果保存在变量中",g_context().show_dict())


    def show_log(self,data_name,data=None):
        logger.debug(f"-------Log：{data_name}-----")
        logger.debug(f"{data_name}:{data}")
        logger.debug(f"-------END Log：{data_name}-----")

    def ex_invoke(self,  **kwargs):
        key = kwargs['key'] #做什么操作 发送请求 提取数据
        key_dirs = get_key_dirs()
        if not key_dirs:
            raise AttributeError(
                f"关键字 '{key}' 不存在，且未配置 key_dir。"
                f"请使用 deploy_hat_keyword 部署扩展，或将 {key}.py 放入 HAT/key_dir。"
            )

        ensure_key_dirs_on_syspath()
        last_error: Exception | None = None
        for key_dir in key_dirs:
            try:
                module = __import__(key)
                class_ = getattr(module, key)
                key_func = class_(self.request).__getattribute__(key)
                key_func(**kwargs['step_value'])
                return
            except (ModuleNotFoundError, AttributeError) as exc:
                last_error = exc
                continue

        searched = ", ".join(key_dirs)
        raise AttributeError(
            f"关键字 '{key}' 未找到。请在 key_dir 部署 {key}.py，"
            f"且文件名=类名=方法名={key}。"
            f"已搜索: {searched}"
        ) from last_error


    def 加密aes(self,**kwargs):
        key=b'1234567812345678'
        # aes需要字节数据
        data = kwargs["data"].encode('utf-8')
        # 加密 ECB
        cipher = AES.new(key, AES.MODE_ECB)
        # 填充
        ct_bytes = cipher.encrypt(pad(data, AES.block_size))
        ct = base64.b64encode(ct_bytes).decode('utf-8')
        # 加密好的数据放在全局变量
        g_context().set_dict(kwargs['VARNAME'],ct)
        print('全局变量是否有加密数据',g_context().show_dict())
