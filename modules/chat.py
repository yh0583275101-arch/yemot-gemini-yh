import os
import requests
import asyncio
import edge_tts
from flask import Blueprint, request
import google.generativeai as genai

chat_bp = Blueprint('chat', __name__)

# שמירת היסטוריית שיחות והגדרות בזיכרון השרת (לפי מספרי טלפון)
user_sessions = {}

def get_session(phone):
    if phone not in user_sessions:
        user_sessions[phone] = {
            'history': [],
            'prompt': 'אתה עוזר חכם ואישי. ענה בצורה טבעית, שפת דיבור זורמת של חבר אל חבר. אל תשתמש בשום פנים ואופן בכוכביות, סולמיות, אימוג\'ים או סימוני טקסט מיוחדים. השתמש בסימני פיסוק בלבד (פסיק ונקודה) כדי שהקריין שמקריא את הטקסט יוכל לפסק נכון את המשפטים.',
            'model': 'gemini-1.5-flash' # מודל ברירת מחדל
        }
    return user_sessions[phone]

async def generate_tts(text, filename):
    # שימוש בקול הגברי 'Avri' של מיקרוסופט - חינמי, טבעי ונשמע סביב גיל 35
    communicate = edge_tts.Communicate(text, "he-IL-AvriNeural", rate="+5%")
    await communicate.save(filename)

@chat_bp.route('/api/chat', methods=['GET', 'POST'])
def chat():
    # קבלת כל ההגדרות והמפתחות מימות המשיח (הוגדרו ב-ext.ini)
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    gemini_key = args.get('gemini_key')
    yemot_num = args.get('yemot_num')
    yemot_pass = args.get('yemot_pass')
    
    user_audio = args.get('user_audio')
    next_step = args.get('next_step')
    
    session = get_session(phone)
    genai.configure(api_key=gemini_key)

    # 1. אם הלקוח ביקש לשמוע שוב את התשובה
    if next_step == '2':
        return f"id_list_message=f-answer_{phone}&read=f-next_step_menu=next_step,,1,1,Digits"

    # 2. אם יש הקלטה חדשה מהלקוח
    if user_audio:
        # הורדת ההקלטה מימות המשיח
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path={user_audio}"
        audio_data = requests.get(download_url).content
        
        local_audio_path = f"/tmp/input_{phone}.wav"
        with open(local_audio_path, 'wb') as f:
            f.write(audio_data)

        # העלאת השמע ל-Gemini ושליחת ההיסטוריה
        uploaded_audio = genai.upload_file(local_audio_path)
        model = genai.GenerativeModel(
            model_name=session['model'],
            system_instruction=session['prompt']
        )
        
        chat_session = model.start_chat(history=session['history'])
        response = chat_session.send_message(["אנא ענה על ההקלטה המצורפת", uploaded_audio])
        
        # עדכון היסטוריה (כדי לזכור את ההקשר)
        session['history'] = chat_session.history
        
        answer_text = response.text

        # יצירת קובץ שמע מהתשובה (TTS)
        tts_filename = f"/tmp/answer_{phone}.wav"
        asyncio.run(generate_tts(answer_text, tts_filename))

        # העלאת התשובה המוקריינת לימות המשיח
        upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
        with open(tts_filename, 'rb') as f:
            requests.post(upload_url, data={
                'token': f"{yemot_num}:{yemot_pass}",
                'path': f"ivr2:/answer_{phone}.wav"
            }, files={'file': f})

        # הפעלת התשובה ללקוח, ואז בקשת פעולה הבאה (1 לשאלה נוספת, 2 לשמיעה חוזרת)
        return f"id_list_message=f-answer_{phone}&read=f-next_step_menu=next_step,,1,1,Digits"

    # 3. כניסה ראשונית לשלוחה או לחיצה על 1 לשאלה נוספת
    return f"read=f-greeting=user_audio,,record"