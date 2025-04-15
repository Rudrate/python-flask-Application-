import os
import subprocess
import soundfile as sf
import noisereduce as nr
import uuid
import json
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
import fitz

# Vertex AI imports for LLM operations
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import texttospeech

app = Flask(__name__)
app.secret_key = "secure_random_key"  # Update with an appropriate secret key

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# File to persist conversation history (using JSON Lines)
HISTORY_FILE = os.path.join(UPLOAD_FOLDER, "conversation_history.txt")

# Initialize Vertex AI with your project details
project_id = 'python-flash-website'  # Update with your project ID as necessary
vertexai.init(project=project_id, location="us-central1")
model = GenerativeModel("gemini-1.5-flash-001")

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'webm', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_webm_to_wav(in_path):
    wav_path = in_path.replace('.webm', '.wav')
    try:
        subprocess.run(['ffmpeg', '-i', in_path, '-ac', '1', '-ar', '16000', wav_path], check=True)
        os.remove(in_path)  # Remove the original WebM file
        return wav_path
    except Exception as e:
        print(f"[ERROR] WebM to WAV conversion failed: {e}")
        return None

def convert_wav_to_mp3(in_path):
    mp3_path = in_path.replace('.wav', '.mp3')
    try:
        subprocess.run(['ffmpeg', '-i', in_path, '-ac', '1', '-ar', '16000', '-b:a', '128k', mp3_path], check=True)
        return mp3_path
    except Exception as e:
        print(f"[ERROR] WAV to MP3 conversion failed: {e}")
        return None

def reduce_noise(audio_path):
    try:
        data, sr = sf.read(audio_path, dtype='float32')
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        cleaned = nr.reduce_noise(y=data, sr=sr, y_noise=data[:sr])
        sf.write(audio_path, cleaned, sr)
    except Exception as e:
        print(f"[WARNING] Noise reduction failed: {e}")

def extract_pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    text_data = ""
    for page in doc:
        text_data += page.get_text()
    doc.close()
    return text_data

# Global variable for storing book text
book_text = ""

@app.route('/upload_pdf', methods=['POST'])
def upload_pdf():
    global book_text
    if 'bookPdf' not in request.files:
        return "No file part", 400
    pdf_file = request.files['bookPdf']
    if pdf_file.filename == '':
        return "No file selected", 400
    if not allowed_file(pdf_file.filename):
        return "Unsupported file", 400

    filename = secure_filename(pdf_file.filename)
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    pdf_file.save(pdf_path)
    book_text = extract_pdf_text(pdf_path)
    return "Book uploaded and parsed successfully!", 200

def text_to_speech(text):
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US", ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=config)
    out_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
    out_path = os.path.join(UPLOAD_FOLDER, out_name)
    with open(out_path, 'wb') as f:
        f.write(response.audio_content)
    return out_name

# ---- UPDATED CONVERSATION HISTORY FUNCTIONS ----

def append_history(question, answer, tts_filename):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history_entry = {
        "timestamp": timestamp,
        "question": question,
        "answer": answer,
        "audio": tts_filename
    }
    with open(HISTORY_FILE, 'a') as file:
        file.write(json.dumps(history_entry) + "\n")

def load_history():
    history_entries = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as file:
            for line in file:
                if line.strip():
                    try:
                        entry = json.loads(line.strip())
                        history_entries.append(entry)
                    except json.JSONDecodeError as e:
                        print(f"[WARNING] Could not decode history entry: {e}")
    return history_entries

# -------------------------------------------------

@app.route('/')
def index():
    history = load_history()
    recorded_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.mp3')]
    return render_template('index.html', conversation_history=history, audio_files=recorded_files)

@app.route('/ask_book', methods=['POST'])
def ask_book():
    global book_text
    if not book_text:
        return jsonify({'error': 'Please upload a book first.'}), 400
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio data received.'}), 400

    file = request.files['audio_data']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid or missing file.'}), 400

    # Save the uploaded audio (WebM format)
    webm_name = secure_filename(f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.webm")
    webm_path = os.path.join(UPLOAD_FOLDER, webm_name)
    file.save(webm_path)

    wav_path = convert_webm_to_wav(webm_path)
    if not wav_path:
        return jsonify({'error': 'Conversion to WAV failed.'}), 500
    reduce_noise(wav_path)
    mp3_file = convert_wav_to_mp3(wav_path)
    if not mp3_file:
        return jsonify({'error': 'Conversion to MP3 failed.'}), 500

    try:
        with open(wav_path, 'rb') as f:
            audio_bytes = f.read()
        trans_prompt = "Please transcribe this audio:"
        audio_part = Part.from_data(audio_bytes, mime_type="audio/wav")
        contents = [audio_part, trans_prompt]
        trans_response = model.generate_content(contents)
        question_text = trans_response.text.strip()
    except Exception as e:
        print(f"[ERROR] Transcription failed: {e}")
        return jsonify({'error': 'Transcription error.'}), 500

    try:
        combined_prompt = f"""
        Below is the content of a book:
        {book_text}
        
        The user asks:
        "{question_text}"
        
        Please provide a concise, informative answer based on the book.
        """
        prompt_part = Part.from_text(combined_prompt)
        answer_response = model.generate_content([prompt_part])
        answer_text = answer_response.text.strip()
    except Exception as e:
        print(f"[ERROR] LLM processing failed: {e}")
        return jsonify({'error': 'Answer generation error.'}), 500

    try:
        tts_filename = text_to_speech(answer_text)
    except Exception as e:
        print(f"[ERROR] Text-to-Speech failed: {e}")
        return jsonify({'error': 'TTS error.'}), 500

    append_history(question_text, answer_text, tts_filename)

    return jsonify({
        'transcribed_question': question_text,
        'answer_text': answer_text,
        'tts_file': tts_filename
    }), 200

@app.route('/uploads/<filename>')
def get_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    print("[INFO] Starting Book Interaction Hub on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=True)
