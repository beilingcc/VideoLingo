# -*- coding: utf-8 -*-
"""
将字幕硬编码（烧录）到视频中的模块

本模块利用强大的 `ffmpeg` 工具，将先前生成的SRT字幕文件（包括源语言和翻译语言）
嵌入到原始视频中，生成一个带有永久字幕的新视频文件。这个过程通常被称为“硬字幕”或“烧录”。

核心功能:
1.  **跨平台字体支持 (Cross-Platform Font Support)**:
    - 自动检测操作系统（Linux, macOS, Windows），并选择合适的默认字体
      （如 Noto Sans CJK, Arial Unicode MS, Arial）以确保中文字符能正确显示。
    - 用户可以在模块顶部的常量区域自定义字体名称和大小。

2.  **动态FFmpeg命令构建 (Dynamic FFmpeg Command Building)**:
    - `merge_subtitles_to_video` 函数是主要的工作流程。
    - 它首先定位原始视频文件，并使用 `cv2` (OpenCV) 获取视频的原始分辨率。
    - 接着，它构建一个复杂的 `ffmpeg` 命令字符串。这个命令包含以下关键部分：
      a. **视频滤镜 (`-vf`)**: 这是命令的核心，包含一个滤镜链（filter chain）。
      b. `scale` 和 `pad`: 确保视频被缩放并填充到目标分辨率，同时保持原始宽高比，
         避免画面拉伸变形。
      c. `subtitles`: 这个滤镜被调用两次，一次用于源语言SRT，一次用于翻译SRT。
         - `force_style`: 这是一个非常重要的参数，允许我们精细地控制字幕的
           外观，包括字体大小 (`FontSize`)、字体名称 (`FontName`)、颜色 (`PrimaryColour`)、
           边框 (`OutlineColour`, `OutlineWidth`)、阴影 (`ShadowColour`)、背景框
           (`BackColour`)、对齐方式 (`Alignment`) 和垂直边距 (`MarginV`)。
         - 通过为源语言和翻译语言字幕设置不同的样式，可以轻松地区分它们。

3.  **GPU加速支持 (GPU Acceleration)**:
    - `check_gpu_available` 函数通过检查 `ffmpeg` 的编码器列表，判断是否支持
      NVIDIA 的 `h264_nvenc` 编码器。
    - 如果用户在配置文件中启用了 `ffmpeg_gpu` 选项，并且系统支持，则会在 `ffmpeg`
      命令中添加 `-c:v h264_nvenc` 参数，利用GPU进行视频编码，极大地加快处理速度。

4.  **条件执行与占位符视频 (Conditional Execution & Placeholder Video)**:
    - 模块会检查配置文件中的 `burn_subtitles` 标志。
    - 如果该标志为 `False`，则不会执行耗时的字幕烧录过程。相反，它会使用 `cv2`
      快速生成一个1秒钟的黑色视频作为占位符。这在某些工作流中非常有用，
      例如当用户只想生成音频或单独的字幕文件时。

5.  **健壮的进程管理 (Robust Process Management)**:
    - 使用 `subprocess.Popen` 异步启动 `ffmpeg` 进程，允许程序在等待期间
      可以执行其他任务（虽然在此脚本中未使用）。
    - 使用 `try...except` 块来捕获执行过程中的异常，并确保在发生错误时
      能够终止 `ffmpeg` 进程，避免产生僵尸进程。

使用方法:
  直接运行此脚本 (`python -m core._7_sub_into_vid`)，它会：
  1. 查找项目目录下的视频文件。
  2. 检查 `output` 目录中是否存在 `src.srt` 和 `trans.srt`。
  3. 根据配置决定是烧录字幕还是生成占位符视频。
  4. 执行 `ffmpeg` 命令，并在 `output` 目录中生成 `output_sub.mp4`。
"""

import os, subprocess, time, platform, re
from core._1_ytdlp import find_video_files
from core.utils import *

# ------------------ Helper Functions ------------------

def get_video_info(video_path: str) -> dict:
    """使用 ffprobe 高效获取视频信息，避免使用cv2。"""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration,nb_frames',
            '-of', 'csv=p=0:s=x'
        ]
        result = subprocess.run(cmd + [video_path], capture_output=True, text=True, check=True, encoding='utf-8')
        width, height, duration_str, total_frames_str = result.stdout.strip().split('x')
        duration_sec = float(duration_str)
        total_frames = int(total_frames_str) if total_frames_str.isdigit() and int(total_frames_str) > 0 else int(duration_sec * 25) # Fallback for streams without frame count

        # 将时长转换为 HH:MM:SS 格式
        td = timedelta(seconds=duration_sec)

        return {
            'width': int(width),
            'height': int(height),
            'duration_seconds': duration_sec,
            'duration_str': str(td),
            'total_frames': total_frames
        }
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as e:
        console.print(f"[bold red]❌ 错误：无法使用 ffprobe 获取视频信息。请确保 ffmpeg 已正确安装并位于系统PATH中。[/bold red]")
        console.print(f"[yellow]  - 错误详情: {e}[/yellow]")
        return None

