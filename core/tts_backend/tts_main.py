# -*- coding: utf-8 -*-
"""
本模块是整个文本转语音 (TTS) 功能的核心调度中心。

主要功能:
- **统一入口**: 提供 `tts_main` 函数作为所有 TTS 请求的唯一入口。
- **动态后端选择**: 从 `config.yaml` 文件中读取 `tts_method` 配置，动态选择并调用相应的 TTS 后端服务。
  支持的后端包括 OpenAI, GPT-SoVITS, Fish-TTS, Azure, Edge, SiliconFlow Fish-TTS, SiliconFlow CosyVoice2, F5-TTS, 以及自定义 TTS。
- **文本预处理**: 在调用 TTS API 前，使用 `clean_text_for_tts` 清洗文本，移除可能导致错误的特殊字符。
- **边缘情况处理**:
  - 对空文本或过短的文本（如单个字符）直接生成静音音频，避免下游处理错误。
  - 如果目标音频文件已存在，则跳过生成，以支持断点续传。
- **健壮的容错机制**:
  - **自动重试**: 当 TTS 生成失败或生成的音频时长为0时，会自动重试最多3次。
  - **文本修正**: 在最后一次重试前，会调用 GPT-4 对原始文本进行“修正”，尝试解决因文本内容问题导致的生成失败。
  - **最终回退**: 如果所有重试均失败，会生成一段短暂的静音音频作为最终的兜底措施，确保每个文本片段都有对应的音频文件，防止处理流程中断。

调用流程:
1. `tts_main` 被调用，传入待合成的文本、保存路径、编号和任务信息。
2. 清洗文本并检查是否为空。
3. 加载配置，确定要使用的 TTS 方法。
4. 进入重试循环：
   a. 调用选定的 TTS 后端函数。
   b. 检查生成的音频文件是否有效（时长 > 0）。
   c. 如果无效，删除文件并准备重试。在最后一次尝试前，调用 GPT 修正文本。
   d. 如果成功，则跳出循环。
5. 如果循环结束仍未成功，则生成静音文件或抛出异常。
"""

import os
import re
from pydub import AudioSegment

# --- 导入所有支持的 TTS 后端模块 ---
from core.asr_backend.audio_preprocess import get_audio_duration
from core.tts_backend.gpt_sovits_tts import gpt_sovits_tts_for_videolingo
from core.tts_backend.sf_fishtts import siliconflow_fish_tts_for_videolingo
from core.tts_backend.openai_tts import openai_tts
from core.tts_backend.fish_tts import fish_tts
from core.tts_backend.azure_tts import azure_tts
from core.tts_backend.edge_tts import edge_tts
from core.tts_backend.sf_cosyvoice2 import cosyvoice_tts_for_videolingo
from core.tts_backend.custom_tts import custom_tts
from core.prompts import get_correct_text_prompt
from core.tts_backend._302_f5tts import f5_tts_for_videolingo
from core.utils import load_key, rprint, ask_gpt


def clean_text_for_tts(text: str) -> str:
    """
    清洗文本，移除在 TTS 中可能导致问题的特殊字符。

    Args:
        text (str): 原始输入文本。

    Returns:
        str: 清洗后的文本。
    """
    # 定义一个要移除的特殊字符列表 (例如：商标符号、版权符号等)
    chars_to_remove = ['&', '®', '™', '©']
    for char in chars_to_remove:
        text = text.replace(char, '')
    return text.strip()


