import json
from core.utils import *

# ------------
# 提示词模板模块
# 包含各个处理阶段所需的AI提示词模板
# ------------

## ================================================================
# @ step4_splitbymeaning.py
def get_split_prompt(sentence, num_parts = 2, word_limit = 20):
    """
    生成用于分割句子的提示词
    
    根据语言和指定的参数，生成一个提示词，用于指导AI将长句子分割成更小的部分，
    同时保持每部分的语义连贯性和合适的长度。
    
    参数:
        sentence (str): 需要分割的句子
        num_parts (int): 要分割成的部分数量，默认为2
        word_limit (int): 每部分的最大单词数，默认为20
        
    返回:
        str: 格式化的提示词
    """
    # 获取检测到的语言
    language = load_key("whisper.detected_language")
    
    # 构建分割提示词
    split_prompt = f"""
## Role
You are a professional Netflix subtitle splitter in **{language}**.

## Task
Split the given subtitle text into **{num_parts}** parts, each less than **{word_limit}** words.

1. Maintain sentence meaning coherence according to Netflix subtitle standards
2. MOST IMPORTANT: Keep parts roughly equal in length (minimum 3 words each)
3. Split at natural points like punctuation marks or conjunctions
4. If provided text is repeated words, simply split at the middle of the repeated words.

## Steps
1. Analyze the sentence structure, complexity, and key splitting challenges
2. Generate two alternative splitting approaches with [br] tags at split positions
3. Compare both approaches highlighting their strengths and weaknesses
4. Choose the best splitting approach

## Given Text
<split_this_sentence>
{sentence}
</split_this_sentence>

## Output in only JSON format and no other text
```json
{{
    "analysis": "Brief description of sentence structure, complexity, and key splitting challenges",
    "split1": "First splitting approach with [br] tags at split positions",
    "split2": "Alternative splitting approach with [br] tags at split positions",
    "assess": "Comparison of both approaches highlighting their strengths and weaknesses",
    "choice": "1 or 2"
}}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
""".strip()
    return split_prompt

"""{{
    "analysis": "Brief analysis of the text structure",
    "split": "Complete sentence with [br] tags at split positions"
}}"""

## ================================================================
# @ step4_1_summarize.py
def get_summary_prompt(source_content, custom_terms_json=None):
    """
    生成用于总结内容和提取术语的提示词
    
    根据源内容和可能的自定义术语，生成一个提示词，用于指导AI总结视频内容
    并提取专业术语及其翻译。
    
    参数:
        source_content (str): 需要总结的源内容文本
        custom_terms_json (dict, optional): 自定义术语的JSON数据，默认为None
        
    返回:
        str: 格式化的提示词
    """
    # 获取源语言和目标语言
    src_lang = load_key("whisper.detected_language")
    tgt_lang = load_key("target_language")
    
    # 添加自定义术语注释
    terms_note = ""
    if custom_terms_json:
        terms_list = []
        for term in custom_terms_json['terms']:
            terms_list.append(f"- {term['src']}: {term['tgt']} ({term['note']})")
        terms_note = "\n### Existing Terms\nPlease exclude these terms in your extraction:\n" + "\n".join(terms_list)
    
    # 构建总结提示词
    summary_prompt = f"""
## Role
You are a video translation expert and terminology consultant, specializing in {src_lang} comprehension and {tgt_lang} expression optimization.

## Task
For the provided {src_lang} video text:
1. Summarize main topic in two sentences
2. Extract professional terms/names with {tgt_lang} translations (excluding existing terms)
3. Provide brief explanation for each term

{terms_note}

Steps:
1. Topic Summary:
   - Quick scan for general understanding
   - Write two sentences: first for main topic, second for key point
2. Term Extraction:
   - Mark professional terms and names (excluding those listed in Existing Terms)
   - Provide {tgt_lang} translation or keep original
   - Add brief explanation
   - Extract less than 15 terms

## INPUT
<text>
{source_content}
</text>

## Output in only JSON format and no other text
{{
  "theme": "Two-sentence video summary",
  "terms": [
    {{
      "src": "{src_lang} term",
      "tgt": "{tgt_lang} translation or original", 
      "note": "Brief explanation"
    }},
    ...
  ]
}}  

## Example
{{
  "theme": "本视频介绍人工智能在医疗领域的应用现状。重点展示了AI在医学影像诊断和药物研发中的突破性进展。",
  "terms": [
    {{
      "src": "Machine Learning",
      "tgt": "机器学习",
      "note": "AI的核心技术，通过数据训练实现智能决策"
    }},
    {{
      "src": "CNN",
      "tgt": "CNN",
      "note": "卷积神经网络，用于医学图像识别的深度学习模型"
    }}
  ]
}}

Note: Start you answer with ```json and end with ```, do not add any other text.
""".strip()
    return summary_prompt

