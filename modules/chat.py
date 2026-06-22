import os
import requests
from flask import Blueprint, request
import google.generativeai as genai

chat_bp = Blueprint('chat', __name__)

user_sessions = {}

def get_session(phone):
    if phone not in user_sessions:
        user_sessions[phone] = {
            'history': [],
            'prompt': 'אתה עוזר חכם ואישי. ענה בקולך בצורה טבעית, שפת דיבור זורמת של חבר אל חבר.',
            'model': 'gemini-2.5-flash'
        }
    return user_sessions[phone]

@chat_bp.route('/api/chat', methods=['GET', 'POST'])
def chat():
    try:
        args = request.values
        phone = args.get('ApiPhone', 'unknown')
        gemini_key = args.get('gemini_key')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        user_audio = args.get('user_audio')
        
        print(f"--- פנייה חדשה מטלפון {phone} ---")
        
        session = get_session(phone)
        genai.configure(api_key=gemini_key)

        if user_audio:
            print("מזהה הקלטה חדשה, מתחיל הורדה מימות המשיח...")
            download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
            
            res = requests.get(download_url)
            if res.status_code != 200:
                print(f"שגיאה בהורדת הקובץ: {res.status_code}")
                return f"id_list_message=t-M1103&go_to_folder=/"
                
            local_audio_path = f"input_{phone}.wav"
            with open(local_audio_path, 'wb') as f:
                f.write(res.content)

            print("הקובץ נשמר. מעלה ל-Gemini...")
            uploaded_audio = genai.upload_file(local_audio_path)
            
            model = genai.GenerativeModel(
                model_name=session['model'],
                system_instruction=session['prompt']
            )
            
            chat_session = model.start_chat(history=session['history'])
            response = chat_session.send_message(["אנא ענה על ההקלטה המצורפת בקולך", uploaded_audio])
            session['history'] = chat_session.history
            
            tts_filename = f"answer_{phone}.wav"
            
            # שליפת קובץ האודיו הגולמי שחזר ישירות מג'מיני
            try:
                audio_bytes = response.candidates[0].content.parts[0].inline_data.data
                with open(tts_filename, 'wb') as f:
                    f.write(audio_bytes)
                print("קובץ השמע מג'מיני נשמר בהצלחה.")
            except Exception as audio_err:
                print(f"באג בשליפת אודיו ישיר: {str(audio_err)}")
                return f"id_list_message=t-M1103&go_to_folder=/"

            # העלאת הקובץ ישירות לתוך שלוחה 1 (ivr2:1/)
            upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
            with open(tts_filename, 'rb') as f:
                requests.post(upload_url, data={
                    'token': f"{yemot_num}:{yemot_pass}",
                    'path': f"ivr2:1/answer_{phone}.wav" # <-- התיקון לנתיב שלוחה 1!
                }, files={'file': f})

            if os.path.exists(local_audio_path): os.remove(local_audio_path)
            if os.path.exists(tts_filename): os.remove(tts_filename)

            # משמיע את התשובה מתוך שלוחה 1 ומבקש להקליט שוב
            return f"read=f-1/answer_{phone}=user_audio,,record"

        return f"read=f-greeting=user_audio,,record"
        
    except Exception as e:
        print(f"!!! קריסה: {str(e)}")
        return f"id_list_message=t-M1103&go_to_folder=/"