def tts_main(text: str, save_as: str, number: int, task_df):
    """
    TTS 主调度函数，根据配置选择后端，并包含自动重试与容错逻辑。

    Args:
        text (str): 需要转换为语音的文本。
        save_as (str): 音频文件的保存路径。
        number (int): 当前任务的编号，用于需要上下文的 TTS 服务 (如声音克隆)。
        task_df (pd.DataFrame): 包含所有任务信息的 DataFrame，用于需要上下文的 TTS 服务。
    """
    # 1. 预处理文本
    text = clean_text_for_tts(text)

    # 2. 处理边缘情况：空文本或过短的文本（单字符等），直接生成静音
    #    某些 TTS 服务无法处理或会报错，统一生成静音可以保证流程健壮性
    cleaned_text = re.sub(r'[^\w\s]', '', text).strip() # 移除非字母数字和空格的字符后检查
    if not cleaned_text or len(cleaned_text) <= 1:
        silence = AudioSegment.silent(duration=100)  # 创建100毫秒的静音
        silence.export(save_as, format="wav")
        rprint(f"[yellow]警告: 文本为空或过短，已生成静音文件 -> {save_as}")
        return

    # 3. 如果文件已存在，则跳过，支持断点续传
    if os.path.exists(save_as):
        rprint(f"[dim]文件已存在，跳过: {save_as}[/dim]")
        return

    rprint(f"🎤 正在生成音频: \"{text[:50]}...\"")
    
    # 4. 从配置文件加载要使用的 TTS 方法
    TTS_METHOD = load_key("tts_method")

    # 5. 健壮的重试与容错循环
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 在最后一次尝试前，如果仍然失败，则调用 GPT 来“修正”文本
            # 这可以解决某些因文本格式或内容问题导致的 TTS 失败
            if attempt == max_retries - 1:
                rprint("[yellow]警告: 多次尝试失败，正在调用 GPT 修正文本后进行最后一次尝试...")
                correct_text_result = ask_gpt(get_correct_text_prompt(text), resp_type="json", log_title='tts_correct_text')
                if correct_text_result and 'text' in correct_text_result:
                    original_text = text
                    text = correct_text_result['text']
                    rprint(f"[yellow]GPT 已修正文本: '{original_text}' -> '{text}'")
                else:
                    rprint("[red]错误: GPT 文本修正失败，将使用原始文本进行最后尝试。")

            # --- 根据配置动态调用不同的 TTS 后端 ---
            if TTS_METHOD == 'openai_tts':
                openai_tts(text, save_as)
            elif TTS_METHOD == 'gpt_sovits':
                gpt_sovits_tts_for_videolingo(text, save_as, number, task_df)
            elif TTS_METHOD == 'fish_tts':
                fish_tts(text, save_as)
            elif TTS_METHOD == 'azure_tts':
                azure_tts(text, save_as)
            elif TTS_METHOD == 'sf_fish_tts':
                siliconflow_fish_tts_for_videolingo(text, save_as, number, task_df)
            elif TTS_METHOD == 'edge_tts':
                edge_tts(text, save_as)
            elif TTS_METHOD == 'custom_tts':
                custom_tts(text, save_as)
            elif TTS_METHOD == 'sf_cosyvoice2':
                cosyvoice_tts_for_videolingo(text, save_as, number, task_df)
            elif TTS_METHOD == 'f5tts':
                f5_tts_for_videolingo(text, save_as, number, task_df)

            # 6. 检查生成的音频是否有效
            if not os.path.exists(save_as):
                 raise FileNotFoundError("TTS 服务未生成任何文件。")
            
            duration = get_audio_duration(save_as)
            if duration > 0.05:  # 认为大于50ms的音频是有效的
                rprint(f"[green]✅ 音频生成成功: {save_as} (时长: {duration:.2f}s)")
                break  # 成功，跳出重试循环
            else:
                # 如果文件存在但时长为0，说明生成失败，删除它以便重试
                if os.path.exists(save_as):
                    os.remove(save_as)
                # 如果这是最后一次尝试，记录警告并生成静音作为兜底
                if attempt == max_retries - 1:
                    rprint(f"[red]错误: 最终尝试后生成的音频时长仍为0。文本: '{text}'")
                    silence = AudioSegment.silent(duration=100)
                    silence.export(save_as, format="wav")
                    rprint(f"[yellow]已生成静音文件作为替代: {save_as}")
                    return
                rprint(f"[yellow]警告: 生成的音频时长为0，正在进行第 {attempt + 2}/{max_retries} 次重试...")

        except Exception as e:
            rprint(f"[red]错误: TTS 生成失败 (尝试 {attempt + 1}/{max_retries}) - {e}")
            if attempt == max_retries - 1:
                rprint(f"[bold red]❌ 经过 {max_retries} 次重试后，音频生成彻底失败。请检查错误日志。[/bold red]")
                raise Exception(f"多次重试后音频生成失败: {str(e)}")
            rprint(f"[yellow]正在进行第 {attempt + 2}/{max_retries} 次重试...")
