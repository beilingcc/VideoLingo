# -*- coding: utf-8 -*-
"""
本模块实现了调用 SiliconFlow 平台的 CosyVoice2 模型进行文本转语音 (TTS) 的功能。
专为 VideoLingo 项目定制，支持声音克隆 (voice cloning)。

主要功能:
- 将本地 WAV 音频文件转换为 Base64 编码，用于 API 请求。
- 根据任务编号动态查找对应的参考音频，用于声音克隆。
- 如果特定编号的参考音频不存在，则使用默认的备选音频。
- 如果备选音频也不存在，则尝试自动调用脚本提取参考音频。
- 使用与 OpenAI SDK 兼容的接口与 SiliconFlow API 进行交互。
- 将生成的音频流式传输并保存到指定路径。
- 使用装饰器提供了请求失败后的自动重试机制。

依赖:
- `openai` 库: 用于与 SiliconFlow API 进行交互。
- `core.utils`: 用于加载 API 密钥和异常处理。
- `core._9_refer_audio`: 用于在需要时提取参考音频。

注意:
    使用前请确保已在 `config.yaml` 文件中正确配置了 `sf_cosyvoice2` 的 `api_key`。
"""

from openai import OpenAI
from pathlib import Path
import base64
from core.utils import load_key, except_handler

def wav_to_base64(wav_file_path: Path) -> str:
    """
    将 WAV 音频文件读取并编码为 Base64 字符串。

    Args:
        wav_file_path (Path): WAV 文件的路径对象。

    Returns:
        str: Base64 编码后的音频数据。
    """
    with open(wav_file_path, 'rb') as audio_file:
        audio_content = audio_file.read()
    base64_audio = base64.b64encode(audio_content).decode('utf-8')
    return base64_audio

@except_handler("使用 SiliconFlow TTS 生成音频失败")
def cosyvoice_tts_for_videolingo(text: str, save_as: str, number: int, task_df):
    """
    使用 SiliconFlow CosyVoice2 模型为 VideoLingo 项目生成 TTS 音频。

    该函数会根据字幕编号查找对应的原始文本和参考音频，实现声音克隆。

    Args:
        text (str): 需要转换为语音的目标文本。
        save_as (str): 生成音频的保存路径。
        number (int): 当前处理的字幕编号，用于查找参考音频和提示文本。
        task_df (pd.DataFrame): 包含任务信息的 DataFrame，至少需要 'number' 和 'origin' 列。

    Returns:
        bool: 如果成功生成并保存音频，则返回 True。
    
    Raises:
        FileNotFoundError: 如果参考音频及其备选都找不到，并且自动提取失败。
    """
    # 从任务 DataFrame 中根据编号查找对应的原始文本，作为 prompt
    prompt_text = task_df.loc[task_df['number'] == number, 'origin'].values[0]
    
    # 从配置文件加载 SiliconFlow API 密钥
    api_key = load_key("sf_cosyvoice2.api_key")
    
    # --- 参考音频处理逻辑 ---
    current_dir = Path.cwd()
    # 1. 构造当前编号对应的参考音频路径
    ref_audio_path = current_dir / f"output/audio/refers/{number}.wav"
    
    # 2. 如果特定编号的参考音频不存在，则使用 1 号音频作为备选
    if not ref_audio_path.exists():
        ref_audio_path = current_dir / "output/audio/refers/1.wav"
        # 3. 如果备选音频也不存在，尝试调用脚本自动提取
        if not ref_audio_path.exists():
            try:
                from core._9_refer_audio import extract_refer_audio_main
                print(f"参考音频文件 '{ref_audio_path}' 不存在，尝试自动提取...")
                extract_refer_audio_main()
                # 提取后再次检查文件是否存在
                if not ref_audio_path.exists():
                    raise FileNotFoundError(f"自动提取后，参考音频 '{ref_audio_path}' 仍然不存在。")
            except Exception as e:
                print(f"自动提取参考音频失败: {str(e)}")
                raise # 重新抛出异常，中断执行

    # 将找到的参考音频文件转换为 Base64
    reference_base64 = wav_to_base64(ref_audio_path)
    
    # 初始化客户端，指向 SiliconFlow 的 API 地址
    client = OpenAI(api_key=api_key, base_url="https://api.siliconflow.cn/v1")

    # 确保保存目录存在
    save_path = Path(save_as)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    # 调用 API，使用流式响应来创建音频文件
    with client.audio.speech.with_streaming_response.create(
        model="FunAudioLLM/CosyVoice2-0.5B", # 指定使用的模型
        voice="", # voice 参数在这里不重要，因为我们使用 reference
        input=text, # 要合成的文本
        response_format="wav", # 音频格式
        # extra_body 用于传递 SiliconFlow 的特定参数
        extra_body={"references": [{
            "audio": f"data:audio/wav;base64,{reference_base64}", # Base64 编码的参考音频
            "text": prompt_text # 与参考音频匹配的提示文本
        }]}
    ) as response:
        response.stream_to_file(save_path)
    
    print(f"音频已成功保存至: {save_path}")
    return True