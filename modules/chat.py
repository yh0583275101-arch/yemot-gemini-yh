import os
import json
import requests
import asyncio
import edge_tts
from flask import Blueprint, request
import google.generativeai as genai
import traceback
import soundfile as sf
from scipy.signal import resample

chat_bp = Blueprint('chat', __name__)

# פרומפט קבוע בסיסי
SYSTEM_PROMPT = """אתה עוזר קולי חכם ואישי בטלפון בשם גִ'ינְגֶ'ר. המין שלך הוא זכר לכן כשאתה מדבר על עצמך תדבר בלשון זכר. המפתח שבנה אותך הוא סְמַרְטי גִ'ינְגֶ'ר אפליקציות בע"מ. ענה למשתמש בצורה טובה, ברורה ומפורטת, ותזהה לפי הקול האם מי שמדבר זה זכר או נקבה ולפי התוצאה תדבר אליו בלשון של המין שלו שזיהת בהקלטה, אך הקפד לא להאריך יותר מדי . חובה להוסיף סימני פיסוק תקניים (נקודות, פסיקים, סימני שאלה). הקפד להשתמש בסימני קריאה (!) במשפטים שדורשים הדגשה, התלהבות או טון דרמטי יותר. וכששלחו לך בשאלה טקסט מנוקד ואתה חוזר על אותה מילה מנוקדת תנקד אותה לפי הניקוד שהיה במילה ששלחו לך בשאלה. אל תשתמש בשום פנים ואופן בכוכביות (**), סולמיות (#) או סימוני טקסט מיוחדים."""

# פונקציות עזר לעבודה מול ה-API של ימות המשיח
def download_ym_text(yemot_num, yemot_pass, path):
    url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{path}"
    res = requests.get(url)
    return res.text.strip() if res.status_code == 200 else ""

def upload_ym_bytes(yemot_num, yemot_pass, path, content_bytes, filename="file.txt"):
    url = "https://www.call2all.co.il/ym/api/UploadFile"
    res = requests.post(url, data={
        'token': f"{yemot_num}:{yemot_pass}",
        'path': f"ivr2:{path}"
    }, files={'file': (filename, content_bytes)})
    return res.status_code == 200

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

def process_chat_turn(phone, gemini_key, yemot_num, yemot_pass, user_audio, topic_id, is_new_topic=False):
    # 1. הורדת קובץ השמע שהמשתמש הקליט
    download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path=ivr2:{user_audio}"
    res = requests.get(download_url)
    if res.status_code != 200:
        return "id_list_message=t-M1103"
        
    local_audio_path = f"/tmp/input_{phone}.wav"
    with open(local_audio_path, 'wb') as f:
        f.write(res.content)
        
    # 2. טעינת היסטוריית השיחה מקובץ טקסט/JSON בשלוחה 2
    history_path = f"2/{topic_id}/history.json"
    history_text = download_ym_text(yemot_num, yemot_pass, history_path)
    history = json.loads(history_text) if history_text else []
    
    # חישוב אינדקס הקובץ הבא (למשל: 001 לשאלה ראשונה, 002 לתשובה ראשונה)
    file_idx = len(history) * 2 + 1
    
    # ארכוב שאלת המשתמש ישירות בתוך תיקיית הנושא בשלוחה 2!
    with open(local_audio_path, 'rb') as f:
        upload_ym_bytes(yemot_num, yemot_pass, f"2/{topic_id}/{file_idx:03d}.wav", f.read(), f"{file_idx:03d}.wav")
        
    # 3. העלאה לג'מיני וקבלת תשובה
    genai.configure(api_key=gemini_key)
    uploaded_audio = genai.upload_file(local_audio_path)
    
    # קריאת פרומפט אישי משלוחה 3 אם קיים
    custom_prompt = download_ym_text(yemot_num, yemot_pass, f"3/{phone}_prompt.txt")
    full_system_instruction = SYSTEM_PROMPT
    if custom_prompt:
        full_system_instruction += f"\nהנחיה מיוחדת מהמשתמש שחובה ליישם: {custom_prompt}"
        
    model = genai.GenerativeModel(model_name='gemini-2.5-flash', system_instruction=full_system_instruction)
    chat_session = model.start_chat(history=history)
    response = chat_session.send_message(["אנא הקשב לקובץ וענה עליו בהתאם להנחיות:", uploaded_audio])
    answer_text = response.text
    
    # שמירת ההיסטוריה המעודכנת בחזרה לימות המשיח
    updated_history_data = []
    for msg in chat_session.history:
        updated_history_data.append({
            'role': msg.role,
            'parts': [part.text for part in msg.parts if hasattr(part, 'text')]
        })
    upload_ym_bytes(yemot_num, yemot_pass, history_path, json.dumps(updated_history_data).encode('utf-8'), "history.json")
    
    # 4. יצירת קובץ ה-TTS של התשובה של אברי
    ans_idx = file_idx + 1
    tts_filename = f"/tmp/ans_{phone}.wav"
    asyncio.run(generate_tts(answer_text, tts_filename))
    
    # העלאת תשובת אברי ישירות לתיקיית הנושא בשלוחה 2
    with open(tts_filename, 'rb') as f:
        upload_ym_bytes(yemot_num, yemot_pass, f"2/{topic_id}/{ans_idx:03d}.wav", f.read(), f"{ans_idx:03d}.wav")
        
    # אם זה נושא חדש, מייצרים כותרת ומעדכנים את רשימת הנושאים האישית של המשתמש
    if is_new_topic and file_idx == 1:
        title_res = model.generate_content(f"תן כותרת קצרה מנוקדת בת 2 עד 3 מילים עבור הטקסט הבא (ללא תווים מיוחדים): {answer_text}")
        title = title_res.text.strip()
        topics_path = f"2/{phone}_topics.txt"
        topics_text = download_ym_text(yemot_num, yemot_pass, topics_path)
        new_topics_text = (topics_text + f"\n{topic_id}|{title}").strip()
        upload_ym_bytes(yemot_num, yemot_pass, topics_path, new_topics_text.encode('utf-8'), f"{phone}_topics.txt")
        
    if os.path.exists(local_audio_path): os.remove(local_audio_path)
    if os.path.exists(tts_filename): os.remove(tts_filename)
    
    # השמעת התשובה מתוך שלוחה 2, והמשך הקלטה רציפה ישירות לשם!
    return f"read=f-2/{topic_id}/{ans_idx:03d}=user_audio,,record,,,no"

