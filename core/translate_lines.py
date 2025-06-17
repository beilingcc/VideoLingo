from core.prompts import generate_shared_prompt, get_prompt_faithfulness, get_prompt_expressiveness
from rich.panel import Panel
from rich.console import Console
from rich.table import Table
from rich import box
from core.utils import *
console = Console()

# ------------
# 翻译主流程模块
# 负责将多行文本分块翻译，支持忠实翻译和表达性翻译两步
# ------------

def valid_translate_result(result: dict, required_keys: list, required_sub_keys: list):
    """
    校验翻译结果格式是否符合要求
    参数:
        result (dict): 翻译结果
        required_keys (list): 需要的主键列表
        required_sub_keys (list): 每个主键下需要的子键列表
    返回:
        dict: 校验状态和信息
    """
    # 检查主键
    if not all(key in result for key in required_keys):
        return {"status": "error", "message": f"Missing required key(s): {', '.join(set(required_keys) - set(result.keys()))}"}
    # 检查每个主键下的子键
    for key in result:
        if not all(sub_key in result[key] for sub_key in required_sub_keys):
            return {"status": "error", "message": f"Missing required sub-key(s) in item {key}: {', '.join(set(required_sub_keys) - set(result[key].keys()))}"}
    return {"status": "success", "message": "Translation completed"}


def translate_lines(lines, previous_content_prompt, after_cotent_prompt, things_to_note_prompt, summary_prompt, index = 0):
    """
    翻译多行文本的主函数，分为忠实翻译和表达性翻译两步
    参数:
        lines (str): 需要翻译的多行文本
        previous_content_prompt (str): 上下文前文
        after_cotent_prompt (str): 上下文后文
        things_to_note_prompt (str): 术语注意事项
        summary_prompt (str): 内容摘要
        index (int): 当前块索引
    返回:
        tuple: (最终翻译结果, 原始文本)
    """
    # 生成共享上下文提示词
    shared_prompt = generate_shared_prompt(previous_content_prompt, after_cotent_prompt, summary_prompt, things_to_note_prompt)

    # 内部函数：重试翻译，确保结果格式和长度正确
    def retry_translation(prompt, length, step_name):
        def valid_faith(response_data):
            return valid_translate_result(response_data, [str(i) for i in range(1, length+1)], ['direct'])
        def valid_express(response_data):
            return valid_translate_result(response_data, [str(i) for i in range(1, length+1)], ['free'])
        for retry in range(3):
            if step_name == 'faithfulness':
                result = ask_gpt(prompt+retry* " ", resp_type='json', valid_def=valid_faith, log_title=f'translate_{step_name}')
            elif step_name == 'expressiveness':
                result = ask_gpt(prompt+retry* " ", resp_type='json', valid_def=valid_express, log_title=f'translate_{step_name}')
            if len(lines.split('\n')) == len(result):
                return result
            if retry != 2:
                console.print(f'[yellow]⚠️ {step_name.capitalize()} translation of block {index} failed, Retry...[/yellow]')
        raise ValueError(f'[red]❌ {step_name.capitalize()} translation of block {index} failed after 3 retries. Please check `output/gpt_log/error.json` for more details.[/red]')

    # Step 1: 忠实翻译
    prompt1 = get_prompt_faithfulness(lines, shared_prompt)
    faith_result = retry_translation(prompt1, len(lines.split('\n')), 'faithfulness')

    # 清理直译结果中的换行符
    for i in faith_result:
        faith_result[i]["direct"] = faith_result[i]["direct"].replace('\n', ' ')

    # 判断是否需要表达性翻译
    reflect_translate = load_key('reflect_translate')
    if not reflect_translate:
        # 只做忠实翻译，直接输出
        translate_result = "\n".join([faith_result[i]["direct"].strip() for i in faith_result])
        # 构建结果展示表格
        table = Table(title="Translation Results", show_header=False, box=box.ROUNDED)
        table.add_column("Translations", style="bold")
        for i, key in enumerate(faith_result):
            table.add_row(f"[cyan]Origin:  {faith_result[key]['origin']}[/cyan]")
            table.add_row(f"[magenta]Direct:  {faith_result[key]['direct']}[/magenta]")
            if i < len(faith_result) - 1:
                table.add_row("[yellow]" + "-" * 50 + "[/yellow]")
        console.print(table)
        return translate_result, lines

    # Step 2: 表达性翻译
    prompt2 = get_prompt_expressiveness(faith_result, lines, shared_prompt)
    express_result = retry_translation(prompt2, len(lines.split('\n')), 'expressiveness')

    # 构建结果展示表格
    table = Table(title="Translation Results", show_header=False, box=box.ROUNDED)
    table.add_column("Translations", style="bold")
    for i, key in enumerate(express_result):
        table.add_row(f"[cyan]Origin:  {faith_result[key]['origin']}[/cyan]")
        table.add_row(f"[magenta]Direct:  {faith_result[key]['direct']}[/magenta]")
        table.add_row(f"[green]Free:    {express_result[key]['free']}[/green]")
        if i < len(express_result) - 1:
            table.add_row("[yellow]" + "-" * 50 + "[/yellow]")
    console.print(table)

    # 整理最终翻译结果
    translate_result = "\n".join([express_result[i]["free"].replace('\n', ' ').strip() for i in express_result])

    # 校验翻译行数是否与原文一致
    if len(lines.split('\n')) != len(translate_result.split('\n')):
        console.print(Panel(f'[red]❌ Translation of block {index} failed, Length Mismatch, Please check `output/gpt_log/translate_expressiveness.json`[/red]'))
        raise ValueError(f'Origin ···{lines}···,\nbut got ···{translate_result}···')

    return translate_result, lines


if __name__ == '__main__':
    # 测试用例
    lines = '''All of you know Andrew Ng as a famous computer science professor at Stanford.\nHe was really early on in the development of neural networks with GPUs.\nOf course, a creator of Coursera and popular courses like deeplearning.ai.\nAlso the founder and creator and early lead of Google Brain.'''
    previous_content_prompt = None
    after_cotent_prompt = None
    things_to_note_prompt = None
    summary_prompt = None
    translate_lines(lines, previous_content_prompt, after_cotent_prompt, things_to_note_prompt, summary_prompt)