def check_gpu_available() -> bool:
    """检查系统中 'ffmpeg' 是否支持 'h264_nvenc' GPU编码器。"""
    try:
        result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, check=True, encoding='utf-8')
        return 'h264_nvenc' in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_platform_font() -> tuple[str, str]:
    """根据操作系统和配置获取字体名称。"""
    default_font = load_key("subtitle_styles.font_name", default="Arial")
    src_font = load_key("subtitle_styles.src.font_name", default=default_font)
    trans_font = load_key("subtitle_styles.trans.font_name", default=default_font)

    if platform.system() == 'Linux':
        linux_font = 'Noto Sans CJK SC'
        src_font = src_font if src_font != 'Arial' else linux_font
        trans_font = trans_font if trans_font != 'Arial' else linux_font
    elif platform.system() == 'Darwin':
        mac_font = 'Arial Unicode MS'
        src_font = src_font if src_font != 'Arial' else mac_font
        trans_font = trans_font if trans_font != 'Arial' else mac_font
    
    return src_font, trans_font

def build_ffmpeg_command(video_path: str, output_path: str, src_srt: str, trans_srt: str) -> list:
    """构建功能强大且可配置的FFmpeg命令。"""
    src_font, trans_font = get_platform_font()

    # 从配置加载样式，提供合理的默认值
    src_style = load_key("subtitle_styles.src", default={})
    trans_style = load_key("subtitle_styles.trans", default={})

    # 构建源字幕样式字符串
    style_src_args = {
        'FontName': src_font,
        'FontSize': src_style.get('font_size', 15),
        'PrimaryColour': src_style.get('color', '&HFFFFFF'),
        'OutlineColour': src_style.get('outline_color', '&H000000'),
        'Outline': src_style.get('outline_width', 1),
        'Shadow': src_style.get('shadow', 1),
        'MarginV': src_style.get('margin_v', 50)
    }
    style_src_str = ','.join([f"{k}={v}" for k, v in style_src_args.items()])

    # 构建翻译字幕样式字符串
    style_trans_args = {
        'FontName': trans_font,
        'FontSize': trans_style.get('font_size', 17),
        'PrimaryColour': trans_style.get('color', '&H00FFFF'),
        'OutlineColour': trans_style.get('outline_color', '&H000000'),
        'Outline': trans_style.get('outline_width', 1),
        'BackColour': trans_style.get('back_color', '&H33000000'),
        'BorderStyle': 4, # 4 for background box
        'Alignment': 2, # 2 for bottom center
        'MarginV': trans_style.get('margin_v', 25)
    }
    style_trans_str = ','.join([f"{k}={v}" for k, v in style_trans_args.items()])

    video_filter = f"subtitles='{src_srt.replace('\\', '/')}':force_style='{style_src_str}',subtitles='{trans_srt.replace('\\', '/')}':force_style='{style_trans_str}'"

    cmd = ['ffmpeg', '-i', video_path, '-vf', video_filter, '-c:a', 'copy']

    if load_key("ffmpeg_gpu") and check_gpu_available():
        console.log("[green]  - 检测到NVIDIA GPU，使用NVENC硬件加速。[/green]")
        cmd.extend(['-c:v', 'h264_nvenc'])
    else:
        console.log("[yellow]  - 未使用GPU加速，将使用CPU进行编码。[/yellow]")
        cmd.extend(['-c:v', 'libx264'])
    
    cmd.extend(['-y', output_path])
    return cmd