# --- שלוחה 1: שיחה חדשה ---
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
        
        # כניסה ראשונית לשלוחה 1 - יצירת נושא חדש לגמרי
        if not user_audio or user_audio == "1":
            topics_text = download_ym_text(yemot_num, yemot_pass, "2/topics.txt")
            existing_topics = [line for line in topics_text.split('\n') if '|' in line]
            topic_id = len(existing_topics) + 1
            
            # שמירת מזהה הנושא הנוכחי בקובץ טקסט ייעודי למשתמש בשלוחה 1
            upload_ym_bytes(yemot_num, yemot_pass, f"1/{phone}_current_topic.txt", str(topic_id).encode('utf-8'), f"{phone}_current_topic.txt")
            
            # יצירת קובץ ext.ini אוטומטי בתוך התיקייה החדשה בשלוחה 2
            ini_content = "type=play_folder\nplay_folder_stars_go_to=/4\n"
            upload_ym_bytes(yemot_num, yemot_pass, f"2/{topic_id}/ext.ini", ini_content.encode('utf-8'), "ext.ini")
            
            return "read=f-greeting=user_audio,,record,,,no"
            
        # המשך שיחה קיימת בשלוחה 1
        topic_id = download_ym_text(yemot_num, yemot_pass, f"1/{phone}_current_topic.txt")
        if not topic_id: topic_id = "1"
        
        return process_chat_turn(phone, gemini_key, yemot_num, yemot_pass, user_audio, topic_id, is_new_topic=True)
        
    except Exception as e:
        print(traceback.format_exc())
        return "id_list_message=t-M1103"

# --- שלוחה 4: המשך שיחה קיימת מההיסטוריה (כשלוחצים כוכבית בשלוחה 2) ---
@chat_bp.route('/api/continue_chat', methods=['GET', 'POST'])
def continue_chat():
    try:
        args = request.values
        phone = args.get('ApiPhone')
        gemini_key = args.get('gemini_key')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        user_audio = args.get('user_audio')
        
        if args.get('hangup') == 'yes': return ""
        if not phone or phone == 'unknown': return ""
        
        # כניסה ראשונית לשלוחה 4 (מיד לאחר שהקיש כוכבית בשלוחה 2)
        if not user_audio:
            topic_id = download_ym_text(yemot_num, yemot_pass, f"2/{phone}_last_selected.txt")
            if not topic_id: topic_id = "1"
            upload_ym_bytes(yemot_num, yemot_pass, f"4/{phone}_current_topic.txt", topic_id.encode('utf-8'), f"{phone}_current_topic.txt")
            return "read=M1006=user_audio,,record,,,no"
            
        # המשך שיחה רציפה בשלוחה 4
        topic_id = download_ym_text(yemot_num, yemot_pass, f"4/{phone}_current_topic.txt")
        if not topic_id: topic_id = "1"
        
        return process_chat_turn(phone, gemini_key, yemot_num, yemot_pass, user_audio, topic_id, is_new_topic=False)
        
    except Exception as e:
        print(traceback.format_exc())
        return "id_list_message=t-M1103"

@chat_bp.route('/api/error', methods=['GET', 'POST'])
def handle_error():
    return "OK"
