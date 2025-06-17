# 导入所需的标准库
import os  # 用于操作系统相关操作，如文件路径、删除文件等
import re  # 用于正则表达式，进行文本匹配和处理
import shutil  # 用于高级文件操作，如删除目录树
import subprocess  # 用于运行子进程，如此处的ffmpeg命令
from time import sleep  # 用于在操作后暂停，确保文件系统更新

# 导入第三方库
import streamlit as st  # Streamlit库，用于创建Web应用界面

# 导入项目核心模块
from core._1_ytdlp import download_video_ytdlp, find_video_files  # 从ytdlp模块导入视频下载和查找功能
from core.utils import *  # 导入所有自定义工具函数
from translations.translations import translate as t  # 导入翻译函数，用于多语言支持

# 定义常量
OUTPUT_DIR = "output"  # 指定存放下载或上传文件的输出目录

def download_video_section():
    """
    在Streamlit界面上创建一个区域，用于下载或上传视频。
    
    - 如果视频已存在，则显示视频和删除按钮。
    - 如果视频不存在，则提供从YouTube下载或本地上传的选项。
    - 处理音频文件上传，并将其转换为视频格式。

    Returns:
        bool: 如果视频文件已准备就绪，返回True；否则返回False。
    """
    st.header(t("a. Download or Upload Video"))  # 显示区域标题
    with st.container(border=True):  # 使用带边框的容器美化界面
        try:
            # 尝试在输出目录中查找视频文件
            video_file = find_video_files()
            st.video(video_file)  # 如果找到，则播放视频
            
            # 创建一个按钮，用于删除现有视频并重新选择
            if st.button(t("Delete and Reselect"), key="delete_video_button"):
                os.remove(video_file)  # 删除视频文件
                if os.path.exists(OUTPUT_DIR):
                    shutil.rmtree(OUTPUT_DIR)  # 删除整个输出目录
                sleep(1)  # 短暂休眠，确保文件操作完成
                st.rerun()  # 重新运行Streamlit应用，刷新界面
            return True  # 视频已存在，返回True

        except FileNotFoundError:
            # 如果找不到视频文件，则显示下载和上传选项
            col1, col2 = st.columns([3, 1])  # 创建两列布局
            with col1:
                url = st.text_input(t("Enter YouTube link:"))  # YouTube链接输入框
            with col2:
                # 视频分辨率选择
                res_dict = {
                    "360p": "360",
                    "1080p": "1080",
                    "Best": "best"
                }
                target_res = load_key("ytb_resolution")  # 从配置加载默认分辨率
                res_options = list(res_dict.keys())
                # 设置下拉框的默认选项
                default_idx = list(res_dict.values()).index(target_res) if target_res in res_dict.values() else 0
                res_display = st.selectbox(t("Resolution"), options=res_options, index=default_idx)
                res = res_dict[res_display]  # 获取用户选择的分辨率值

            # “下载视频”按钮
            if st.button(t("Download Video"), key="download_button", use_container_width=True):
                if url:  # 确保URL不为空
                    with st.spinner("Downloading video..."):  # 显示加载提示
                        download_video_ytdlp(url, resolution=res)  # 调用下载函数
                    st.rerun()  # 下载完成后刷新应用

            # “上传视频”组件
            allowed_formats = load_key("allowed_video_formats") + load_key("allowed_audio_formats")
            uploaded_file = st.file_uploader(t("Or upload video"), type=allowed_formats)
            
            if uploaded_file:
                # 清理并创建输出目录
                if os.path.exists(OUTPUT_DIR):
                    shutil.rmtree(OUTPUT_DIR)
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                
                # 清理文件名，移除特殊字符和空格
                raw_name = uploaded_file.name.replace(' ', '_')
                name, ext = os.path.splitext(raw_name)
                clean_name = re.sub(r'[^\w\-_\.]', '', name) + ext.lower()
                    
                # 将上传的文件保存到本地
                with open(os.path.join(OUTPUT_DIR, clean_name), "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # 如果上传的是音频文件，则进行转换
                if ext.lower() in load_key("allowed_audio_formats"):
                    convert_audio_to_video(os.path.join(OUTPUT_DIR, clean_name))
                st.rerun()  # 处理完上传后刷新应用
            else:
                return False  # 没有视频，返回False

def convert_audio_to_video(audio_file: str) -> str:
    """
    使用FFmpeg将音频文件转换为带有黑屏的MP4视频文件。

    Args:
        audio_file (str): 输入的音频文件路径。

    Returns:
        str: 输出的视频文件路径。
    """
    output_video = os.path.join(OUTPUT_DIR, 'black_screen.mp4')
    if not os.path.exists(output_video):
        print(f"🎵➡️🎬 Converting audio to video with FFmpeg ......")
        # 构建FFmpeg命令
        # -f lavfi -i color=c=black:s=640x360: 创建一个黑色的视频流作为背景
        # -i audio_file: 指定输入的音频文件
        # -shortest: 使输出视频的长度与最短的输入流（即音频）相同
        # -c:v libx264 -c:a aac: 指定视频和音频编解码器
        # -pix_fmt yuv420p: 指定像素格式，以获得更好的兼容性
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=640x360', 
            '-i', audio_file, '-shortest', '-c:v', 'libx264', '-c:a', 'aac', 
            '-pix_fmt', 'yuv420p', output_video
        ]
        # 运行FFmpeg命令，并捕获输出
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"🎵➡️🎬 Converted <{audio_file}> to <{output_video}> with FFmpeg\n")
        # 转换完成后删除原始音频文件
        os.remove(audio_file)
    return output_video
