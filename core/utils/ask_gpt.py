import os
import json
from threading import Lock
import json_repair
from openai import OpenAI
from core.utils.config_utils import load_key
from rich import print as rprint
from core.utils.decorator import except_handler

# ------------
# GPT请求模块
# 负责与OpenAI API通信，发送请求并处理响应
# 包含缓存机制，避免重复请求
# ------------

# 线程锁，用于保护缓存文件的读写操作
LOCK = Lock()
# GPT响应缓存文件夹
GPT_LOG_FOLDER = 'output/gpt_log'

def _save_cache(model, prompt, resp_content, resp_type, resp, message=None, log_title="default"):
    """
    保存GPT响应到缓存文件
    
    参数:
        model (str): 使用的模型名称
        prompt (str): 发送的提示词
        resp_content (str): 原始响应内容
        resp_type (str): 响应类型，如'json'或None
        resp (dict/str): 处理后的响应
        message (str, optional): 附加信息，默认为None
        log_title (str, optional): 日志文件名，默认为"default"
        
    返回:
        None
    """
    with LOCK:
        logs = []
        file = os.path.join(GPT_LOG_FOLDER, f"{log_title}.json")
        # 确保目录存在
        os.makedirs(os.path.dirname(file), exist_ok=True)
        # 如果文件存在，读取现有日志
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        # 添加新的日志条目
        logs.append({"model": model, "prompt": prompt, "resp_content": resp_content, "resp_type": resp_type, "resp": resp, "message": message})
        # 写入更新后的日志
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=4)

def _load_cache(prompt, resp_type, log_title):
    """
    从缓存文件加载GPT响应
    
    参数:
        prompt (str): 发送的提示词
        resp_type (str): 响应类型，如'json'或None
        log_title (str): 日志文件名
        
    返回:
        dict/str/bool: 如果找到缓存的响应则返回，否则返回False
    """
    with LOCK:
        file = os.path.join(GPT_LOG_FOLDER, f"{log_title}.json")
        # 如果缓存文件存在
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                # 遍历所有日志条目
                for item in json.load(f):
                    # 如果找到匹配的提示词和响应类型
                    if item["prompt"] == prompt and item["resp_type"] == resp_type:
                        return item["resp"]
        return False

# ------------
# 发送GPT请求
# ------------

@except_handler("GPT request failed", retry=5)
def ask_gpt(prompt, resp_type=None, valid_def=None, log_title="default"):
    """
    向GPT发送请求并获取响应
    
    参数:
        prompt (str): 发送给GPT的提示词
        resp_type (str, optional): 响应类型，如'json'或None，默认为None
        valid_def (callable, optional): 验证响应的函数，默认为None
        log_title (str, optional): 日志文件名，默认为"default"
        
    返回:
        dict/str: 处理后的GPT响应
        
    异常:
        ValueError: 如果API密钥未设置或响应格式无效
    """
    # 检查API密钥是否设置
    if not load_key("api.key"):
        raise ValueError("API key is not set")
    
    # 检查缓存
    cached = _load_cache(prompt, resp_type, log_title)
    if cached:
        rprint("use cache response")
        return cached

    # 加载配置
    model = load_key("api.model")
    base_url = load_key("api.base_url")
    # 处理特殊的base_url
    if 'ark' in base_url:
        base_url = "https://ark.cn-beijing.volces.com/api/v3" # 火山引擎base url
    elif 'v1' not in base_url:
        base_url = base_url.strip('/') + '/v1'
    
    # 创建OpenAI客户端
    client = OpenAI(api_key=load_key("api.key"), base_url=base_url)
    # 如果需要JSON响应且模型支持，设置响应格式
    response_format = {"type": "json_object"} if resp_type == "json" and load_key("api.llm_support_json") else None

    # 构建消息
    messages = [{"role": "user", "content": prompt}]

    # 设置请求参数
    params = dict(
        model=model,
        messages=messages,
        response_format=response_format,
        timeout=300
    )
    
    # 发送请求
    resp_raw = client.chat.completions.create(**params)

    # 处理响应
    resp_content = resp_raw.choices[0].message.content
    if resp_type == "json":
        # 如果需要JSON响应，使用json_repair修复可能的JSON格式错误
        resp = json_repair.loads(resp_content)
    else:
        resp = resp_content
    
    # 如果提供了验证函数，验证响应格式
    if valid_def:
        valid_resp = valid_def(resp)
        if valid_resp['status'] != 'success':
            # 如果验证失败，保存错误日志并抛出异常
            _save_cache(model, prompt, resp_content, resp_type, resp, log_title="error", message=valid_resp['message'])
            raise ValueError(f"❎ API response error: {valid_resp['message']}")

    # 保存成功的响应到缓存
    _save_cache(model, prompt, resp_content, resp_type, resp, log_title=log_title)
    return resp


if __name__ == '__main__':
    from rich import print as rprint
    
    # 测试JSON输出
    result = ask_gpt("""test respond ```json\n{\"code\": 200, \"message\": \"success\"}\n```""", resp_type="json")
    rprint(f"Test json output result: {result}")
