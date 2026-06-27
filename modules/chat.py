import os
import time
import requests
import asyncio
import edge_tts
from flask import Blueprint, request
import google.generativeai as genai
import traceback
import soundfile as sf
from scipy.signal import resample

chat_bp = Blueprint('chat', __name__)

user_sessions = {}

def get_session(phone):
    if phone not in user_sessions:
        user_sessions[phone] = {
            'history': [],
            'prompt': """אתה עוזר קולי חכם ואישי בטלפון בשם גִ'ינְגֶ'ר. המין שלך הוא זכר לכן כשאתה מדבר על עצמך תדבר בלשון זכר. המפתח שבנה אותך הוא סְמַרְטי גִ'ינְגֶ'ר אפליקציות בע"מ.  ענה למשתמש בצורה טובה, ברורה ומפורטת, ותזהה לפי הקול האם מי שמדבר זה זכר או נקבה ולפי התוצאה תדבר אליו בלשון של המין שלו שזיהת בהקלטה, אך הקפד לא להאריך יותר מדי . חובה להוסיף סימני פיסוק תקניים (נקודות, פסיקים, סימני שאלה). הקפד להשתמש בסימני קריאה (!) במשפטים שדורשים הדגשה, התלהבות או טון דרמטי יותר. וכששלחו לך בשאלה טקסט מנוקד ואתה חוזר על אותה מילה מנוקדת תנקד אותה לפי הניקוד שהיה במילה ששלחו לך בשאלה. אל תשתמש בשום פנים ואופן בכוכביות (**), סולמיות (#) או סימוני טקסט מיוחדים""",
            'model': 'gemini-2.5-flash'
        }
    return user_sessions[phone]

async def generate_tts(text, wav_filename):
    # 1. יצירת קובץ MP3 זמני ממיקרוסופט
    temp_mp3 = wav_filename + ".mp3"
    communicate = edge_tts.Communicate(text, "he-IL-AvriNeural", rate="+5%")
    await communicate.save(temp_mp3)
    
    # 2. קריאת קובץ ה-MP3 שנוצר בצורה אוטומטית ומדויקת
    data, sample_rate = sf.read(temp_mp3)
    
    # 3. חישוב כמות הדגימות החדשה כדי להגיע בדיוק ל-8000Hz (התדר של ימות המשיח)
    target_rate = 8000
    number_of_samples = int(len(data) * target_rate / sample_rate)
    
    # ביצוע שינוי תדר מתמטי נקי לחלוטין למניעת רעשים מוזרים
    resampled_data = resample(data, number_of_samples)
    
    # 4. שמירה ישירה כקובץ WAV מסוג Windows PCM 16-bit נקי
    sf.write(wav_filename, resampled_data, target_rate, subtype='PCM_16')
    
    # ניקוי קובץ ה-MP3 הזמני מהשרת
    if os.path.exists(temp_mp3):
        os.remove(temp_mp3)
        
