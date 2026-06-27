import os
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
            'topics': {},  # שמירת כותרות הנושאים: {audio_id: title}
            'current_topic': None,  # המזהה של הנושא הפעיל כרגע
            'custom_prompt': "",  # הפרומפט האישי שנוסיף משלוחה 3
            'prompt': """אתה עוזר קולי חכם ואישי בטלפון בשם גִ'ינְגֶ'ר. המין שלך הוא זכר לכן כשאתה מדבר על עצמך תדבר בלשון זכר. המפתח שבנה אותך הוא סְמַרְטי גִ'ינְגֶ'ר אפליקציות בע"מ.  ענה למשתמש בצורה טובה, ברורה ומפורטת, ותזהה לפי הקול האם מי שמדבר זה זכר או נקבה ולפי התוצאה תדבר אליו בלשון של המין שלו שזיהת בהקלטה, אך הקפד לא להאריך יותר מדי . חובה להוסיף סימני פיסוק תקניים (נקודות, פסיקים, סימני שאלה). הקפד להשתמש בסימני קריאה (!) במשפטים שדורשים הדגשה, התלהבות או טון דרמטי יותר. וכששלחו לך בשאלה טקסט מנוקד ואתה חוזר על אותה מילה מנוקדת תנקד אותה לפי הניקוד שהיה במילה ששלחו לך בשאלה. אל תשתמש בשום פנים ואופן בכוכביות (**), סולמיות (#) או סימוני טקסט מיוחדים"""
        }
    return user_sessions[phone]

async def generate_tts(text, wav_filename):
    temp_mp3 = wav_filename + ".mp3"
    communicate = edge_tts.Communicate(text, "he-IL-AvriNeural", rate="+5%")
    await communicate.save(temp_mp3)
    data, sample_rate = sf.read(temp_mp3)
    target_rate = 8000
    number_of_samples = int(len(data) * target_rate / sample_rate)
    resampled_data = resample(data, number_of_samples)
    sf.write(wav_filename, resampled_data, target_rate, subtype='PCM_16')
    if os.path.exists(temp_mp3): os.remove(temp_mp3)
        
@chat_bp.route('/api/chat', methods=['GET', 'POST'])
def chat():
    try:
        args = request.values
        phone = args.get('ApiPhone')
        gemini_key = args.get('gemini_key')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        user_audio = args.get('user_audio')
        
        if args.get('hangup') == 'yes': return ""
        if not phone or phone == 'unknown': return ""

        session = get_session(phone)
        genai.configure(api_key=gemini_key)

        # כניסה ראשונית או איפוס ידני לשלוחה 1 (נושא חדש)
        if not user_audio or request.args.get('new_topic') == 'yes':
            session['history'] = []  # איפוס היסטוריה לטובת נושא חדש
            session['current_topic'] = None
            return f"read=f-greeting=user_audio,,record,,,no"

        # החלפת תווים לא חוקיים בנתיב
        audio_id = user_audio.replace('/', '_').replace('.', '_')

        print(f"מתחיל הורדת הקלטה: {user_audio}")
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
        res = requests.get(download_url)
        if res.status_code != 200: return "id_list_message=t-M1103"
            
        local_audio_path = f"/tmp/input_{phone}.wav"
        with open(local_audio_path, 'wb') as f:
            f.write(res.content)

        uploaded_audio = genai.upload_file(local_audio_path)
        
        # שילוב סיסטם פרומפט קבוע + פרומפט אישי של משתמש משלוחה 3 אם קיים
        full_system_instruction = session['prompt']
        if session['custom_prompt']:
            full_system_instruction += f"\nהנחיה מיוחדת מהמשתמש שחובה ליישם: {session['custom_prompt']}"

        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            system_instruction=full_system_instruction
        )
        
        chat_session = model.start_chat(history=session['history'])
        response = chat_session.send_message([""" אנא הקשב לקובץ השמע המצורף וענה עליו בקיצור נמרץ בתור תשובה למשתמש אבל אל תגיד למשתמש שקיבלת את ההודעה כקובץ שמע אלא א"כ המשתמש מבקש.:""", uploaded_audio])
        answer_text = response.text
        
        # שמירת השיחה ועדכון נושאים במידה ומדובר בתחילת שיחה
        session['history'] = chat_session.history
        if not session['current_topic']:
            session['current_topic'] = audio_id
            # נבקש מג'מיני כותרת קצרה ונסתרת בת 2-3 מילים לנושא
            title_res = model.generate_content(f"תן כותרת קצרה מנוקדת בת 2 עד 3 מילים עבור הטקסט הבא (ללא תווים מיוחדים): {answer_text}")
            session['topics'][audio_id] = title_res.text.strip()

        # יצירת הקובץ עם מזהה ייחודי למניעת באג ה-Cache!
        tts_filename = f"/tmp/{phone}_{audio_id}.wav"
        asyncio.run(generate_tts(answer_text, tts_filename))

        # העלאה תחת שם דינמי וייחודי
        upload_url = f"https://www.call2all.co.il/ym/api/UploadFile"
        with open(tts_filename, 'rb') as f:
            requests.post(upload_url, data={
                'token': f"{yemot_num}:{yemot_pass}",
                'path': f"ivr2:1/{phone}_{audio_id}.wav"
            }, files={'file': f})
        
        if os.path.exists(local_audio_path): os.remove(local_audio_path)
        if os.path.exists(tts_filename): os.remove(tts_filename)

        # החזרת הפקודה עם הקובץ הדינמי החדש!
        return f"read=f-1/{phone}_{audio_id}=user_audio,,record,,,no"
        
    except Exception as e:
        print(traceback.format_exc())
        return "id_list_message=t-M1103"