## ================================================================
# @ step5_translate.py & translate_lines.py
def generate_shared_prompt(previous_content_prompt, after_content_prompt, summary_prompt, things_to_note_prompt):
    """
    生成共享的上下文提示词
    
    将前后文本内容、摘要和注意事项组合成一个提示词，用于提供翻译的上下文信息。
    
    参数:
        previous_content_prompt (str): 前文内容
        after_content_prompt (str): 后文内容
        summary_prompt (str): 内容摘要
        things_to_note_prompt (str): 需要注意的事项
        
    返回:
        str: 格式化的共享提示词
    """
    return f'''### Context Information
<previous_content>
{previous_content_prompt}
</previous_content>

<subsequent_content>
{after_content_prompt}
</subsequent_content>

### Content Summary
{summary_prompt}

### Points to Note
{things_to_note_prompt}'''

def get_prompt_faithfulness(lines, shared_prompt):
    """
    生成忠实翻译提示词
    
    生成一个提示词，用于指导AI进行忠实于原文的直译。
    
    参数:
        lines (str): 需要翻译的文本行
        shared_prompt (str): 共享的上下文提示词
        
    返回:
        str: 格式化的忠实翻译提示词
    """
    # 获取目标语言
    TARGET_LANGUAGE = load_key("target_language")
    # 按换行符分割文本行
    line_splits = lines.split('\n')
    
    # 构建JSON字典，包含原文和直译占位符
    json_dict = {}
    for i, line in enumerate(line_splits, 1):
        json_dict[f"{i}"] = {"origin": line, "direct": f"direct {TARGET_LANGUAGE} translation {i}."}
    json_format = json.dumps(json_dict, indent=2, ensure_ascii=False)

    # 获取源语言
    src_language = load_key("whisper.detected_language")
    
    # 构建忠实翻译提示词
    prompt_faithfulness = f'''
## Role
You are a professional Netflix subtitle translator, fluent in both {src_language} and {TARGET_LANGUAGE}, as well as their respective cultures. 
Your expertise lies in accurately understanding the semantics and structure of the original {src_language} text and faithfully translating it into {TARGET_LANGUAGE} while preserving the original meaning.

## Task
We have a segment of original {src_language} subtitles that need to be directly translated into {TARGET_LANGUAGE}. These subtitles come from a specific context and may contain specific themes and terminology.

1. Translate the original {src_language} subtitles into {TARGET_LANGUAGE} line by line
2. Ensure the translation is faithful to the original, accurately conveying the original meaning
3. Consider the context and professional terminology

{shared_prompt}

<translation_principles>
1. Faithful to the original: Accurately convey the content and meaning of the original text, without arbitrarily changing, adding, or omitting content.
2. Accurate terminology: Use professional terms correctly and maintain consistency in terminology.
3. Understand the context: Fully comprehend and reflect the background and contextual relationships of the text.
</translation_principles>

## INPUT
<subtitles>
{lines}
</subtitles>

## Output in only JSON format and no other text
```json
{json_format}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''
    return prompt_faithfulness.strip()


def get_prompt_expressiveness(faithfulness_result, lines, shared_prompt):
    """
    生成表达性翻译提示词
    
    生成一个提示词，用于指导AI在忠实翻译的基础上进行更加自然流畅的意译。
    
    参数:
        faithfulness_result (dict): 忠实翻译的结果
        lines (str): 原始文本行
        shared_prompt (str): 共享的上下文提示词
        
    返回:
        str: 格式化的表达性翻译提示词
    """
    # 获取目标语言
    TARGET_LANGUAGE = load_key("target_language")
    
    # 构建JSON格式，包含原文、直译、反思和自由翻译占位符
    json_format = {
        key: {
            "origin": value["origin"],
            "direct": value["direct"],
            "reflect": "your reflection on direct translation",
            "free": "your free translation"
        }
        for key, value in faithfulness_result.items()
    }
    json_format = json.dumps(json_format, indent=2, ensure_ascii=False)

    # 获取源语言
    src_language = load_key("whisper.detected_language")
    
    # 构建表达性翻译提示词
    prompt_expressiveness = f'''
## Role
You are a professional Netflix subtitle translator and language consultant.
Your expertise lies not only in accurately understanding the original {src_language} but also in optimizing the {TARGET_LANGUAGE} translation to better suit the target language's expression habits and cultural background.

## Task
We already have a direct translation version of the original {src_language} subtitles.
Your task is to reflect on and improve these direct translations to create more natural and fluent {TARGET_LANGUAGE} subtitles.

1. Analyze the direct translation results line by line, pointing out existing issues
2. Provide detailed modification suggestions
3. Perform free translation based on your analysis
4. Do not add comments or explanations in the translation, as the subtitles are for the audience to read
5. Do not leave empty lines in the free translation, as the subtitles are for the audience to read

