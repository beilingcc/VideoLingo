# ------------
# 核心工具模块初始化文件
# 提供各种通用工具函数
# ------------

# 使用try-except避免在安装过程中出现导入错误
try:
    from .ask_gpt import ask_gpt                               # GPT请求函数
    from .decorator import except_handler, check_file_exists   # 异常处理和文件检查装饰器
    from .config_utils import load_key, update_key, get_joiner # 配置工具函数
    from rich import print as rprint                           # 增强的打印函数
except ImportError:
    pass

# 定义模块导出的所有组件
__all__ = [
    "ask_gpt",           # GPT请求函数
    "except_handler",    # 异常处理装饰器
    "check_file_exists", # 文件存在性检查装饰器
    "load_key",          # 加载配置键值函数
    "update_key",        # 更新配置键值函数
    "rprint",            # 增强的打印函数
    "get_joiner"         # 获取分隔符函数
]