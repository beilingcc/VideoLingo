from ruamel.yaml import YAML
import threading

# ------------
# 配置文件工具模块
# 负责加载和更新config.yaml配置文件
# ------------

CONFIG_PATH = 'config.yaml'  # 配置文件路径
lock = threading.Lock()      # 线程锁，保证多线程安全

yaml = YAML()
yaml.preserve_quotes = True  # 保留YAML中的引号

# -----------------------
# 加载和更新配置
# -----------------------

def load_key(key):
    """
    加载配置文件中的指定键值
    
    支持多级key（用点分隔），如'a.b.c'。
    
    参数:
        key (str): 配置项的键，支持多级
    返回:
        任意: 对应的配置值
    异常:
        KeyError: 如果找不到指定的key
    """
    with lock:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            data = yaml.load(file)

    keys = key.split('.')
    value = data
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            raise KeyError(f"Key '{k}' not found in configuration")
    return value

def update_key(key, new_value):
    """
    更新配置文件中的指定键值
    
    支持多级key（用点分隔），如'a.b.c'。
    
    参数:
        key (str): 配置项的键，支持多级
        new_value: 新的值
    返回:
        bool: 更新成功返回True，否则False
    异常:
        KeyError: 如果找不到指定的key
    """
    with lock:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            data = yaml.load(file)

        keys = key.split('.')
        current = data
        for k in keys[:-1]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False

        if isinstance(current, dict) and keys[-1] in current:
            current[keys[-1]] = new_value
            with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
                yaml.dump(data, file)
            return True
        else:
            raise KeyError(f"Key '{keys[-1]}' not found in configuration")
        
# 基础工具

def get_joiner(language):
    """
    根据语言返回分词连接符
    
    参数:
        language (str): 语言代码
    返回:
        str: 连接符（空格或空字符串）
    异常:
        ValueError: 不支持的语言代码
    """
    if language in load_key('language_split_with_space'):
        return " "
    elif language in load_key('language_split_without_space'):
        return ""
    else:
        raise ValueError(f"Unsupported language code: {language}")

if __name__ == "__main__":
    print(load_key('language_split_with_space'))