{shared_prompt}

<Translation Analysis Steps>
Please use a two-step thinking process to handle the text line by line:

1. Direct Translation Reflection:
   - Evaluate language fluency
   - Check if the language style is consistent with the original text
   - Check the conciseness of the subtitles, point out where the translation is too wordy

2. {TARGET_LANGUAGE} Free Translation:
   - Aim for contextual smoothness and naturalness, conforming to {TARGET_LANGUAGE} expression habits
   - Ensure it's easy for {TARGET_LANGUAGE} audience to understand and accept
   - Adapt the language style to match the theme (e.g., use casual language for tutorials, professional terminology for technical content, formal language for documentaries)
</Translation Analysis Steps>
   
## INPUT
<subtitles>
{lines}
</subtitles>

## Output in only JSON format and no other text
```json
{json_format}
```

Note: Start you answer with ```json and end with ```, do not add any other text.
'''
    return prompt_expressiveness.strip()


## ================================================================
# @ step6_splitforsub.py
def get_align_prompt(src_sub, tr_sub, src_part):
    """
    生成字幕对齐提示词
    
    生成一个提示词，用于指导AI将翻译后的字幕与原始字幕进行对齐。
    
    参数:
        src_sub (str): 源字幕
        tr_sub (str): 翻译后的字幕
        src_part (str): 需要对齐的源字幕部分
        
    返回:
        str: 格式化的字幕对齐提示词
    """
    # 获取源语言和目标语言
    src_lang = load_key("whisper.detected_language")
    tgt_lang = load_key("target_language")
    
    # 构建字幕对齐提示词
    align_prompt = f"""
## Role
You are a professional subtitle alignment expert, with deep understanding of both {src_lang} and {tgt_lang}.

## Task
I need you to find the corresponding translation in the translated subtitles for a specific part of the source subtitles.

## Source Subtitles (Complete)
{src_sub}

## Translated Subtitles (Complete)
{tr_sub}

## Source Part to Find Translation For
{src_part}

## Instructions
1. Carefully analyze the source part and find its corresponding translation in the translated subtitles
2. Return ONLY the exact matching translation text, nothing more
3. If there's no clear match, return the closest possible translation
4. DO NOT add any explanations or comments

## Output
Return ONLY the translated text that corresponds to the source part.
"""
    return align_prompt.strip()

## ================================================================
# @ step8_gen_audio_task.py @ step10_gen_audio.py
def get_subtitle_trim_prompt(text, duration):
    """
    生成字幕修剪提示词
    
    生成一个提示词，用于指导AI根据时长限制修剪字幕内容。
    
    参数:
        text (str): 需要修剪的字幕文本
        duration (float): 字幕时长限制（秒）
        
    返回:
        str: 格式化的字幕修剪提示词
    """
    # 获取目标语言
    tgt_lang = load_key("target_language")
    
    # 构建字幕修剪提示词
    trim_prompt = f"""
## Role
You are a professional subtitle editor specializing in {tgt_lang}, with expertise in condensing text while preserving core meaning.

## Task
I have a subtitle that needs to be shortened to fit a specific duration constraint.

## Original Subtitle
{text}

## Duration Constraint
This subtitle must be spoken within {duration:.1f} seconds.

## Instructions
1. Trim the subtitle to make it shorter while preserving the core meaning
2. Remove unnecessary words, phrases, or details
3. Maintain the essential information and key points
4. Ensure the result is natural and fluent in {tgt_lang}
5. The trimmed subtitle should be significantly shorter than the original

## Output
Return ONLY the trimmed subtitle text, nothing more.
"""
    return trim_prompt.strip()


def get_correct_text_prompt(text):
    """
    生成文本纠正提示词
    
    生成一个提示词，用于指导AI纠正文本中的错误。
    
    参数:
        text (str): 需要纠正的文本
        
    返回:
        str: 格式化的文本纠正提示词
    """
    # 获取目标语言
    tgt_lang = load_key("target_language")
    
    # 构建文本纠正提示词
    correct_prompt = f"""
## Role
You are a professional {tgt_lang} language expert with deep knowledge of grammar, spelling, and natural expression.

## Task
I have a piece of text that may contain grammatical errors, awkward phrasing, or unnatural expressions. Please correct it to make it sound natural and fluent in {tgt_lang}.

## Original Text
{text}

## Instructions
1. Fix any grammatical errors
2. Correct spelling mistakes
3. Improve awkward or unnatural phrasing
4. Make the text flow naturally in {tgt_lang}
5. Preserve the original meaning and tone
6. DO NOT add new information or change the meaning

## Output
Return ONLY the corrected text, nothing more.
"""
    return correct_prompt.strip()
