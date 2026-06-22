import os
import requests
import asyncio
import edge_tts
from flask import Blueprint, request
import google.generativeai as genai

chat_bp = Blueprint('chat', __name__)

user_sessions = {}

def get_session(phone):
    if phone not in user_sessions:
        user_sessions[phone] = {
            'history': [],
            'prompt': 'אתה עוזר חכם ואישי. ענה בצורה טבעית, שפת דיבור זורמת של חבר אל חבר. אל תשתמש בשום פנים ואופן בכוכביות, סולמיות, אימוג\'ים או סימוני טקסט מיוחדים. השתמש בסימני פיסוק בלבד (פסיק ונקודה) כדי שהקריין שמקריא את הטקסט יוכל לפסק נכון את המשפטים.',
            'model': 'gemini-2.5-flash'
        }
    return user_sessions[phone]

async def generate_tts(text, filename):
    communicate = edge_tts.Communicate(text, "he-IL-AvriNeural", rate="+5%")
    await communicate.save(filename)

@chat_bp.route('/api/chat', methods=['GET', 'POST'])
def chat():
    try:
        args = request.values
        phone = args.get('ApiPhone', 'unknown')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        user_audio = args.get('user_audio')
        
        # משיכת מפתח ה-API בצורה שמתאימה גם כשהוא מוגדר בשורה נפרדת בימות המשיח
        gemini_key = args.get('gemini_key')
        
        print(f"--- פנייה חדשה מטלפון {phone} ---")
        
        if not gemini_key:
            print("!!! שגיאה: מפתח gemini_key לא התקבל בשרת")
            return f"id_list_message=t-M1103&go_to_folder=/"

        session = get_session(phone)
        genai.configure(api_key=gemini_key)

        if user_audio:
            print("מזהה הקלטה חדשה, מתחיל הורדה מימות המשיח...")
            download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
            
            res = requests.get(download_url)
            if res.status_code != 200:
                print(f"שגיאה בהורדת הקובץ מימות המשיח: קוד סטטוס {res.status_code}")
                return f"id_list_message=t-M1103&go_to_folder=/"
                
            local_audio_path = f"input_{phone}.wav"
            with open(local_audio_path, 'wb') as f:
                f.write(res.content)

            print("הקובץ נשמר בהצלחה בשרת. מעלה ל-Gemini...")
            uploaded_audio = genai.upload_file(local_audio_path)
            
            model = genai.GenerativeModel(
                model_name=session['model'],
                system_instruction=session['prompt']
            )
            
            chat_session = model.start_chat(history=session['history'])
            response = chat_session.send_message(["אנא ענה על ההקלטה המצורפת", uploaded_audio])
            
            session['history'] = chat_session.history
            answer_text = response.text
            print(f"תשובת הבינה המלאכותית: {answer_text}")

            tts_filename = f"answer_{phone}.wav"
            asyncio.run(generate_tts(answer_text, tts_filename))
            print("קובץ ה-TTS נוצר בהצלחה. מעלה חזרה לשלוחה 1...")

            # העלאה ישירה לתוך שלוחה 1 (ivr2:1/)
            upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
            with open(tts_filename, 'rb') as f:
                requests.post(upload_url, data={
                    'token': f"{yemot_num}:{yemot_pass}",
                    'path': f"ivr2:1/answer_{phone}.wav"
                }, files={'file': f})

            print("הקובץ עלה לימות המשיח בהצלחה!")
            
            if os.path.exists(local_audio_path): os.remove(local_audio_path)
            if os.path.exists(tts_filename): os.remove(tts_filename)

            # הפקודה המדויקת שמשמיעה מתוך שלוחה 1 ומבקשת להקליט שוב
            return f"read=f-answer_{phone}=user_audio,,record"

        # כניסה ראשונית לשלוחה
        return f"read=f-greeting=user_audio,,record"
        
    except Exception as e:
        print(f"!!! קריסה חמורה בפונקציית הצ'אט: {str(e)}")
        return f"id_list_message=t-M1103&go_to_folder=/"
