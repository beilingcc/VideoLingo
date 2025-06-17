import os
import string
import warnings
from core.spacy_utils.load_nlp_model import init_nlp, SPLIT_BY_CONNECTOR_FILE
from core.utils import *
from core.utils.models import _3_1_SPLIT_BY_NLP

# 忽略未来版本相关的警告，保持输出整洁
warnings.filterwarnings("ignore", category=FutureWarning)

def split_long_sentence(doc):
    """
    使用动态规划，根据语法结构（如动词、句子末端、依存关系根）将长句子切分为更自然的短句。
    目标是让切分后的句子在语法上尽可能完整和连贯。

    Args:
        doc (spacy.Doc): 经过spaCy处理的文档对象。

    Returns:
        list: 由切分后的短句字符串组成的列表。
    """
    # 获取所有词语的文本形式
    tokens = [token.text for token in doc]
    n = len(tokens)
    
    # 初始化动态规划数组。dp[i] 表示从开头到第 i 个词元的最优切分方案（即最少的句子数量）
    dp = [float('inf')] * (n + 1)
    dp[0] = 0  # 初始状态，0个词元不需要切分，代价为0
    
    # prev 数组用于记录最优切分点。prev[i] 表示在第 i 个词元处达到最优切分时，其前一个切分点的位置
    prev = [0] * (n + 1)
    
    # 动态规划主循环
    for i in range(1, n + 1):
        # 内层循环，寻找从 j 到 i 的最佳切分点 j
        # 限制搜索范围，避免生成过长的句子（最多100个词元）
        for j in range(max(0, i - 100), i):
            # 确保切分出的句子长度不小于30个词元，避免产生过多碎片化的短句
            if i - j >= 30:
                token = doc[i-1]  # 获取当前子句的最后一个词元
                # 判断是否为有效的切分点。条件：
                # 1. j=0：句子的开始，总是一个有效的切分点。
                # 2. token.is_sent_end：当前词元是spaCy识别的句子末端（如句号、问号）。
                # 3. token.pos_ in ['VERB', 'AUX']：当前词元是动词或助动词，通常是子句的核心。
                # 4. token.dep_ == 'ROOT'：当前词元是句子的依存关系根，是句子的核心成分。
                if j == 0 or (token.is_sent_end or token.pos_ in ['VERB', 'AUX'] or token.dep_ == 'ROOT'):
                    # 如果通过在 j 点切分，可以得到一个更优的解（即更少的句子数量），则更新dp和prev数组
                    if dp[j] + 1 < dp[i]:
                        dp[i] = dp[j] + 1
                        prev[i] = j
    
    # 根据记录的最优切分点（prev数组），从后向前回溯，重建句子
    sentences = []
    i = n
    # 获取语言配置，以选择正确的连接词（如中文用''，英文用' '）
    whisper_language = load_key("whisper.language")
    language = load_key("whisper.detected_language") if whisper_language == 'auto' else whisper_language
    joiner = get_joiner(language)
    
    while i > 0:
        j = prev[i]
        # 将从 j 到 i 的词元拼接成一个句子
        sentences.append(joiner.join(tokens[j:i]).strip())
        i = j
    
    # 因为是回溯得到的，所以需要反转列表以恢复原始顺序
    return sentences[::-1]

def split_extremely_long_sentence(doc):
    """
    当 `split_long_sentence` 无法找到合适的切分点时（例如，句子结构异常），
    使用此函数进行硬切分，确保每个子句的长度不超过60个词元。
    这是一种备用策略，保证程序不会因超长句子而失败。

    Args:
        doc (spacy.Doc): 经过spaCy处理的文档对象。

    Returns:
        list: 由切分后的短句字符串组成的列表。
    """
    tokens = [token.text for token in doc]
    n = len(tokens)
    
    # 计算需要将句子切分成多少部分，确保每部分长度不超过60
    # (n + 59) // 60 是一种向上取整的技巧
    num_parts = (n + 59) // 60
    
    part_length = n // num_parts
    
    sentences = []
    whisper_language = load_key("whisper.language")
    language = load_key("whisper.detected_language") if whisper_language == 'auto' else whisper_language # consider force english case
    joiner = get_joiner(language)
    for i in range(num_parts):
        start = i * part_length
        end = start + part_length if i < num_parts - 1 else n
        sentence = joiner.join(tokens[start:end])
        sentences.append(sentence)
    
    return sentences


def split_long_by_root_main(nlp):
    with open(SPLIT_BY_CONNECTOR_FILE, "r", encoding="utf-8") as input_file:
        sentences = input_file.readlines()

    all_split_sentences = []
    for sentence in sentences:
        doc = nlp(sentence.strip())
        if len(doc) > 60:
            split_sentences = split_long_sentence(doc)
            if any(len(nlp(sent)) > 60 for sent in split_sentences):
                split_sentences = [subsent for sent in split_sentences for subsent in split_extremely_long_sentence(nlp(sent))]
            all_split_sentences.extend(split_sentences)
            rprint(f"[yellow]✂️  Splitting long sentences by root: {sentence[:30]}...[/yellow]")
        else:
            all_split_sentences.append(sentence.strip())

    punctuation = string.punctuation + "'" + '"'  # include all punctuation and apostrophe ' and "

    with open(_3_1_SPLIT_BY_NLP, "w", encoding="utf-8") as output_file:
        for i, sentence in enumerate(all_split_sentences):
            stripped_sentence = sentence.strip()
            if not stripped_sentence or all(char in punctuation for char in stripped_sentence):
                rprint(f"[yellow]⚠️  Warning: Empty or punctuation-only line detected at index {i}[/yellow]")
                if i > 0:
                    all_split_sentences[i-1] += sentence
                continue
            output_file.write(sentence + "\n")

    # delete the original file
    os.remove(SPLIT_BY_CONNECTOR_FILE)   

    rprint(f"[green]💾 Long sentences split by root saved to →  {_3_1_SPLIT_BY_NLP}[/green]")

if __name__ == "__main__":
    nlp = init_nlp()
    split_long_by_root_main(nlp)
    # raw = "平口さんの盛り上げごまが初めて売れました本当に嬉しいです本当にやっぱり見た瞬間いいって言ってくれるそういうコマを作るのがやっぱりいいですよねその2ヶ月後チコさんが何やらそわそわしていましたなんか気持ち悪いやってきたのは平口さんの駒の評判を聞きつけた愛知県の収集家ですこの男性師匠大沢さんの駒も持っているといいますちょっと褒めすぎかなでも確実にファンは広がっているようです自信がない部分をすごく感じてたのでこれで自信を持って進んでくれるなっていう本当に始まったばっかりこれからいろいろ挑戦していってくれるといいなと思って今月平口さんはある場所を訪れましたこれまで数々のタイトル戦でコマを提供してきた老舗5番手平口さんのコマを扱いたいと言いますいいですねぇ困ってだんだん成長しますので大切に使ってそういう長く良い駒になる駒ですね商談が終わった後店主があるものを取り出しましたこの前の名人戦で使った駒があるんですけど去年、名人銭で使われた盛り上げごま低く盛り上げて品良くするというのは難しい素晴らしいですね平口さんが目指す高みですこういった感じで作れればまだまだですけどただ、多分、咲く。"
    # nlp = init_nlp()
    # doc = nlp(raw.strip())
    # for sent in split_still_long_sentence(doc):
    #     print(sent, '\n==========')
