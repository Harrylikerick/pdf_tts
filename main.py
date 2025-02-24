import re
import os
from gtts import gTTS
import fitz  # PyMuPDF
import logging
import time
import requests

# 代理设置
PROXY = {
    'http': 'http://127.0.0.1:7890',  # 默认代理地址和端口
    'https': 'http://127.0.0.1:7890'
}

def convert_sanskrit_to_romanian(text):
    """Convert Sanskrit romanization to Romanian phonetic text"""
    conversions = {
        'ā': 'a', 'ṭ': 't', 'ḍ': 'd', 'ṇ': 'n',
        'ṣ': 'ș', 'ś': 'ș', 'ḥ': 'h', 'ṃ': 'm',
        'ñ': 'ni', 'ṅ': 'ng', 'th': 't', 'dh': 'd',
        'ph': 'p', 'bh': 'b', 'r̥': 'rî', 'l̥': 'lî',
        'ai': 'ai', 'au': 'au', 'svāhā': 'svaha',
        'tadyathā': 'tadiata'
    }
    
    result = text
    for sanskrit, romanian in conversions.items():
        result = result.replace(sanskrit, romanian)
    return result

def sanitize_filename(title):
    """Sanitize title to create a valid filename, removing more noise."""
    # 移除所有非字母数字字符、空格、下划线和连字符
    filename = re.sub(r'[^\w\s-]', '', title).strip()
    # 移除标题中的 "卍" 字符
    filename = filename.replace('卍', '').strip()
    # 移除标题中类似 "M05.xx" 的编号
    filename = re.sub(r'M05\.\d+', '', filename).strip()
    # 移除标题中类似 "(xx 卷)" 的卷数信息
    filename = re.sub(r'\(.\d+ 卷\)', '', filename).strip()
    # 移除标题中类似 "〖唐.+译〗" 的译者信息
    filename = re.sub(r'〖唐.+译〗', '', filename).strip()
    filename = re.sub(r'〖元.+译〗', '', filename).strip()
    filename = re.sub(r'〖隋.+译〗', '', filename).strip()
    filename = re.sub(r'〖刘宋.+译〗', '', filename).strip()
    # 移除标题中类似 "大正藏第xx 册No. xxxx[A-Z]" 的信息
    filename = re.sub(r'大正藏第.+', '', filename).strip()
    # 移除标题中类似 "CBETA 佛经： T\d+ , \d+ , \d+ , .+" 的信息
    filename = re.sub(r'CBETA 佛经：.+', '', filename).strip()
    # 移除标题中类似 "No. xxxx[A-Z]" 的信息
    filename = re.sub(r'No\. \d+[A-Z]?', '', filename).strip()
    filename = re.sub(r'No \d+[A-Z]?', '', filename).strip()
    # 移除多余的 "卷" 字
    filename = filename.replace('卷', '').strip()
    # 将空格替换为下划线
    filename = filename.replace(' ', '_')
    # 限制文件名长度 (可选)
    filename = filename[:200]
    return filename

