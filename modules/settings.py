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
    
    # בדיקה כמה שלוחות נושאים קיימות בפועל (עד הנושא הבא שייפתח)
    total_topics = session['next_topic_id'] - 1
    
    if total_topics == 0:
        return "id_list_message=t-אין שיחות מוקלטות במערכת&go_to_folder=/"
        
    # אם המשתמש בחר מספר נושא מתוך התפריט
    if selection and selection.isdigit():
        topic_id = int(selection)
        if 1 <= topic_id <= total_topics:
            session['current_topic_id'] = topic_id
            
            # בדיקה כמה קבצים יש בתיקייה כדי לדעת מה האינדקס הבא להקלטה
            # נגדיר לימות המשיח לעבור לשלוחה הפנימית הזו ולהשמיע אותה כשרשור הודעות!
            # הגדרות ה-ext.ini הפנימיות שיצרנו בשלב 3 יאפשרו לחיצה על כוכבית באמצע לעבור להקלטה.
            return f"go_to_folder=/2/{topic_id}"

    # בניית תפריט הקראה פשוט לפי מספרים (נושא 1, נושא 2...)
    menu_text = "להאזנה לשיחות הקודמות שלך. "
    for i in range(1, total_topics + 1):
        menu_text += f"עבור שיחה מספר {i}, הקש {i}. "
        
    menu_filename = f"/tmp/menu_{phone}.wav"
    asyncio.run(generate_tts(menu_text, menu_filename))
    
    upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
    with open(menu_filename, 'rb') as f:
        requests.post(upload_url, data={
            'token': f"{yemot_num}:{yemot_pass}",
            'path': f"ivr2:2/menu_{phone}.wav"
        }, files={'file': f})
        
    if os.path.exists(menu_filename): os.remove(menu_filename)
    
    return f"read=f-2/menu_{phone}=selection,Number,1,1,{total_topics},,yes"


# --- שלוחה 3: הגדרת פרומפט אישי של המשתמש ---
@settings_bp.route('/api/set_prompt', methods=['GET', 'POST'])
def set_prompt():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    user_audio = args.get('user_audio')
    gemini_key = args.get('gemini_key')
    yemot_num = args.get('yemot_num')
    yemot_pass = args.get('yemot_pass')
    
    if user_audio:
        genai.configure(api_key=gemini_key)
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
        audio_data = requests.get(download_url).content
        
        local_audio = f"/tmp/prompt_{phone}.wav"
        with open(local_audio, 'wb') as f: f.write(audio_data)
            
        uploaded = genai.upload_file(local_audio)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(["תמלל את הקלטת המשתמש הזו במלואה מילה במילה. הטקסט ישמש כהנחיית התנהגות קבועה עבורך:", uploaded])
        
        session = get_session(phone)
        session['custom_prompt'] = response.text.strip()
        
        if os.path.exists(local_audio): os.remove(local_audio)
        return "id_list_message=t-ההנחיה האישית שלך נשמרה בהצלחה&go_to_folder=/"

    return "read=f-record_prompt=user_audio,,record,,,no"
