# 导入标准库
import os  # 用于处理文件和目录路径
import streamlit as st  # Streamlit库，用于创建Web应用
import io, zipfile  # 用于在内存中创建和处理ZIP文件

# 导入项目内部模块
from core.st_utils.download_video_section import download_video_section  # 导入视频下载/上传UI部分
from core.st_utils.sidebar_setting import page_setting  # 导入页面设置函数
from translations.translations import translate as t  # 导入翻译函数

def download_subtitle_zip_button(text: str):
    """
    创建一个下载按钮，用于将 'output' 目录下的所有SRT字幕文件打包成一个ZIP文件供用户下载。

    Args:
        text (str): 下载按钮上显示的文本。
    """
    zip_buffer = io.BytesIO()  # 在内存中创建一个字节缓冲区来存储ZIP文件
    output_dir = "output"  # 字幕文件所在的目录
    
    # 使用zipfile库创建一个ZIP文件
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        # 遍历output目录下的所有文件
        for file_name in os.listdir(output_dir):
            if file_name.endswith(".srt"):  # 只处理SRT文件
                file_path = os.path.join(output_dir, file_name)
                # 将SRT文件读入并写入ZIP存档
                with open(file_path, "rb") as file:
                    zip_file.writestr(file_name, file.read())
    
    zip_buffer.seek(0)  # 将缓冲区指针重置到开头，以便读取其内容
    
    # 创建Streamlit下载按钮
    st.download_button(
        label=text,  # 按钮标签
        data=zip_buffer,  # 要下载的数据（ZIP文件内容）
        file_name="subtitles.zip",  # 下载时默认的文件名
        mime="application/zip"  # 文件的MIME类型
    )

# --- Streamlit Markdown和CSS样式 ---

# “在GitHub上点赞”按钮的HTML和CSS
give_star_button = """
<style>
    /* GitHub按钮样式 */
    .github-button {
        display: block;
        width: 100%;
        padding: 0.5em 1em;
        color: #144070; /* 文字颜色 */
        background-color: #d0e0f2; /* 背景颜色 */
        border-radius: 6px; /* 圆角 */
        text-decoration: none; /* 无下划线 */
        font-weight: bold; /* 粗体 */
        text-align: center; /* 文本居中 */
        transition: background-color 0.3s ease, color 0.3s ease; /* 过渡效果 */
        box-sizing: border-box;
    }
    /* 鼠标悬停效果 */
    .github-button:hover {
        background-color: #ffffff; /* 悬停时背景变白 */
        color: #144070; /* 悬停时文字颜色不变 */
    }
</style>
<!-- 按钮的HTML结构 -->
<a href="https://github.com/Huanshere/VideoLingo" target="_blank" style="text-decoration: none;">
    <div class="github-button">
        Star on GitHub 
    </div>
</a>
"""

# 自定义Streamlit按钮（st.button, st.download_button）的CSS样式
button_style = """
<style>
/* 普通按钮样式 */
div.stButton > button:first-child {
    display: block;
    padding: 0.5em 1em;
    color: #144070;
    background-color: transparent; /* 透明背景 */
    text-decoration: none;
    font-weight: bold;
    text-align: center;
    transition: all 0.3s ease;
    box-sizing: border-box;
    border: 2px solid #D0DFF2; /* 边框样式 */
    font-size: 1.2em;
}
/* 普通按钮悬停效果 */
div.stButton > button:hover {
    background-color: transparent;
    color: #144070;
    border-color: #144070; /* 悬停时边框颜色加深 */
}
/* 普通按钮激活/聚焦状态，防止出现默认的背景和阴影 */
div.stButton > button:active, div.stButton > button:focus {
    background-color: transparent !important;
    color: #144070 !important;
    border-color: #144070 !important;
    box-shadow: none !important;
}
div.stButton > button:active:hover, div.stButton > button:focus:hover {
    background-color: transparent !important;
    color: #144070 !important;
    border-color: #144070 !important;
    box-shadow: none !important;
}

/* 下载按钮样式 (与普通按钮类似) */
div.stDownloadButton > button:first-child {
    display: block;
    padding: 0.5em 1em;
    color: #144070;
    background-color: transparent;
    text-decoration: none;
    font-weight: bold;
    text-align: center;
    transition: all 0.3s ease;
    box-sizing: border-box;
    border: 2px solid #D0DFF2;
    font-size: 1.2em;
}
/* 下载按钮悬停效果 */
div.stDownloadButton > button:hover {
    background-color: transparent;
    color: #144070;
    border-color: #144070;
}
/* 下载按钮激活/聚焦状态 */
div.stDownloadButton > button:active, div.stDownloadButton > button:focus {
    background-color: transparent !important;
    color: #144070 !important;
    border-color: #144070 !important;
    box-shadow: none !important;
}
div.stDownloadButton > button:active:hover, div.stDownloadButton > button:focus:hover {
    background-color: transparent !important;
    color: #144070 !important;
    border-color: #144070 !important;
    box-shadow: none !important;
}
</style>
"""