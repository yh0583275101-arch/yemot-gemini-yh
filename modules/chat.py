import os
import requests
import asyncio
import edge_tts
from flask import Blueprint, request
import google.generativeai as genai
import threading

chat_bp = Blueprint('chat', __name__)

user_sessions = {}
processing_status = {}

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

def background_processing(phone, yemot_num, yemot_pass, user_audio, gemini_key):
    try:
        session = get_session(phone)
        genai.configure(api_key=gemini_key)
        
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
        res = requests.get(download_url)
        if res.status_code != 200:
            processing_status[phone] = "error"
            return
            
        audio_data = res.content
        local_audio_path = f"input_{phone}.wav"
        with open(local_audio_path, 'wb') as f:
            f.write(audio_data)

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

        upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
        with open(tts_filename, 'rb') as f:
            requests.post(upload_url, data={
                'token': f"{yemot_num}:{yemot_pass}",
                'path': f"ivr2:/answer_{phone}.wav"
            }, files={'file': f})

        if os.path.exists(local_audio_path): os.remove(local_audio_path)
        if os.path.exists(tts_filename): os.remove(tts_filename)

        processing_status[phone] = "ready"
        
    except Exception as e:
        print(f"קריסה בתהליך הרקע: {str(e)}")
        processing_status[phone] = "error"

@chat_bp.route('/api/chat', methods=['GET', 'POST'])
def chat():
    try:
        args = request.values
        phone = args.get('ApiPhone', 'unknown')
        gemini_key = args.get('gemini_key')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        
        user_audio = args.get('user_audio')
        next_step = args.get('next_step')
        check_status = args.get('check_status')
        
        print(f"--- פנייה חדשה מטלפון {phone} ---")
        print(f"user_audio: {user_audio}, next_step: {next_step}")
        
        session = get_session(phone)
        genai.configure(api_key=gemini_key)

        if check_status == 'yes':
            status = processing_status.get(phone, "working")
            if status == "ready":
                processing_status[phone] = "idle"
                return f"read=f-greeting=user_audio,,record&say_before_read=f-answer_{phone}"
            elif status == "error":
                return f"id_list_message=t-M1103&go_to_folder=/"
            else:
                return f"read=t-M0000=no_digits,,3,3,Digits&go_to_folder=?check_status=yes"

        if next_step == '2':
            return f"id_list_message=f-answer_{phone}&read=f-next_step_menu=next_step,,1,1,Digits"

        if user_audio:
            print(f"מזהה הקלטה מ-{phone}. מפעיל תהליך ברקע למניעת Timeout...")
            processing_status[phone] = "working"
            
            t = threading.Thread(target=background_processing, args=(phone, yemot_num, yemot_pass, user_audio, gemini_key))
            t.start()
            
            return f"id_list_message=t-M0000&go_to_folder=?check_status=yes"
        # if user_audio:
        #     print("מזהה הקלטה חדשה, מתחיל הורדה מימות המשיח...")
        #     download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
            
        #     # ניסיון הורדה בטוח
        #     res = requests.get(download_url)
        #     if res.status_code != 200:
        #         print(f"שגיאה בהורדת הקובץ מימות המשיח: קוד סטטוס {res.status_code}")
        #         return f"id_list_message=t-M1103&go_to_folder=/" # הודעת שגיאה כללית וחזרה
                
        #     audio_data = res.content
            
        #     # שימוש בנתיב הנוכחי של האפליקציה במקום /tmp
        #     local_audio_path = f"input_{phone}.wav"
        #     with open(local_audio_path, 'wb') as f:
        #         f.write(audio_data)

        #     print("הקובץ נשמר בהצלחה בשרת. מעלה ל-Gemini...")
        #     uploaded_audio = genai.upload_file(local_audio_path)
            
        #     model = genai.GenerativeModel(
        #         model_name=session['model'],
        #         system_instruction=session['prompt']
        #     )
            
        #     chat_session = model.start_chat(history=session['history'])
        #     response = chat_session.send_message(["אנא ענה על ההקלטה המצורפת", uploaded_audio])
            
        #     session['history'] = chat_session.history
        #     answer_text = response.text
        #     print(f"תשובת הבינה המלאכותית: {answer_text}")

        #     tts_filename = f"answer_{phone}.wav"
        #     asyncio.run(generate_tts(answer_text, tts_filename))
        #     print("קובץ ה-TTS נוצר בהצלחה. מעלה חזרה לימות המשיח...")

        #     upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
        #     with open(tts_filename, 'rb') as f:
        #         requests.post(upload_url, data={
        #             'token': f"{yemot_num}:{yemot_pass}",
        #             'path': f"ivr2:/answer_{phone}.wav"
        #         }, files={'file': f})

        #     print("הקובץ עלה לימות המשיח בהצלחה!")
            
        #     # ניקוי קבצים זמניים מקומיים
        #     if os.path.exists(local_audio_path): os.remove(local_audio_path)
        #     if os.path.exists(tts_filename): os.remove(tts_filename)

        #     return f"read=f-greeting=user_audio,,record&say_before_read=f-answer_{phone}"

        # כניסה ראשונית - משמיע את קובץ ה-greeting שהעלת ומקליט
        return f"read=f-greeting=user_audio,,record"
        
    except Exception as e:
        # אם יש שגיאה - היא תודפס ישירות ללוג של רנדר בצורה ברורה!
        print(f"!!! קריסה חמורה בפונקציית הצ'אט: {str(e)}")
        return f"id_list_message=t-M1103&go_to_folder=/"
