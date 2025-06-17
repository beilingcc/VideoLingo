# -*- coding: utf-8 -*-
"""
视频下载模块 (流水线入口)

本模块是整个视频处理流水线的第一个环节，负责从指定的 URL 下载视频内容。
它构建于强大的 `yt-dlp` 库之上，提供了健壮的视频下载、格式选择和文件管理功能。

核心功能:
- **自动更新依赖**: 在执行下载前，会自动尝试更新 `yt-dlp` 库，以确保对最新视频平台的支持。
- **灵活的视频下载**: 支持指定视频分辨率，能够智能选择最佳的视频和音频流进行合并。
- **Cookie 支持**: 可以加载本地的 Cookie 文件，用于下载需要登录验证的视频内容。
- **文件名净化与管理**: 下载完成后，会自动清理文件名中的非法字符，并进行重命名，确保文件系统的兼容性。
- **精确的文件定位**: 提供一个辅助函数，用于在下载目录中准确地找到目标视频文件，为后续处理步骤提供输入。

使用方法:
  可以直接运行此脚本，并根据提示输入视频 URL 和期望的分辨率来下载视频。
  也可以作为模块导入到主流程中，调用 `download_video_ytdlp` 和 `find_video_files` 函数。
"""

import os
import sys
import glob
import re
import subprocess
from core.utils import *

def sanitize_filename(filename: str) -> str:
    """
    净化并清理文件名，移除操作系统不允许的非法字符。

    Args:
        filename (str): 原始文件名，通常从视频元数据中获取。

    Returns:
        str: 返回一个合法的文件名。如果清理后文件名为空，则返回默认名 'video'。
    """
    # 使用正则表达式移除Windows和Linux系统中常见的非法文件名字符
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # 移除文件名首尾可能存在的点或空格，这在某些文件系统中也是不允许的
    filename = filename.strip('. ')
    # 如果经过处理后文件名变为空字符串，则提供一个默认名称
    return filename if filename else 'video'

def update_ytdlp():
    """
    执行 `yt-dlp` 库的在线更新。
    """
    console.print("[green]  - 检查并更新 yt-dlp...[/green]")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if 'yt_dlp' in sys.modules:
            del sys.modules['yt_dlp']
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]  ⚠️  警告: 更新 yt-dlp 失败: {e}。将使用当前版本继续。[/yellow]")

    from yt_dlp import YoutubeDL
    return YoutubeDL


def download_video_ytdlp(url: str, save_path: str = 'output', resolution: str = '1080'):
    """
    使用 yt-dlp 下载指定 URL 的视频。

    Args:
        url (str): 要下载的视频的 URL。
        save_path (str, optional): 视频和相关文件的保存目录。默认为 'output'。
        resolution (str, optional): 期望的视频分辨率（高度）。默认为 '1080'。
                                  可以设置为 'best' 来获取最高可用分辨率。
    """
    os.makedirs(save_path, exist_ok=True)

    YoutubeDL = update_ytdlp()

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best' if resolution == 'best' else f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]',
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'writethumbnail': True,
        'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
        'progress_hooks': [lambda d: None],  # 禁用默认的下载进度条
    }

    cookies_path = load_key("youtube.cookies_path")
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = str(cookies_path)
        console.print(f"[green]  - 检测到并使用 Cookie 文件: {cookies_path}[/green]")

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    console.print("[green]  - 下载完成，开始净化文件名...[/green]")
    for file in os.listdir(save_path):
        if os.path.isfile(os.path.join(save_path, file)):
            filename, ext = os.path.splitext(file)
            new_filename = sanitize_filename(filename)
            if new_filename != filename:
                try:
                    os.rename(os.path.join(save_path, file), os.path.join(save_path, new_filename + ext))
                except OSError as e:
                    console.print(f"[yellow]  ⚠️  警告: 重命名文件 '{file}' 失败: {e}。[/yellow]")

