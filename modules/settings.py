import os
import requests
import asyncio
from flask import Blueprint, request
import google.generativeai as genai
from modules.chat import get_session, generate_tts

settings_bp = Blueprint('settings', __name__)

# --- שלוחה 2: תפריט כניסה והאזנה לשרשורים קודמים ---
@settings_bp.route('/api/topics_menu', methods=['GET', 'POST'])
def topics_menu():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    selection = args.get('selection')
    yemot_num = args.get('yemot_num')
    yemot_pass = args.get('yemot_pass')
    
    session = get_session(phone)
    total_topics = session['next_topic_id'] - 1
    
    if total_topics == 0:
        return "id_list_message=t-אין שיחות מוקלטות במערכת&go_to_folder=/"
        
    if selection and selection.isdigit():
        topic_id = int(selection)
        if 1 <= topic_id <= total_topics:
            session['current_topic_id'] = topic_id
            return f"go_to_folder=/2/{topic_id}"

    menu_text = "להאזנה לשיחות הקודמות שלך. "
    for i in range(1, total_topics + 1):
        menu_text += f"עבור שיחה מספר {i}, הקש {i}. "
        
    menu_filename = f"/tmp/menu_{phone}.wav"
    asyncio.run(generate_tts(menu_text, menu_filename))
    
    upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
    with open(menu_filename, 'rb') as f:
        requests.post(upload_url, data={'token': f"{yemot_num}:{yemot_pass}", 'path': f"ivr2:2/menu_{phone}.wav"}, files={'file': f})
    if os.path.exists(menu_filename): os.remove(menu_filename)
    
    return f"read=2/menu_{phone}=selection,Number,1,1,{total_topics},,yes"


# --- שלוחה 3: הגדרת פרומפט אישי ושמירתו כקובץ טקסט בימות המשיח ---
@settings_bp.route('/api/set_prompt', methods=['GET', 'POST'])
def set_prompt():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    user_audio = args.get('user_audio')
    gemini_key = args.get('gemini_key')
    yemot_num = args.get('yemot_num')
    yemot_pass = args.get('yemot_pass')
    mode = args.get('mode') # קבלת הבחירה: 1 לדריסה, 2 להוספה
    
    # שלב ב': המשתמש בחר מצב (דריסה/הוספה) ואנחנו מעבדים את ההקלטה
    if user_audio and mode:
        genai.configure(api_key=gemini_key)
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
        audio_data = requests.get(download_url).content
        
        local_audio = f"/tmp/prompt_{phone}.wav"
        with open(local_audio, 'wb') as f: f.write(audio_data)
            
        uploaded = genai.upload_file(local_audio)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(["תמלל את הקלטת המשתמש הזו במלואה מילה במילה ללא תוספות:", uploaded])
        new_text = response.text.strip()
        
        # בדיקה האם קיים כבר קובץ טקסט קודם בשלוחה 3 כדי להוסיף עליו
        existing_text = ""
        check_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:3/{phone}_prompt.txt"
        res_check = requests.get(check_url)
        if res_check.status_code == 200:
            existing_text = res_check.text.strip()

        # קביעת הטקסט הסופי לפי בחירת המשתמש
        if mode == "2" and existing_text:
            final_text = existing_text + "\n" + new_text
        else:
            final_text = new_text

        # שמירת קובץ הטקסט המעודכן זמנית בשרת
        txt_filename = f"/tmp/{phone}_prompt.txt"
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(final_text)
            
        # העלאת קובץ הטקסט הקבוע לשלוחה 3 של המשתמש בימות המשיח!
        upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
        with open(txt_filename, 'rb') as f:
            requests.post(upload_url, data={'token': f"{yemot_num}:{yemot_pass}", 'path': f"ivr2:3/{phone}_prompt.txt"}, files={'file': f})
            
        if os.path.exists(local_audio): os.remove(local_audio)
        if os.path.exists(txt_filename): os.remove(txt_filename)
        
        return "id_list_message=t-ההנחיה האישית שלך עודכנה ונשמרה בהצלחה&go_to_folder=/"

    # שלב א': המשתמש הקליט, עכשיו נשאל אותו האם לדרוס או להוסיף
    if user_audio and not mode:
        return f"read=M1309=mode,Number,1,1,1,,yes&api_link_append=user_audio={user_audio}" 
        # M1309 משמיע תפריט בחירה: להחלפה הקש 1, להוספה הקש 2

    # תחילת התהליך: בקשת הקלטה מהמשתמש (הודעה כללית נא להקליט לאחר הצפצוף)
    return "read=M1006=user_audio,record,3,prompt_temp,no"
