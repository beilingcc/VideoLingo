import functools
import time
import os
from rich import print as rprint

# ------------
# 装饰器工具模块
# 提供异常处理和文件检查等功能的装饰器
# ------------

# ------------------------------
# 重试装饰器
# ------------------------------

def except_handler(error_msg, retry=0, delay=1, default_return=None):
    """
    异常处理装饰器，支持自动重试功能
    
    当被装饰的函数发生异常时，会根据设置的重试次数进行重试，
    每次重试之间的延迟时间会按指数增加。
    
    参数:
        error_msg (str): 发生异常时显示的错误信息
        retry (int, optional): 重试次数，默认为0（不重试）
        delay (int, optional): 初始延迟时间（秒），默认为1
        default_return (any, optional): 如果所有重试都失败，返回的默认值，默认为None
        
    返回:
        function: 装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for i in range(retry + 1):
                try:
                    # 尝试执行原函数
                    return func(*args, **kwargs)
                except Exception as e:
                    # 捕获异常
                    last_exception = e
                    rprint(f"[red]{error_msg}: {e}, retry: {i+1}/{retry}[/red]")
                    if i == retry:
                        # 如果已达到最大重试次数
                        if default_return is not None:
                            # 如果设置了默认返回值，则返回默认值
                            return default_return
                        # 否则重新抛出异常
                        raise last_exception
                    # 延迟一段时间后重试，延迟时间按指数增加
                    time.sleep(delay * (2**i))
        return wrapper
    return decorator


# ------------------------------
# 文件存在性检查装饰器
# ------------------------------

def check_file_exists(file_path):
    """
    文件存在性检查装饰器
    
    检查指定的文件是否存在，如果存在则跳过被装饰的函数执行，
    用于避免重复处理已经存在的文件。
    
    参数:
        file_path (str): 要检查的文件路径
        
    返回:
        function: 装饰器函数
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 检查文件是否存在
            if os.path.exists(file_path):
                # 如果文件已存在，则跳过函数执行
                rprint(f"[yellow]⚠️ File <{file_path}> already exists, skip <{func.__name__}> step.[/yellow]")
                return
            # 如果文件不存在，则执行原函数
            return func(*args, **kwargs)
        return wrapper
    return decorator

if __name__ == "__main__":
    # 测试异常处理装饰器
    @except_handler("function execution failed", retry=3, delay=1)
    def test_function():
        raise Exception("test exception")
    test_function()
