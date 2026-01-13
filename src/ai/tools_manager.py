"""工具管理器 - 负责注册、分发、执行工具"""
import json
import inspect
from functools import wraps
from typing import Callable, Dict, Any, List, Optional


class ToolManager:
    """工具管理器 - 使用装饰器模式注册和管理工具"""
    
    def __init__(self):
        # 存储工具的字典：name -> {func, schema}
        self.tools_map: Dict[str, Callable] = {}
        # 存储发给 LLM 的 schema 列表
        self.tools_schema: List[Dict[str, Any]] = []

    def register(self, name: str, description: str):
        """
        装饰器：用于注册工具
        
        Args:
            name: 工具名称 (LLM 看到的函数名)
            description: 工具描述 (告诉 LLM 什么时候使用这个工具，非常重要！)
        
        Example:
            @tool_manager.register("get_time", "获取当前系统时间")
            def get_current_time():
                return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        """
        def decorator(func: Callable) -> Callable:
            # 1. 自动分析函数参数，构建 JSON Schema
            sig = inspect.signature(func)
            parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            for param_name, param in sig.parameters.items():
                # 尝试从注解获取类型信息
                param_type = "string"  # 默认
                if param.annotation != inspect.Parameter.empty:
                    if param.annotation == int:
                        param_type = "integer"
                    elif param.annotation == float:
                        param_type = "number"
                    elif param.annotation == bool:
                        param_type = "boolean"
                
                parameters["properties"][param_name] = {
                    "type": param_type,
                    "description": f"Parameter {param_name}"
                }
                
                # 如果没有默认值，则为必需参数
                if param.default == inspect.Parameter.empty:
                    parameters["required"].append(param_name)

            # 2. 构建工具定义
            tool_def = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            }

            # 3. 存入注册表
            self.tools_map[name] = func
            self.tools_schema.append(tool_def)
            
            print(f"[OK] 已注册工具: {name}")
            
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator

    def get_tool_schemas(self) -> Optional[List[Dict[str, Any]]]:
        """
        返回给 OpenAI API 用的 tools 列表
        
        Returns:
            工具定义列表，如果没有工具则返回 None
        """
        return self.tools_schema if self.tools_schema else None

    def execute_tool(self, tool_name: str, arguments_json: str) -> str:
        """
        执行工具并返回结果
        
        Args:
            tool_name: 工具名称
            arguments_json: JSON 格式的参数字符串
            
        Returns:
            工具执行结果的 JSON 字符串
        """
        if tool_name not in self.tools_map:
            return json.dumps({"error": f"Tool {tool_name} not found."}, ensure_ascii=False)
        
        try:
            # 解析参数
            args = json.loads(arguments_json) if arguments_json else {}
            func = self.tools_map[tool_name]
            
            print(f"🔧 Agent 正在调用工具: {tool_name}")
            print(f"   参数: {args}")
            
            # 执行函数
            result = func(**args)
            
            print(f"   结果: {result}")
            
            # 返回 JSON 格式的结果
            if isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False)
            else:
                return json.dumps({"result": str(result)}, ensure_ascii=False)
                
        except Exception as e:
            error_msg = f"Error executing tool {tool_name}: {str(e)}"
            print(f"❌ {error_msg}")
            return json.dumps({"error": error_msg}, ensure_ascii=False)

    def list_tools(self) -> List[str]:
        """列出所有已注册的工具名称"""
        return list(self.tools_map.keys())


# 全局单例
tool_manager = ToolManager()