def extract_romanized_text_from_pdf(file_path):
    """Extract Romanized Sanskrit text from the PDF."""
    romanized_texts = []
    titles = []
    
    try:
        pdf_document = fitz.open(file_path)
        current_title = ""
        current_text = ""
        is_mantra_block = False
        in_title = False
        
        for page_num, page in enumerate(pdf_document):
            page_dict = page.get_text("dict")
            blocks = page_dict['blocks']
            
            for block in blocks:
                if block['type'] == 0:  # 文本块
                    for line in block['lines']:
                        for span in line['spans']:
                            if span['color'] != 0:  # 不是黑色文本
                                continue
                                
                            text = span['text'].strip()
                            if not text:
                                continue
                            
                            # 检查是否为标题开始
                            is_title_start = bool(
                                re.search(r'M05\.\d+|陀罗尼|咒|真言', text) or
                                ('卍' in text and len(text) < 100)
                            )
                            
                            # 检查是否为标题的括号部分
                            is_title_bracket = bool(
                                in_title and 
                                (text.startswith('(') or text.endswith(')') or 
                                 re.search(r'[（）()]|陀罗尼|咒|真言', text))
                            )
                            
                            if is_title_start or is_title_bracket:
                                # 如果当前有咒语文本，保存它
                                if current_text:
                                    cleaned_text = clean_mantra_text(current_text)
                                    if cleaned_text:
                                        romanized_texts.append(cleaned_text)
                                        titles.append(clean_title(current_title) if current_title else f"Section {len(romanized_texts) + 1}")
                                    current_text = ""
                                
                                # 处理标题
                                if is_title_start:
                                    if current_title and not is_title_bracket:  # 如果是新标题
                                        current_title = text
                                    else:
                                        current_title = (current_title + " " + text).strip()
                                    in_title = True
                                elif is_title_bracket:
                                    current_title = (current_title + " " + text).strip()
                                
                                is_mantra_block = True
                                continue
                            
                            # 如果不是标题相关文本，结束标题处理模式
                            if in_title and not is_title_bracket:
                                in_title = False
                            
                            # 检查是否包含梵文字符或罗马字母
                            has_sanskrit = bool(re.search(r'[āīūṛṝḷḹēōṭḍṇṣśḥṃñṅ]', text))  # 添加更多梵文字符
                            is_roman = bool(re.match(r'^[a-zA-Z\s]+$', text))
                            
                            if has_sanskrit or is_roman:
                                if is_mantra_block:
                                    current_text += " " + text
                    
                    # 每个块结束时，如果有标题，清理标题
                    if current_title and not in_title:
                        current_title = clean_title(current_title)
        
        # 处理最后一个咒语块
        if current_text:
            cleaned_text = clean_mantra_text(current_text)
            if cleaned_text:
                romanized_texts.append(cleaned_text)
                titles.append(clean_title(current_title) if current_title else f"Section {len(romanized_texts) + 1}")
        
        pdf_document.close()
        return romanized_texts, titles
        
    except Exception as e:
        logging.error(f"Error processing PDF: {str(e)}")
        return [], []

def clean_mantra_text(text):
    """Clean and format mantra text."""
    # 移除单独的 j 和 t (前后有空格的)
    text = re.sub(r'\s+[jt]\s+', ' ', text)
    text = re.sub(r'\s+[jt]$', '', text)
    text = re.sub(r'^[jt]\s+', '', text)
    
    # 只保留罗马字母、特殊音标字符和空格
    cleaned = re.sub(r'[^a-zA-Zāīūṛṝḷḹēōṭḍṇṣśḥṃñṅ\s]', '', text)  # 添加更多梵文字符
    # 删除多余空格
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def clean_title(title):
    """Clean and format title."""
    # 移除重复的空格和标点
    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'[,，、。]+', '', title)
    
    # 处理括号内容
    # 1. 提取所有括号内容
    bracket_contents = re.findall(r'[（(](.*?)[）)]', title)
    # 2. 移除重复的括号内容
    seen_contents = set()
    unique_contents = []
    for content in bracket_contents:
        content = content.strip()
        if content not in seen_contents:
            seen_contents.add(content)
            unique_contents.append(content)
    
    # 3. 移除原有的所有括号内容
    title = re.sub(r'[（(].*?[）)]', '', title)
    title = title.strip()
    
    # 4. 处理 M05.xx 格式
    m05_match = re.search(r'M05\.(\d+)', title)
    if m05_match:
        number = m05_match.group(1)
        title = re.sub(r'M05\.\d+\s*', '', title)
        title = f"M05{number}_{title}"
    
    # 5. 移除 "卍" 符号和其他不需要的字符
    title = title.replace('卍', '')
    title = re.sub(r'["""]', '', title)
    title = re.sub(r'[_\-]+', '_', title)
    
    # 6. 添加唯一的括号内容
    if unique_contents:
        title = title + '_' + '_'.join(unique_contents)
    
    # 7. 最终清理
    title = re.sub(r'\s+', '_', title.strip())
    title = re.sub(r'_{2,}', '_', title)  # 移除连续的下划线
    title = title.strip('_')  # 移除首尾的下划线
    
    return title

