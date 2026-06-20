from flask import Flask
from modules.chat import chat_bp
from modules.settings import settings_bp

app = Flask(__name__)

# רישום המודולים - ניתן להוסיף עוד מודולים בעתיד ללא שינוי הלוגיקה פה
app.register_blueprint(chat_bp)
app.register_blueprint(settings_bp)

@app.route('/')
def index():
    return "Server is running!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)