import os
import requests
import asyncio
from flask import Blueprint, request
import google.generativeai as genai
from modules.chat import generate_tts, download_ym_text, upload_ym_bytes

settings_bp = Blueprint('settings', __name__)

# --- שלוחה 2: תפריט כניסה והאזנה לשרשורים קודמים ---
@settings_bp.route('/api/topics_menu', methods=['GET', 'POST'])
def topics_menu():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    selection = args.get('selection')
    yemot_num = args.get('yemot_num')
    yemot_pass = args.get('yemot_pass')
    
    topics_path = f"2/{phone}_topics.txt"
    topics_text = download_ym_text(yemot_num, yemot_pass, topics_path)
    
    if not topics_text or "|" not in topics_text:
        return "id_list_message=t-אין שיחות מוקלטות במערכת&go_to_folder=/"
        
    topics_list = [line.split('|') for line in topics_text.split('\n') if '|' in line]
        
    if selection and selection.isdigit():
        idx = int(selection) - 1
        if 0 <= idx < len(topics_list):
            topic_id = topics_list[idx][0]
            upload_ym_bytes(yemot_num, yemot_pass, f"2/{phone}_last_selected.txt", topic_id.encode('utf-8'), f"{phone}_last_selected.txt")
            return f"go_to_folder=/2/{topic_id}"

    menu_text = "להאזנה לשיחות הקודמות שלך. "
    for i, (topic_id, title) in enumerate(topics_list):
        menu_text += f"עבור שיחה מספר {i+1} בנושא {title}, הקש {i+1}. "
        
    menu_filename = f"/tmp/menu_{phone}.wav"
    asyncio.run(generate_tts(menu_text, menu_filename))
    
    with open(menu_filename, 'rb') as f:
        upload_ym_bytes(yemot_num, yemot_pass, f"2/menu_{phone}.wav", f.read(), f"menu_{phone}.wav")
    if os.path.exists(menu_filename): os.remove(menu_filename)
    
    return f"read=f-2/menu_{phone}.wav=selection,Number,1,1,{len(topics_list)},,yes"


# --- שלוחה 3: הגדרת פרומפט אישי ושמירתו כקובץ טקסט בימות המשיח ---
@settings_bp.route('/api/set_prompt', methods=['GET', 'POST'])
def set_prompt():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    user_audio = args.get('user_audio')
    gemini_key = args.get('gemini_key')
    yemot_num = args.get('yemot_num')
    yemot_pass = args.get('yemot_pass')
    mode = args.get('mode')
    
    # שלב ג': עיבוד ההקלטה ושמירה לפי הבחירה (דריסה או הוספה)
    if user_audio and mode:
        genai.configure(api_key=gemini_key)
        
        # שלוחה 3 שומרת זמנית את הקובץ במיקום קבוע בשביל העיבוד
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:3/prompt_temp.wav"
        res = requests.get(download_url)
        if res.status_code != 200:
            return "id_list_message=t-חלה שגיאה בעיבוד הקובץ&go_to_folder=/"
            
        local_audio = f"/tmp/prompt_{phone}.wav"
        with open(local_audio, 'wb') as f: f.write(res.content)
            
        uploaded = genai.upload_file(local_audio)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(["תמלל את קלטת המשתמש הזו במלואה מילה במילה ללא תוספות:", uploaded])
        new_text = response.text.strip()
        
        existing_text = download_ym_text(yemot_num, yemot_pass, f"3/{phone}_prompt.txt")

        if mode == "2" and existing_text:
            final_text = existing_text + "\n" + new_text
        else:
            final_text = new_text

        upload_ym_bytes(yemot_num, yemot_pass, f"3/{phone}_prompt.txt", final_text.encode('utf-8'), f"{phone}_prompt.txt")
        if os.path.exists(local_audio): os.remove(local_audio)
        
        return "id_list_message=t-ההנחיה האישית שלך עודכנה ונשמרה בהצלחה&go_to_folder=/"

    # שלב ב': המשתמש סיים להקליט, אנחנו מעבירים אותו לשאלת התפריט בצורה נקייה בלי שרשורי פקודות אסורים!
    if user_audio:
        # קודם כל נעלה את הקובץ הזמני בצורה מסודרת לתיקייה 3
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
        audio_data = requests.get(download_url).content
        upload_ym_bytes(yemot_num, yemot_pass, "3/prompt_temp.wav", audio_data, "prompt_temp.wav")
        
        # מחזירים אך ורק פקודת הקשה נקייה. הבקשה הבאה שתחזור לשרת תכיל את הפרמטר `mode`
        return "read=M1309=mode,Number,1,1,1,,yes"

    # שלב א': בקשת הקלטה ראשונית מהמשתמש
    return "read=user_audio,,record,,,no"
