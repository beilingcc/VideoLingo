# 导入所需的库
import os  # 用于操作系统相关操作，如路径处理
import pandas as pd  # 用于处理Excel文件和数据
from rich.console import Console  # 用于在终端中创建富文本输出
from rich.panel import Panel  # rich库的一部分，用于创建带边框的面板

# --- 常量定义 ---
# 任务设置Excel文件的路径
SETTINGS_FILE = 'batch/tasks_setting.xlsx'
# 存放本地视频文件的输入文件夹路径
INPUT_FOLDER = os.path.join('batch', 'input')
# 'Dubbing'字段允许的有效值列表（0表示不配音，1表示配音）
VALID_DUBBING_VALUES = [0, 1]

# 初始化rich控制台，用于美化输出
console = Console()

def check_settings():
    """
    检查批处理任务的设置是否正确。
    这个函数会验证以下几点：
    1. 'batch/input' 文件夹中的视频文件是否都在Excel任务列表中有记录。
    2. Excel中指定的本地视频文件是否存在。
    3. Excel中指定的 'Dubbing' 值是否有效（0或1）。
    
    Returns:
        bool: 如果所有检查都通过，则返回 True，否则返回 False。
    """
    # 确保输入文件夹存在，如果不存在则创建
    os.makedirs(INPUT_FOLDER, exist_ok=True)
    
    # 读取任务设置Excel文件
    df = pd.read_excel(SETTINGS_FILE)
    
    # 获取输入文件夹中的所有文件名
    input_files = set(os.listdir(INPUT_FOLDER))
    # 获取Excel中 'Video File' 列的所有文件名
    excel_files = set(df['Video File'].tolist())
    
    # 找出在文件夹中但不在Excel列表中的文件
    files_not_in_excel = input_files - excel_files

    # 初始化检查状态和任务计数器
    all_passed = True
    local_video_tasks = 0
    url_tasks = 0

    # 如果有文件存在于input文件夹但未在Excel中声明，则打印警告
    if files_not_in_excel:
        console.print(Panel(
            "\n".join([f"- {file}" for file in files_not_in_excel]),
            title="[bold red]警告: 以下文件在input文件夹中，但未在Excel中声明",
            expand=False
        ))
        all_passed = False

    # 遍历Excel中的每一行（即每一个任务）进行详细检查
    for index, row in df.iterrows():
        video_file = row['Video File']
        source_language = row['Source Language']
        dubbing = row['Dubbing']

        # 检查视频文件是URL还是本地文件
        if str(video_file).startswith('http'):
            url_tasks += 1  # URL任务计数
        elif os.path.isfile(os.path.join(INPUT_FOLDER, str(video_file))):
            local_video_tasks += 1  # 本地视频任务计数
        else:
            # 如果文件既不是有效的URL格式，也不是存在的本地文件，则报告错误
            console.print(Panel(f"无效的视频文件或URL: 「{video_file}」", title=f"[bold red]错误在第 {index + 2} 行", expand=False))
            all_passed = False

        # 检查 'Dubbing' 字段的值是否有效
        if not pd.isna(dubbing):
            if int(dubbing) not in VALID_DUBBING_VALUES:
                console.print(Panel(f"无效的配音值: 「{dubbing}」 (只允许 0 或 1)", title=f"[bold red]错误在第 {index + 2} 行", expand=False))
                all_passed = False

    # 如果所有检查都通过，则打印成功信息
    if all_passed:
        console.print(Panel(f"✅ 所有设置检查通过!\n检测到 {local_video_tasks} 个本地视频任务和 {url_tasks} 个URL任务。", title="[bold green]成功", expand=False))

    # 返回最终的检查结果
    return all_passed


# 当该脚本作为主程序运行时，执行设置检查函数
if __name__ == "__main__":  
    check_settings()