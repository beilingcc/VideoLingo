# 导入所需库
import streamlit as st  # 用于创建Web应用界面
from translations.translations import translate as t, DISPLAY_LANGUAGES  # 导入翻译函数和支持的显示语言
from core.utils import *  # 导入所有自定义工具函数

def config_input(label, key, help=None):
    """
    一个通用的Streamlit文本输入框处理函数，用于更新配置文件。

    当输入框的值发生改变时，会自动调用`update_key`来保存新值。

    Args:
        label (str): 输入框的标签。
        key (str): 在配置文件中对应的键。
        help (str, optional): 输入框的帮助提示文本。 Defaults to None.

    Returns:
        str: 输入框当前的值。
    """
    # 从配置文件加载当前值
    current_value = load_key(key)
    # 创建文本输入框
    new_value = st.text_input(label, value=current_value, help=help)
    # 如果值有变化，则更新配置文件
    if new_value != current_value:
        update_key(key, new_value)
        # 可能需要重新运行以应用更改，但为避免不必要的刷新，此处注释掉
        # st.rerun()
    return new_value

def page_setting():
    """
    在Streamlit侧边栏中渲染所有的页面设置选项。
    包括语言、LLM、字幕和配音等相关配置。
    """

    # --- 显示语言设置 ---
    st.selectbox(
        "Display Language 🌐", 
        options=list(DISPLAY_LANGUAGES.keys()),
        index=list(DISPLAY_LANGUAGES.values()).index(load_key("display_language")),
        key="display_language_selector"
    )
    selected_lang_code = DISPLAY_LANGUAGES[st.session_state.display_language_selector]
    if selected_lang_code != load_key("display_language"):
        update_key("display_language", selected_lang_code)
        st.rerun()  # 语言更改后立即刷新界面

    # --- 大语言模型 (LLM) 配置 ---
    with st.expander(t("LLM Configuration"), expanded=True):
        config_input(t("API_KEY"), "api.key")
        config_input(t("BASE_URL"), "api.base_url", help=t("Openai format, will add /v1/chat/completions automatically"))
        
        col1, col2 = st.columns([4, 1])
        with col1:
            config_input(t("MODEL"), "api.model", help=t("click to check API validity") + " 👉")
        with col2:
            # API有效性检查按钮
            if st.button("📡", key="api_check_button"):
                is_valid = check_api()
                st.toast(
                    t("API Key is valid") if is_valid else t("API Key is invalid"), 
                    icon="✅" if is_valid else "❌"
                )
        
        # LLM是否支持JSON格式输出的开关
        llm_support_json = st.toggle(t("LLM JSON Format Support"), value=load_key("api.llm_support_json"), help=t("Enable if your LLM supports JSON mode output"))
        if llm_support_json != load_key("api.llm_support_json"):
            update_key("api.llm_support_json", llm_support_json)
            st.rerun()

    # --- 字幕设置 ---
    with st.expander(t("Subtitles Settings"), expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            # 语音识别语言选择
            recog_langs = {
                "🇺🇸 English": "en", "🇨🇳 简体中文": "zh", "🇪🇸 Español": "es",
                "🇷🇺 Русский": "ru", "🇫🇷 Français": "fr", "🇩🇪 Deutsch": "de",
                "🇮🇹 Italiano": "it", "🇯🇵 日本語": "ja"
            }
            selected_recog_lang = st.selectbox(
                t("Recog Lang"),
                options=list(recog_langs.keys()),
                index=list(recog_langs.values()).index(load_key("whisper.language"))
            )
            if recog_langs[selected_recog_lang] != load_key("whisper.language"):
                update_key("whisper.language", recog_langs[selected_recog_lang])
                st.rerun()

        # WhisperX运行环境选择 (本地/云端/ElevenLabs)
        runtime = st.selectbox(t("WhisperX Runtime"), options=["local", "cloud", "elevenlabs"], index=["local", "cloud", "elevenlabs"].index(load_key("whisper.runtime")), help=t("Local runtime requires >8GB GPU, cloud runtime requires 302ai API key, elevenlabs runtime requires ElevenLabs API key"))
        if runtime != load_key("whisper.runtime"):
            update_key("whisper.runtime", runtime)
            st.rerun()
        # 根据不同的运行环境，显示对应的API Key输入框
        if runtime == "cloud":
            config_input(t("WhisperX 302ai API"), "whisper.whisperX_302_api_key")
        elif runtime == "elevenlabs":
            config_input(t("ElevenLabs API"), "whisper.elevenlabs_api_key")

        with col2:
            # 目标翻译语言输入
            target_language = st.text_input(t("Target Lang"), value=load_key("target_language"), help=t("Input any language in natural language, as long as llm can understand"))
            if target_language != load_key("target_language"):
                update_key("target_language", target_language)
                st.rerun()

        # 人声分离增强开关
        demucs = st.toggle(t("Vocal separation enhance"), value=load_key("demucs"), help=t("Recommended for videos with loud background noise, but will increase processing time"))
        if demucs != load_key("demucs"):
            update_key("demucs", demucs)
            st.rerun()
        
        # 烧录字幕开关
        burn_subtitles = st.toggle(t("Burn-in Subtitles"), value=load_key("burn_subtitles"), help=t("Whether to burn subtitles into the video, will increase processing time"))
        if burn_subtitles != load_key("burn_subtitles"):
            update_key("burn_subtitles", burn_subtitles)
            st.rerun()

    # --- 配音设置 ---
    with st.expander(t("Dubbing Settings"), expanded=True):
        tts_methods = ["azure_tts", "openai_tts", "fish_tts", "sf_fish_tts", "edge_tts", "gpt_sovits", "custom_tts", "sf_cosyvoice2", "f5tts"]
        select_tts = st.selectbox(t("TTS Method"), options=tts_methods, index=tts_methods.index(load_key("tts_method")))
        if select_tts != load_key("tts_method"):
            update_key("tts_method", select_tts)
            st.rerun()

        # --- 不同TTS方法的子设置 ---
        if select_tts == "sf_fish_tts":
            config_input(t("SiliconFlow API Key"), "sf_fish_tts.api_key")
            mode_options = {"preset": t("Preset"), "custom": t("Refer_stable"), "dynamic": t("Refer_dynamic")}
            selected_mode = st.selectbox(t("Mode Selection"), options=list(mode_options.keys()), format_func=lambda x: mode_options[x], index=list(mode_options.keys()).index(load_key("sf_fish_tts.mode")) if load_key("sf_fish_tts.mode") in mode_options.keys() else 0)
            if selected_mode != load_key("sf_fish_tts.mode"):
                update_key("sf_fish_tts.mode", selected_mode)
                st.rerun()
            if selected_mode == "preset":
                config_input("Voice", "sf_fish_tts.voice")

        elif select_tts == "openai_tts":
            config_input("302ai API", "openai_tts.api_key")
            config_input(t("OpenAI Voice"), "openai_tts.voice")

        elif select_tts == "fish_tts":
            config_input("302ai API", "fish_tts.api_key")
            character_dict = load_key("fish_tts.character_id_dict")
            fish_tts_character = st.selectbox(t("Fish TTS Character"), options=list(character_dict.keys()), index=list(character_dict.keys()).index(load_key("fish_tts.character")))
            if fish_tts_character != load_key("fish_tts.character"):
                update_key("fish_tts.character", fish_tts_character)
                st.rerun()

        elif select_tts == "azure_tts":
            config_input("302ai API", "azure_tts.api_key")
            config_input(t("Azure Voice"), "azure_tts.voice")
        
        elif select_tts == "gpt_sovits":
            st.info(t("Please refer to Github homepage for GPT_SoVITS configuration"))
            config_input(t("SoVITS Character"), "gpt_sovits.character")
            refer_mode_options = {1: t("Mode 1: Use provided reference audio only"), 2: t("Mode 2: Use first audio from video as reference"), 3: t("Mode 3: Use each audio from video as reference")}
            selected_refer_mode = st.selectbox(t("Refer Mode"), options=list(refer_mode_options.keys()), format_func=lambda x: refer_mode_options[x], index=list(refer_mode_options.keys()).index(load_key("gpt_sovits.refer_mode")), help=t("Configure reference audio mode for GPT-SoVITS"))
            if selected_refer_mode != load_key("gpt_sovits.refer_mode"):
                update_key("gpt_sovits.refer_mode", selected_refer_mode)
                st.rerun()
                
        elif select_tts == "edge_tts":
            config_input(t("Edge TTS Voice"), "edge_tts.voice")

        elif select_tts == "sf_cosyvoice2":
            config_input(t("SiliconFlow API Key"), "sf_cosyvoice2.api_key")
        
        elif select_tts == "f5tts":
            config_input("302ai API", "f5tts.302_api")

def check_api():
    """
    通过向配置的LLM发送一个测试请求来检查API密钥和URL的有效性。

    Returns:
        bool: 如果API响应成功且内容符合预期，则返回True，否则返回False。
    """
    try:
        # 发送一个测试prompt，期望得到一个包含 'message':'success' 的JSON响应
        resp = ask_gpt("This is a test, response 'message':'success' in json format.", 
                      resp_type="json", log_title='None')
        # 检查响应是否符合预期
        return resp.get('message') == 'success'
    except Exception:
        # 捕获任何异常（如网络错误、认证失败等）
        return False
    
# 当该脚本作为主程序运行时，执行API检查（主要用于测试）
if __name__ == "__main__":
    check_api()
