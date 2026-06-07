# 全局变量的类

class g_context:
    _dic={}  #设置了一个类变量

    # g_context().set_dict('name','ALice')  _dic={"name":"ALice"}
    # 添加字典值
    def set_dict(self,key,value):
        self._dic[key]=value

    # dic 完整的字典   g_context().set_by_dict({"age":"18"})  _dic={"name":"ALice","age":"18"}
    def set_by_dict(self,dic):
        self._dic.update(dic)

    # 得到字典值  g_context().get_dict("age")
    def get_dict(self,key):
        return self._dic.get(key,None)

    # _dic={"name":"ALice","age":"18"}  g_context().show_dict()
    def show_dict(self):
        return self._dic