def process_pdf_to_audio(file_path, output_folder):
    """Extract Romanized Sanskrit text from a PDF and convert it into Romanian audio."""
    romanized_texts, titles = extract_romanized_text_from_pdf(file_path)

    if not romanized_texts:
        logging.warning("No Romanized Sanskrit text found in the provided PDF.")
        return []

    audio_paths = []
    # 创建文本文件来保存处理结果
    text_output_path = os.path.join(output_folder, "processed_content.txt")

    with open(text_output_path, 'w', encoding='utf-8') as f:
        for i, (text, title) in enumerate(zip(romanized_texts, titles)):
            # 清理标题，移除卍符号和多余空格
            clean_title = re.sub(r'卍|\s+', ' ', title).strip()
            # 对标题进行文件名清理
            sanitized_title = sanitize_filename(clean_title)

            # 清理文本，只保留罗马化梵文 (已经在 extract_romanized_text_from_pdf 中处理)
            cleaned_text = text.strip()

            # 后处理以移除尾部噪音，现在更严格
            cleaned_text = re.sub(r'[jtLrakidio\s]*$', '', cleaned_text).strip() # 移除更多噪音字符
            cleaned_text = re.sub(r'\b[a-zA-Z]\b\s*$', '', cleaned_text).strip() # 移除尾部单字母
            cleaned_text = re.sub(r'[A-Z]{1,}\s*$', '', cleaned_text).strip() # 移除尾部大写字母
            cleaned_text = cleaned_text.strip() # 再次去除首尾空格

            # 移除文本中间的 "LLL", "LL", "No", "A" 等噪音词
            cleaned_text = re.sub(r'\b(LLL|LL|No|A|T)\b', '', cleaned_text).strip()
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip() # 再次规范化空格
            cleaned_text = cleaned_text.strip() # final strip after all regex

            # 再次检查是否为空或过短
            if not cleaned_text or len(cleaned_text) < 5: # 提高最小长度到 5
                print(f"跳过内容过短或噪音内容: {cleaned_text}")
                continue

            # 写入分隔线
            f.write("原文内容：\n\n")
            f.write(f"{title}\n\n")
            f.write("处理内容：\n\n")

            # 写入音频内容
            f.write("音频：")
            f.write(f"{cleaned_text}\n\n")

            # 写入音频名字
            f.write("音频名字：")
            f.write(f"{sanitized_title}\n") # 使用清理后的文件名
            f.write("==================================================\n\n")

            # 生成音频文件名, 使用清理后的标题作为文件名
            audio_file = f"{sanitized_title}.mp3" # 使用清理后的文件名
            audio_path = os.path.join(output_folder, audio_file)

            # 生成音频文件
            try:
                # 转换文本为罗马尼亚语发音
                romanian_text = convert_sanskrit_to_romanian(cleaned_text)
                tts = gTTS(text=romanian_text, lang='ro')
                tts.save(audio_path)
                audio_paths.append(audio_path)
                time.sleep(1)  # 避免请求过快
            except Exception as e:
                logging.error(f"Error generating audio for section {i+1}: {str(e)}")

    return audio_paths

if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # 设置输入输出路径
    pdf_folder = os.path.join(os.path.dirname(__file__), 'pdf')
    output_folder = os.path.join(os.path.dirname(__file__), 'output')

    # 确保输出文件夹存在
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # 获取PDF文件列表
    pdf_files = [f for f in os.listdir(pdf_folder) if f.endswith('.pdf')]

    if not pdf_files:
        logging.warning('没有找到PDF文件')
    else:
        for pdf_file in pdf_files:
            pdf_path = os.path.join(pdf_folder, pdf_file)
            logging.info(f'正在处理文件: {pdf_file}')
            
            try:
                audio_paths = process_pdf_to_audio(pdf_path, output_folder)
                if audio_paths:
                    logging.info(f'成功生成 {len(audio_paths)} 个音频文件')
                else:
                    logging.warning(f'未从文件 {pdf_file} 中提取到梵文内容')
            except Exception as e:
                logging.error(f'处理文件 {pdf_file} 时发生错误: {str(e)}')
                