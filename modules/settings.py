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
    topics_list = [line.split('|') for line in topics_text.split('\n') if '|' in line]
    
    if not topics_list:
        return "id_list_message=t-אין שיחות מוקלטות במערכת&go_to_folder=/"
        
    if selection and selection.isdigit():
        idx = int(selection) - 1
        if 0 <= idx < len(topics_list):
            topic_id = topics_list[idx][0]
            # שמירת מזהה הנושא האחרון שהמשתמש בחר להאזנה
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
    
    return f"read=2/menu_{phone}=selection,Number,1,1,{len(topics_list)},,yes"


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
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
        audio_data = requests.get(download_url).content
        
        local_audio = f"/tmp/prompt_{phone}.wav"
        with open(local_audio, 'wb') as f: f.write(audio_data)
            
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

    # שלב ב': המשתמש סיים להקליט, נשאל אותו האם להחליף או להוסיף
    if user_audio and not mode:
        return f"read=M1309=mode,Number,1,1,1,,yes&api_link_append=user_audio={user_audio}"

    # שלב א': בקשת הקלטה ראשונית
    return "read=f-greeting=user_audio,,record,,,no"