def run_ffmpeg_with_progress(command: list, total_duration_sec: float) -> bool:
    """执行FFmpeg命令并使用rich.Progress实时显示进度。"""
    try:
        with Progress(SpinnerColumn(), *Progress.get_default_columns(), "Time Remaining:", TimeRemainingColumn(), transient=True) as progress:
            task = progress.add_task("[cyan]烧录字幕中...[/cyan]", total=total_duration_sec)
            
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', errors='ignore')
            
            ffmpeg_output = ""
            for line in process.stdout:
                ffmpeg_output += line
                match = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                if match:
                    hours, minutes, seconds, hundredths = map(int, match.groups())
                    elapsed_time = hours * 3600 + minutes * 60 + seconds + hundredths / 100.0
                    progress.update(task, completed=elapsed_time)

            process.wait()
            progress.update(task, completed=total_duration_sec)

            if process.returncode == 0:
                console.log(f"[green]✅ FFmpeg执行成功！[/green]")
                return True
            else:
                console.print(Panel(f"[bold red]❌ FFmpeg 执行出错。返回码: {process.returncode}[/bold red]", title="错误", border_style="red"))
                console.print(f"[yellow]FFmpeg 完整输出:[/yellow]")
                console.print(ffmpeg_output)
                return False

    except FileNotFoundError:
        console.print("[bold red]❌ 错误：找不到 'ffmpeg'。请确保它已安装并位于系统的PATH中。[/bold red]")
        return False
    except Exception as e:
        console.print(f"[bold red]❌ 执行过程中发生未知错误: {e}[/bold red]")
        return False

# ------------------ Main Function -------------------

@check_file_exists(load_key("paths.subtitled_video"))
def sub_into_vid_main():
    """主函数，负责将SRT字幕文件硬编码到视频中。"""
    console.print(Panel("[bold cyan]📹 开始将字幕烧录进视频...[/bold cyan]", title="第七步：字幕烧录", expand=False))

    # 步骤 1: 检查配置和输入文件
    console.log("[cyan]▶ 步骤 1/4: 检查配置和输入文件...[/cyan]")
    video_file = find_video_files()
    if not video_file:
        console.print("[bold red]错误：在项目中未找到视频文件。[/bold red]")
        return

    output_video_path = load_key("paths.subtitled_video")
    os.makedirs(os.path.dirname(output_video_path), exist_ok=True)

    if not load_key("burn_subtitles"):
        console.log("[yellow]- 配置中已禁用字幕烧录，将生成一个黑色占位符视频。[/yellow]")
        width, height = 1920, 1080
        duration = 1
        cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', f'color=c=black:s={width}x{height}:d={duration}',
            '-vf', 'fps=1', '-c:v', 'libx264', '-t', str(duration), '-y', output_video_path
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
            console.log(f"[green]  ✅ 占位符视频已生成: {output_video_path}[/green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]❌ 生成占位符视频失败。[/bold red]")
            console.print(Panel(e.stderr, title="FFmpeg Error", border_style="red"))
        return

    src_srt_path = load_key("paths.srt_src")
    trans_srt_path = load_key("paths.srt_trans")
    if not os.path.exists(src_srt_path) or not os.path.exists(trans_srt_path):
        console.print(f"[bold red]错误：在输出目录中找不到必需的SRT字幕文件 ({src_srt_path}, {trans_srt_path})。[/bold red]")
        return
    console.log("[green]✅ 配置和文件检查通过。[/green]")

    # 步骤 2: 获取视频信息并构建FFmpeg命令
    console.log("[cyan]▶ 步骤 2/4: 构建FFmpeg命令...[/cyan]")
    video_info = get_video_info(video_file)
    if not video_info:
    else:
        console.print("[yellow]  - 未使用GPU加速。[/yellow]")
        ffmpeg_cmd.extend(['-c:v', 'libx264'])
    ffmpeg_cmd.extend(['-y', OUTPUT_VIDEO])
    console.print("[green]  ✅ FFmpeg命令构建完成。[/green]")

    # 步骤 3: 执行FFmpeg命令
    console.print("[cyan]- 步骤 3/4: 开始执行FFmpeg，这可能需要一些时间...[/cyan]")
    start_time = time.time()
    try:
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        stdout, stderr = process.communicate()
        if process.returncode == 0:
            console.print(f"[green]  ✅ FFmpeg执行成功！总耗时: {time.time() - start_time:.2f} 秒[/green]")
        else:
            console.print(f"[bold red]❌ FFmpeg 执行出错。返回码: {process.returncode}[/bold red]")
            console.print("[yellow]FFmpeg 错误输出:[/yellow]")
            console.print(stderr)
            return
    except FileNotFoundError:
        console.print("[bold red]❌ 错误：找不到 'ffmpeg'。请确保它已安装并位于系统的PATH中。[/bold red]")
        return
    except Exception as e:
        console.print(f"[bold red]❌ 执行过程中发生未知错误: {e}[/bold red]")
        return

    # 步骤 4: 完成
    console.print("[cyan]- 步骤 4/4: 字幕烧录完成。[/cyan]")
    console.print(Panel(f"[bold green]🎉 字幕烧录流程成功完成！[/bold green]", subtitle=f"输出文件位于: {os.path.abspath(OUTPUT_VIDEO)}", expand=False))

if __name__ == "__main__":
    sub_into_vid_main()