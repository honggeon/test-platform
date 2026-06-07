def exec_script(script, context):
    """
    执行脚本
    :param script: 前置脚本
    :param context: 上下文，全局变量
    :return:
    """
    # 如果前置脚本为空 直接return
    if script is None: return
    exec(script, {"context": context})
    # exec 让字符串变成代码并且执行
    # exec 第个参数是 字符串的python代码
    # 第二个参数是全局变量字典  "context"随意变化 a,b