def find_video_files(save_path: str = 'output') -> str:
    """
    在指定目录中查找并返回唯一的视频文件路径。

    Args:
        save_path (str, optional): 要搜索的目录。默认为 'output'。

    Raises:
        ValueError: 如果在目录中找到的视频文件数量不等于1，则抛出此异常。

    Returns:
        str: 找到的视频文件的完整路径。
    """
    # 根据配置文件中允许的视频格式，查找所有匹配的视频文件
    allowed_formats = load_key("allowed_video_formats", default=['mp4', 'mkv', 'webm'])
    video_files = [file for file in glob.glob(os.path.join(save_path, "*")) if os.path.splitext(file)[1][1:].lower() in allowed_formats]
    
    # 规范化路径分隔符，特别是在 Windows 系统上，统一使用正斜杠 '/' 
    if sys.platform.startswith('win'):
        video_files = [file.replace("\\", "/") for file in video_files]
    
    # 排除可能是之前运行生成的输出文件，避免处理错误的文件
    video_files = [file for file in video_files if not os.path.basename(file).startswith("output")]
    
    # 严格检查，确保只找到了一个视频文件，这是后续流程正确执行的前提
    if len(video_files) != 1:
        raise ValueError(f"错误：在 '{save_path}' 目录中找到了 {len(video_files)} 个视频文件，应为1个。请检查目录内容。")
    
    return video_files[0]

@check_file_exists(_1_YTDLP)
def ytdlp_main():
    """模块作为流水线一部分运行时的主函数入口。"""
    console.print(Panel("[bold cyan]🚀 开始下载视频...[/bold cyan]", title="第一步: 下载视频", expand=False))

    # --- 步骤 1: 加载配置 ---
    console.print("[cyan]- 步骤 1/3: 正在加载配置...[/cyan]")
    url = load_key("video_url")
    if not url or not url.startswith("http"):
        console.print(Panel("[bold red]❌ 配置错误[/bold red]", subtitle="未在配置文件中找到有效的 'video_url'。请配置视频链接。", expand=False))
        return
    resolution = load_key("video_resolution", default='1080')
    console.print(f"[green]  ✅ 配置加载成功: URL='{url}', 分辨率='{resolution}'[/green]")

    # --- 步骤 2: 执行下载 ---
    console.print("[cyan]- 步骤 2/3: 正在执行下载... (这可能需要一些时间)[/cyan]")
    try:
        download_video_ytdlp(url, resolution=resolution)
    except Exception as e:
        console.print(Panel(f"[bold red]❌ 下载失败[/bold red]", subtitle=str(e), expand=False))
        return

    # --- 步骤 3: 验证下载结果 ---
    console.print("[cyan]- 步骤 3/3: 正在验证下载结果...[/cyan]")
    try:
        video_path = find_video_files()
        console.print(Panel(f"[bold green]🎉 视频下载成功！[/bold green]", subtitle=f"视频文件路径: `{video_path}`", expand=False))
    except ValueError as e:
        console.print(Panel(f"[bold red]❌ 下载后验证失败[/bold red]", subtitle=str(e), expand=False))

def ytdlp_main_interactive():
    """模块独立运行时的主函数入口。"""
    console.print(Panel("[bold cyan]交互式视频下载[/bold cyan]", title="第一步: 下载视频", expand=False))
    try:
        url = input('  请输入您想下载的视频 URL: ')
        if not url or not url.startswith("http"):
            console.print("[bold red]❌ 无效的 URL。[/bold red]")
            return
        resolution = input('  请输入期望的分辨率 (例如 360, 720, 1080), 直接回车默认为 1080: ')
        resolution = resolution if resolution.isdigit() else '1080'

        console.print("[cyan]- 正在执行下载... (这可能需要一些时间)[/cyan]")
        download_video_ytdlp(url, resolution=resolution)

        video_path = find_video_files()
        console.print(Panel(f"[bold green]🎉 视频下载成功！[/bold green]", subtitle=f"视频文件路径: `{video_path}`", expand=False))
    except Exception as e:
        console.print(Panel(f"[bold red]❌ 发生错误[/bold red]", subtitle=str(e), expand=False))

if __name__ == '__main__':
    ytdlp_main_interactive()
