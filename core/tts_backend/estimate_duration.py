# 导入所需库
import syllables  # 用于估算英文单词的音节数
from pypinyin import pinyin, Style  # 用于获取汉字的拼音，从而计算音节数
from g2p_en import G2p  # 英文音素转换库，作为syllables库的备用方案
from typing import Optional  # 用于类型提示
import re  # 正则表达式库，用于文本匹配和处理

class AdvancedSyllableEstimator:
    """
    一个高级的音节和时长估算器，能够处理多种语言和混合文本。
    """
    def __init__(self):
        """
        初始化估算器，加载所需模型和配置参数。
        """
        self.g2p_en = G2p()  # 初始化英文音素转换器
        # 定义不同语言每个音节的平均时长（秒）
        self.duration_params = {'en': 0.225, 'zh': 0.21, 'ja': 0.21, 'fr': 0.22, 'es': 0.22, 'ko': 0.21, 'default': 0.22}
        # 定义用于检测不同语言的正则表达式模式
        self.lang_patterns = {
            'zh': r'[\u4e00-\u9fff]',  # 匹配中文字符
            'ja': r'[\u3040-\u309f\u30a0-\u30ff]',  # 匹配日文假名
            'fr': r'[àâçéèêëîïôùûüÿœæ]',  # 匹配法文特有字符
            'es': r'[áéíóúñ¿¡]',  # 匹配西班牙文特有字符
            'en': r'[a-zA-Z]+',  # 匹配英文字母
            'ko': r'[\uac00-\ud7af\u1100-\u11ff]'  # 匹配韩文字符
        }
        # 定义不同语言文本片段之间的连接符
        self.lang_joiners = {'zh': '', 'ja': '', 'en': ' ', 'fr': ' ', 'es': ' ', 'ko': ' '}
        # 定义标点符号和停顿时间
        self.punctuation = {
            'mid': r'[，；：,;、]+',  # 句中标点
            'end': r'[。！？.!?]+',  # 句末标点
            'space': r'\s+',  # 空格
            'pause': {'space': 0.15, 'default': 0.1}  # 不同类型停顿的默认时长（秒）
        }

    def estimate_duration(self, text: str, lang: Optional[str] = None) -> float:
        """
        估算单语言文本的朗读时长。
        """
        syllable_count = self.count_syllables(text, lang)
        return syllable_count * self.duration_params.get(lang or 'default')

    def count_syllables(self, text: str, lang: Optional[str] = None) -> int:
        """
        计算给定文本的音节数，支持多种语言。
        """
        if not text.strip(): return 0
        lang = lang or self._detect_language(text)  # 如果未指定语言，则自动检测
        
        vowels_map = {  # 法语和西班牙语的元音，用于音节估算
            'fr': 'aeiouyàâéèêëîïôùûüÿœæ',
            'es': 'aeiouáéíóúü'
        }
        
        if lang == 'en':
            return self._count_english_syllables(text)
        elif lang == 'zh':
            text = re.sub(r'[^\u4e00-\u9fff]', '', text)  # 只保留汉字
            return len(pinyin(text, style=Style.NORMAL))  # 计算拼音数量
        elif lang == 'ja':
            text = re.sub(r'[きぎしじちぢにひびぴみり][ょゅゃ]', 'X', text)  # 处理拗音
            text = re.sub(r'[っー]', '', text)  # 去掉促音和长音符号
            return len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text)) # 计算假名和汉字数量
        elif lang in ('fr', 'es'):
            text = re.sub(r'e\b', '', text.lower()) if lang == 'fr' else text.lower()  # 法语词末的e通常不发音
            return max(1, len(re.findall(f'[{vowels_map[lang]}]+', text))) # 通过元音簇估算音节
        elif lang == 'ko':
            return len(re.findall(r'[\uac00-\ud7af]', text))  # 韩文一个字符为一个音节
        return len(text.split())  # 默认按空格分割单词数作为音节数

    def _count_english_syllables(self, text: str) -> int:
        """
        专门计算英文文本的音节数。
        """
        total = 0
        for word in text.strip().split():
            try:
                total += syllables.estimate(word)  # 优先使用syllables库
            except:
                phones = self.g2p_en(word)  # 失败则使用g2p库
                total += max(1, len([p for p in phones if any(c in p for c in 'aeiou')])) # 计算音素中的元音数量
        return max(1, total)

    def _detect_language(self, text: str) -> str:
        """
        根据文本中的特征字符检测主要语言。
        """
        for lang, pattern in self.lang_patterns.items():
            if re.search(pattern, text):
                return lang
        return 'en'  # 默认返回英文

    def process_mixed_text(self, text: str) -> dict:
        """
        处理包含多种语言和标点符号的混合文本，估算总时长和各项参数。
        """
        if not text or not isinstance(text, str):
            return {'language_breakdown': {}, 'total_syllables': 0, 'punctuation': [], 'spaces': [], 'estimated_duration': 0}
            
        result = {'language_breakdown': {}, 'total_syllables': 0, 'punctuation': [], 'spaces': []}
        # 按标点和空格分割文本
        segments = re.split(f"({self.punctuation['space']}|{self.punctuation['mid']}|{self.punctuation['end']})", text)
        total_duration = 0
        
        for i, segment in enumerate(segments):
            if not segment: continue
            
            # 处理空格
            if re.match(self.punctuation['space'], segment):
                prev_lang = self._detect_language(segments[i-1]) if i > 0 else None
                next_lang = self._detect_language(segments[i+1]) if i < len(segments)-1 else None
                # 如果空格两边是中日韩等无空格连接的语言，则视为空格停顿
                if prev_lang and next_lang and (self.lang_joiners[prev_lang] == '' or self.lang_joiners[next_lang] == ''):
                    result['spaces'].append(segment)
                    total_duration += self.punctuation['pause']['space']
            # 处理标点
            elif re.match(f"{self.punctuation['mid']}|{self.punctuation['end']}", segment):
                result['punctuation'].append(segment)
                total_duration += self.punctuation['pause']['default']
            # 处理文本片段
            else:
                lang = self._detect_language(segment)
                if lang:
                    syllables_count = self.count_syllables(segment, lang)
                    if lang not in result['language_breakdown']:
                        result['language_breakdown'][lang] = {'syllables': 0, 'text': ''}
                    result['language_breakdown'][lang]['syllables'] += syllables_count
                    result['language_breakdown'][lang]['text'] += (self.lang_joiners[lang] + segment 
                        if result['language_breakdown'][lang]['text'] else segment)
                    result['total_syllables'] += syllables_count
                    total_duration += syllables_count * self.duration_params.get(lang, self.duration_params['default'])
        
        result['estimated_duration'] = total_duration
        return result
    
