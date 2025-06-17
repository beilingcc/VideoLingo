import streamlit as st
import os, sys
from core.st_utils.imports_and_utils import *
from core import *

# ------------
# 设置环境路径
# ------------
current_dir = os.path.dirname(os.path.abspath(__file__))
os.environ['PATH'] += os.pathsep + current_dir
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置Streamlit页面
st.set_page_config(page_title="VideoLingo", page_icon="docs/logo.svg")

# 定义输出视频路径常量
SUB_VIDEO = "output/output_sub.mp4"  # 带字幕的视频输出路径
DUB_VIDEO = "output/output_dub.mp4"  # 带配音的视频输出路径

def text_processing_section():
    """
    文本处理部分UI，包括翻译和生成字幕的功能
    """
    st.header(t("b. Translate and Generate Subtitles"))
    with st.container(border=True):
        st.markdown(f"""
        <p style='font-size: 20px;'>
        {t("This stage includes the following steps:")}
        <p style='font-size: 20px;'>
            1. {t("WhisperX word-level transcription")}<br>
            2. {t("Sentence segmentation using NLP and LLM")}<br>
            3. {t("Summarization and multi-step translation")}<br>
            4. {t("Cutting and aligning long subtitles")}<br>
            5. {t("Generating timeline and subtitles")}<br>
            6. {t("Merging subtitles into the video")}
        """, unsafe_allow_html=True)

        # 检查是否已经生成了带字幕的视频
        if not os.path.exists(SUB_VIDEO):
            if st.button(t("Start Processing Subtitles"), key="text_processing_button"):
                process_text()
                st.rerun()
        else:
            # 如果已经生成了带字幕的视频，显示视频和下载选项
            if load_key("burn_subtitles"):
                st.video(SUB_VIDEO)
            download_subtitle_zip_button(text=t("Download All Srt Files"))
            
            if st.button(t("Archive to 'history'"), key="cleanup_in_text_processing"):
                cleanup()
                st.rerun()
            return True

def process_text():
    """
    处理文本的主要流程，包括转录、分割、翻译和生成字幕
    """
    with st.spinner(t("Using Whisper for transcription...")):
        _2_asr.transcribe()  # 使用Whisper进行语音转文本
    with st.spinner(t("Splitting long sentences...")):  
        _3_1_split_nlp.split_by_spacy()  # 使用Spacy进行句子分割
        _3_2_split_meaning.split_sentences_by_meaning()  # 基于语义分割句子
    with st.spinner(t("Summarizing and translating...")):
        _4_1_summarize.get_summary()  # 获取摘要
        if load_key("pause_before_translate"):
            input(t("⚠️ PAUSE_BEFORE_TRANSLATE. Go to `output/log/terminology.json` to edit terminology. Then press ENTER to continue..."))
        _4_2_translate.translate_all()  # 翻译所有内容
    with st.spinner(t("Processing and aligning subtitles...")): 
        _5_split_sub.split_for_sub_main()  # 为字幕分割文本
        _6_gen_sub.align_timestamp_main()  # 对齐时间戳
    with st.spinner(t("Merging subtitles to video...")):
        _7_sub_into_vid.merge_subtitles_to_video()  # 将字幕合并到视频中
    
    st.success(t("Subtitle processing complete! 🎉"))
    st.balloons()

def audio_processing_section():
    """
    音频处理部分UI，包括配音功能
    """
    st.header(t("c. Dubbing"))
    with st.container(border=True):
        st.markdown(f"""
        <p style='font-size: 20px;'>
        {t("This stage includes the following steps:")}
        <p style='font-size: 20px;'>
            1. {t("Generate audio tasks and chunks")}<br>
            2. {t("Extract reference audio")}<br>
            3. {t("Generate and merge audio files")}<br>
            4. {t("Merge final audio into video")}
        """, unsafe_allow_html=True)
        # 检查是否已经生成了带配音的视频
        if not os.path.exists(DUB_VIDEO):
            if st.button(t("Start Audio Processing"), key="audio_processing_button"):
                process_audio()
                st.rerun()
        else:
            # 如果已经生成了带配音的视频，显示视频和相关选项
            st.success(t("Audio processing is complete! You can check the audio files in the `output` folder."))
            if load_key("burn_subtitles"):
                st.video(DUB_VIDEO) 
            if st.button(t("Delete dubbing files"), key="delete_dubbing_files"):
                delete_dubbing_files()
                st.rerun()
            if st.button(t("Archive to 'history'"), key="cleanup_in_audio_processing"):
                cleanup()
                st.rerun()

def process_audio():
    """
    处理音频的主要流程，包括生成配音任务、提取参考音频、生成音频和合并
    """
    with st.spinner(t("Generate audio tasks")): 
        _8_1_audio_task.gen_audio_task_main()  # 生成音频任务
        _8_2_dub_chunks.gen_dub_chunks()  # 生成配音块
    with st.spinner(t("Extract refer audio")):
        _9_refer_audio.extract_refer_audio_main()  # 提取参考音频
    with st.spinner(t("Generate all audio")):
        _10_gen_audio.gen_audio()  # 生成所有音频
    with st.spinner(t("Merge full audio")):
        _11_merge_audio.merge_full_audio()  # 合并完整音频
    with st.spinner(t("Merge dubbing to the video")):
        _12_dub_to_vid.merge_video_audio()  # 将配音合并到视频中
    
    st.success(t("Audio processing complete! 🎇"))
    st.balloons()

def main():
    """
    主函数，设置页面布局并调用各个处理部分
    """
    # 显示logo
    logo_col, _ = st.columns([1,1])
    with logo_col:
        st.image("docs/logo.png", use_column_width=True)
    st.markdown(button_style, unsafe_allow_html=True)
    
    # 欢迎文本
    welcome_text = t("Hello, welcome to VideoLingo. If you encounter any issues, feel free to get instant answers with our Free QA Agent <a href=\"https://share.fastgpt.in/chat/share?shareId=066w11n3r9aq6879r4z0v9rh\" target=\"_blank\">here</a>! You can also try out our SaaS website at <a href=\"https://videolingo.io\" target=\"_blank\">videolingo.io</a> for free!")
    st.markdown(f"<p style='font-size: 20px; color: #808080;'>{welcome_text}</p>", unsafe_allow_html=True)
    
    # 添加设置侧边栏
    with st.sidebar:
        page_setting()
        st.markdown(give_star_button, unsafe_allow_html=True)
    
    # 调用各个处理部分
    download_video_section()  # 视频下载部分
    text_processing_section()  # 文本处理部分
    audio_processing_section()  # 音频处理部分

if __name__ == "__main__":
    main()
