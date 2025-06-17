# 导入所需的库
import os  # 用于操作系统相关操作，如路径处理
import gc  # 用于垃圾回收
from batch.utils.settings_check import check_settings  # 导入设置检查函数
from batch.utils.video_processor import process_video  # 导入视频处理函数
from core.utils.config_utils import load_key, update_key  # 导入配置读写工具
import pandas as pd  # 用于处理Excel文件和数据
from rich.console import Console  # 用于在终端中创建富文本输出
from rich.panel import Panel  # rich库的一部分，用于创建带边框的面板
import time  # 用于时间相关操作，如暂停
import shutil  # 用于文件和目录的高级操作，如复制和删除

# 初始化rich控制台，用于美化输出
console = Console()

def record_and_update_config(source_language, target_language):
    """
    记录原始的语言设置，并根据需要更新配置文件。
    这样可以为每个视频任务临时设置特定的语言，处理完后再恢复。

    Args:
        source_language (str): 从Excel中读取的源语言。
        target_language (str): 从Excel中读取的目标语言。

    Returns:
        tuple: 包含原始源语言和目标语言的元组。
    """
    # 加载当前配置文件中的源语言和目标语言作为原始设置
    original_source_lang = load_key('whisper.language')
    original_target_lang = load_key('target_language')
    
    # 如果Excel中指定了源语言，则更新配置文件
    if source_language and not pd.isna(source_language):
        update_key('whisper.language', source_language)
    # 如果Excel中指定了目标语言，则更新配置文件
    if target_language and not pd.isna(target_language):
        update_key('target_language', target_language)
    
    # 返回原始设置，以便后续恢复
    return original_source_lang, original_target_lang

def process_batch():
    """
    主函数，用于处理整个批处理流程。
    它会读取Excel任务列表，并逐一处理每个视频。
    """
    # 在开始批处理前，首先检查所有必要的设置是否正确
    if not check_settings():
        raise Exception("设置检查失败，请根据提示修正config.yaml中的配置")

    # 读取位于 'batch' 目录下的任务设置Excel文件
    df = pd.read_excel('batch/tasks_setting.xlsx')
    
    # 遍历Excel文件中的每一行（即每一个任务）
    for index, row in df.iterrows():
        # 只处理状态为空（新任务）或包含'Error'（失败任务）的任务
        if pd.isna(row['Status']) or 'Error' in str(row['Status']):
            total_tasks = len(df)  # 获取任务总数
            video_file = row['Video File']  # 获取视频文件名
            
            # 如果任务状态为'Error'，说明是重试失败的任务
            if not pd.isna(row['Status']) and 'Error' in str(row['Status']):
                console.print(Panel(f"正在重试失败的任务: {video_file}\n任务 {index + 1}/{total_tasks}", 
                                 title="[bold yellow]重试任务", expand=False))
                
                # 从 'batch/output/ERROR' 目录恢复之前失败时备份的文件
                error_folder = os.path.join('batch', 'output', 'ERROR', os.path.splitext(video_file)[0])
                
                if os.path.exists(error_folder):
                    os.makedirs('output', exist_ok=True)  # 确保 'output' 目录存在
                    
                    # 将错误备份文件夹中的所有内容复制回 'output' 目录
                    for item in os.listdir(error_folder):
                        src_path = os.path.join(error_folder, item)
                        dst_path = os.path.join('output', item)
                        
                        if os.path.isdir(src_path):
                            if os.path.exists(dst_path):
                                shutil.rmtree(dst_path)  # 如果目标是目录且已存在，则先删除
                            shutil.copytree(src_path, dst_path)
                        else:
                            if os.path.exists(dst_path):
                                os.remove(dst_path)  # 如果目标是文件且已存在，则先删除
                            shutil.copy2(src_path, dst_path)
                            
                    console.print(f"[green]已为 {video_file} 从ERROR文件夹恢复文件")
                else:
                    console.print(f"[yellow]警告: 未找到错误备份文件夹: {error_folder}")
            else:
                # 如果是新任务，则打印当前任务信息
                console.print(Panel(f"正在处理任务: {video_file}\n任务 {index + 1}/{total_tasks}", 
                                 title="[bold blue]当前任务", expand=False))
            
            # 从任务行中获取源语言和目标语言
            source_language = row['Source Language']
            target_language = row['Target Language']
            
            # 记录并更新当前任务的语言配置
            original_source_lang, original_target_lang = record_and_update_config(source_language, target_language)
            
            try:
                # 获取是否需要配音的设置，默认为0（不配音）
                dubbing = 0 if pd.isna(row['Dubbing']) else int(row['Dubbing'])
                # 判断当前是否为重试操作
                is_retry = not pd.isna(row['Status']) and 'Error' in str(row['Status'])
                # 调用核心视频处理函数
                status, error_step, error_message = process_video(video_file, dubbing, is_retry)
                # 根据返回结果生成状态信息
                status_msg = "Done" if status else f"Error: {error_step} - {error_message}"
            except Exception as e:
                # 捕获未预料到的异常
                status_msg = f"Error: 未处理的异常 - {str(e)}"
                console.print(f"[bold red]处理 {video_file} 时发生错误: {status_msg}")
            finally:
                # 无论成功与否，都恢复原始的语言配置
                update_key('whisper.language', original_source_lang)
                update_key('target_language', original_target_lang)
                
                # 更新DataFrame中的任务状态
                df.at[index, 'Status'] = status_msg
                # 将更新后的DataFrame写回Excel文件
                df.to_excel('batch/tasks_setting.xlsx', index=False)
                
                # 手动执行垃圾回收，释放内存
                gc.collect()
                
                # 短暂暂停，避免过于频繁的文件操作
                time.sleep(1)
        else:
            # 如果任务状态不是空或Error，则跳过
            print(f"跳过任务: {row['Video File']} - 状态: {row['Status']}")

    # 所有任务处理完毕后，打印完成信息
    console.print(Panel("所有任务已处理完毕!\n请到 `batch/output` 目录查看结果!", 
                       title="[bold green]批处理完成", expand=False))

# 当该脚本作为主程序运行时，执行批处理函数
if __name__ == "__main__":
    process_batch()