def init_estimator():
    """
    工厂函数，用于创建并返回一个AdvancedSyllableEstimator实例。
    """
    return AdvancedSyllableEstimator()

def estimate_duration(text: str, estimator: AdvancedSyllableEstimator):
    """
    一个便捷函数，用于直接获取混合文本的估算时长。
    """
    if not text or not isinstance(text, str):
        return 0
    return estimator.process_mixed_text(text)['estimated_duration']

# --- 使用示例 ---
if __name__ == "__main__":
    estimator = init_estimator()
    print(f"'你好' 的估算时长: {estimate_duration('你好', estimator):.2f}s")

    # 测试用例
    test_cases = [
        "Hello world this is a test",  # 纯英文
        "你好世界 这是一个测试",      # 中文带空格
        "Hello 你好 world 世界",      # 中英混合
        "The weather is nice, 所以我们去公园。",  # 中英混合带标点
        "我们需要在输出中体现空格的停顿时间",
        "I couldn't help but notice the vibrant colors of the autumn leaves cascading gently from the trees.", # 长英文句子
        "가을 나뭇잎이 부드럽게 떨어지는 생생한 색깔을 주목하지 않을 수 없었다" # 韩文句子
    ]
    
    for text in test_cases:
        result = estimator.process_mixed_text(text)
        print(f"\n--- 分析文本: '{text}' ---")
        print(f"总音节数: {result['total_syllables']}")
        print(f"估算总时长: {result['estimated_duration']:.2f}s")
        print("语言分解:")
        for lang, info in result['language_breakdown'].items():
            print(f"- {lang.upper()}: {info['syllables']} 音节 ({info['text']})")
        if result['punctuation']:
            print(f"检测到的标点: {''.join(result['punctuation'])}")
        if result['spaces']:
            print(f"作为停顿处理的空格数: {len(result['spaces'])}")