@chat_bp.route('/api/chat', methods=['GET', 'POST'])
def chat():
    try:
        args = request.values
        phone = args.get('ApiPhone')
        gemini_key = args.get('gemini_key')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        user_audio = args.get('user_audio')
        
        # הגנה מבוססת ניתוק
        if args.get('hangup') == 'yes':
            return ""
            
        if not phone or phone == 'unknown':
            print("!!! אזהרה: לא התקבל מספר טלפון תקין")
            return ""

        print(f"--- פנייה חדשה מטלפון {phone} ---")
        
        # מחיקת קובץ התשובה הישן מימות המשיח כדי למנוע כפילויות אם תהיה קריסה
        if user_audio:
            print("מוחק את קובץ התשובה הישן מימות המשיח למניעת כפילויות...")
            delete_url = f"https://www.call2all.co.il/ym/api/DeleteFile?token={yemot_num}:{yemot_pass}&path=ivr2:1/{phone}.wav"
            requests.get(delete_url)

        if not gemini_key:
            print("!!! שגיאה: מפתח gemini_key חסר")
            return "id_list_message=t-M1103"

        session = get_session(phone)
        genai.configure(api_key=gemini_key)

        if user_audio:
            print(f"מתחיל הורדת הקלטה: {user_audio}")
            download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
            
            res = requests.get(download_url)
            if res.status_code != 200:
                print("שגיאה בהורדת הקובץ מימות המשיח")
                return "id_list_message=t-M1103"
                
            local_audio_path = f"/tmp/input_{phone}.wav"
            with open(local_audio_path, 'wb') as f:
                f.write(res.content)

            print("הקובץ נשמר בשרת. מעלה ל-Gemini...")
            uploaded_audio = genai.upload_file(local_audio_path)
            
            model = genai.GenerativeModel(
                model_name=session['model'],
                system_instruction=session['prompt']
            )
            
            print("פונה לג'מיני לקבלת תשובה...")
            chat_session = model.start_chat(history=session['history'])
            
            try:
                response = chat_session.send_message([""" אנא הקשב לקובץ השמע המצורף וענה עליו בקיצור נמרץ בתור תשובה למשתמש אבל אל תגיד למשתמש שקיבלת את ההודעה כקובץ שמע אלא א"כ המשתמש מבקש.:""", uploaded_audio])
                
                if not response or not hasattr(response, 'text') or not response.text:
                    print("!!! ג'מיני החזיר אובייקט ריק או חסום. בדוק הגדרות בטיחות/מכסה.")
                    return "id_list_message=t-M1103"
                    
                answer_text = response.text
                print(f"תשובת הבינה המלאכותית: {answer_text}")
                
            except Exception as gemini_error:
                # מדפיס ללוג של Render את השגיאה המדויקת של גוגל!
                print(f"!!! קריסה ישירה בפנייה לגו׳מיני: {str(gemini_error)}")
                return "id_list_message=t-M1103"

            session['history'] = chat_session.history

            # יצירת שם קובץ ייחודי לכל תור כדי למנוע זיכרון מטמון (Cache) בימות המשיח
            audio_id = user_audio.replace('/', '_').replace('.', '_')
            tts_filename = f"/tmp/{phone}_{audio_id}.wav"
            asyncio.run(generate_tts(answer_text, tts_filename))
            print("קובץ ה-TTS נוצר. מעלה לשלוחה 1...")

            upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
            with open(tts_filename, 'rb') as f:
                requests.post(upload_url, data={
                    'token': f"{yemot_num}:{yemot_pass}",
                    'path': f"ivr2:1/{phone}.wav"
                }, files={'file': f})

            print("הקובץ עלה בהצלחה!")
            
            # ממתינים 2 שניות כדי לתת לשרתים של ימות המשיח להסתנכרן על הקובץ החדש
            print("ממתין 2 שניות לסנכרון הקובץ בימות המשיח...")
            time.sleep(2)
            
            if os.path.exists(local_audio_path): os.remove(local_audio_path)
            if os.path.exists(tts_filename): os.remove(tts_filename)

            return f"read=f-{tts_filename}=user_audio,,record,,,no"


        # כניסה ראשונית לשלוחה
        return f"read=f-greeting=user_audio,,record,,,no"
        
    except Exception as e:
        print("!!! קריסה כללית בפונקציה:")
        print(traceback.format_exc())
        return "id_list_message=t-M1103"

@chat_bp.route('/api/error', methods=['GET', 'POST'])
def handle_error():
    args = request.values
    action = args.get('Action', 'לא ידוע')
    file_path = args.get('FilePath', 'לא ידוע')
    error_msg = args.get('ErrorMessage', 'לא ידוע')
    
    # תרגום הפעולה לעברית לפי בקשתך
    action_desc = ""
    if "id list message" in action.lower():
        action_desc = " - פקודה של השמעת קבצים"
    elif "read" in action.lower():
        action_desc = " - פקודה של השמעת קובץ והקלטה"
        
    print("\n=====================================")
    print(" 🚨 התקבלה שגיאת השמעת קובץ מימות המשיח!")
    print(f" Action: {action}{action_desc}")
    print(f" FilePath: {file_path} /// נתיב הקובץ שניסתה המערכת להשמיע")
    print(f" ErrorMessage: {error_msg} /// סיבת השגיאה")
    print("=====================================\n")
    
    return "OK"
