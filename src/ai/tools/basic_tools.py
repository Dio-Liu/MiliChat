"""基础工具集 - 提供时间、日期等基本功能"""
import datetime
from src.ai.tools_manager import tool_manager


@tool_manager.register(
    name="get_current_time", 
    description="获取当前的系统时间和日期。当用户询问时间、几点了、今天星期几、日期等问题时使用此工具。"
)
def get_current_time():
    """
    获取当前系统时间
    
    Returns:
        str: 格式化的当前时间字符串，包含日期、时间和星期
    """
    now = datetime.datetime.now()
    weekday_map = {
        0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四",
        4: "星期五", 5: "星期六", 6: "星期日"
    }
    weekday = weekday_map[now.weekday()]
    
    # 返回易读的格式
    time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
    return f"{time_str} {weekday}"


# ========================================
# 以下是可扩展的工具示例（暂时注释）
# ========================================

# @tool_manager.register(
#     name="calculate", 
#     description="执行数学计算。当用户需要计算加减乘除等数学运算时使用。"
# )
# def calculate(expression: str):
#     """
#     安全地执行数学表达式计算
#     
#     Args:
#         expression: 数学表达式字符串，如 "2+2" 或 "3*7"
#     
#     Returns:
#         计算结果
#     """
#     try:
#         # 注意：实际使用时应该使用更安全的表达式解析器
#         # 这里仅作示例
#         result = eval(expression, {"__builtins__": {}}, {})
#         return f"计算结果: {result}"
#     except Exception as e:
#         return f"计算错误: {str(e)}"


# @tool_manager.register(
#     name="get_weather",
#     description="查询指定城市的天气信息。当用户询问天气情况时使用。"
# )
# def get_weather(city: str):
#     """
#     查询天气（示例）
#     
#     Args:
#         city: 城市名称
#     
#     Returns:
#         天气信息
#     """
#     # 这里可以接入真实的天气 API
#     return f"{city}的天气：晴朗，温度 25℃"
