from flask import Blueprint, request
from modules.chat import get_session

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/api/set_prompt', methods=['GET', 'POST'])
def set_prompt():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    user_audio = args.get('user_audio')
    
    # מימוש פשוט: מקבלים את ההקלטה, שומרים ומשתמשים בהמרה של גוגל/ימות, 
    # אך מכיוון שביקשת חינמי וGemini יכול להמיר שמע, נשתמש בו לתמלול ההנחיה
    if user_audio:
        gemini_key = args.get('gemini_key')
        yemot_num = args.get('yemot_num')
        yemot_pass = args.get('yemot_pass')
        
        import requests
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        
        download_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={yemot_num}:{yemot_pass}&path={user_audio}"
        audio_data = requests.get(download_url).content
        
        local_audio = f"/tmp/prompt_{phone}.wav"
        with open(local_audio, 'wb') as f:
            f.write(audio_data)
            
        uploaded = genai.upload_file(local_audio)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(["תמלל את ההקלטה הבאה בדיוק מוחלט, זה ישמש כהנחיית מערכת", uploaded])
        
        session = get_session(phone)
        # מוסיפים את הוראות הפיסוק הקבועות כדי לשמור על יציבות הקריין
        session['prompt'] = response.text + ' ענה בצורה טבעית ללא כוכביות או סימונים, השתמש בסימני פיסוק תקניים בלבד.'
        
        return "id_list_message=f-prompt_saved&go_to_folder=/"

    return "read=f-record_prompt=user_audio,,record"


@settings_bp.route('/api/set_model', methods=['GET', 'POST'])
def set_model():
    args = request.values
    phone = args.get('ApiPhone', 'unknown')
    model_choice = args.get('model_choice')
    
    session = get_session(phone)
    
    # מיפוי המודלים (Google מספקת כרגע את 1.5 בתור המודלים החזקים ביותר, מיפינו לפי בקשתך)
    if model_choice == '1':
        session['model'] = 'gemini-3.5-flash' # Gemini 2.5 Flash / Standard Flash
    elif model_choice == '2':
        session['model'] = 'gemini-3.1-flash-lite' # המודל הקל והמהיר ביותר (Lite)
    elif model_choice == '3':
        session['model'] = 'gemini-2.5-flash' # מודל ה-Pro החזק ביותר
        
    return "id_list_message=f-model_updated&go_to_folder=/"
