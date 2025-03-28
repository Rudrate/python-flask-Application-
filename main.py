import os
import subprocess
import soundfile as sf
import noisereduce as nr
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime


import vertexai
from vertexai.generative_models import GenerativeModel, Part

app = Flask(__name__)
app.secret_key = "secure_random_key"


UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Setting the project ID and initialize Vertex AI
project_id = 'python-flash-website'
vertexai.init(project=project_id, location="us-central1")
model = GenerativeModel("gemini-1.5-flash-001")

ALLOWED_EXTENSIONS = {'wav', 'mp3', 'webm'}

# Prompt that instructs the LLM to provide transcript + sentiment
MODEL_PROMPT = """
Please provide an exact transcript for the audio, followed by sentiment analysis.

Your response should follow the format:

Text: USERS SPEECH TRANSCRIPTION

Sentiment Analysis: positive|neutral|negative
"""

def is_audio_file(filename):
    """Check if file extension is supported."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def webm_to_wav(source_path):
    """Convert WebM to WAV using ffmpeg."""
    output_wav = source_path.replace('.webm', '.wav')
    try:
        subprocess.run(['ffmpeg', '-i', source_path, '-ac', '1', '-ar', '16000', output_wav], check=True)
        os.remove(source_path) 
        return output_wav
    except Exception as e:
        print(f"[ERROR] WebM to WAV conversion failed: {e}")
        return None

def wav_to_mp3(source_path):
    """Convert WAV to MP3 using ffmpeg."""
    output_mp3 = source_path.replace('.wav', '.mp3')
    try:
        subprocess.run(['ffmpeg', '-i', source_path, '-ac', '1', '-ar', '16000', '-b:a', '128k', output_mp3], check=True)
        return output_mp3
    except Exception as e:
        print(f"[ERROR] WAV to MP3 conversion failed: {e}")
        return None

def remove_background_noise(audio_path):
    """Apply noise reduction using noisereduce."""
    try:
        audio_data, sample_rate = sf.read(audio_path, dtype='float32')
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)  
        clean_audio = nr.reduce_noise(y=audio_data, sr=sample_rate, y_noise=audio_data[:sample_rate])
        sf.write(audio_path, clean_audio, sample_rate)
    except Exception as e:
        print(f"[WARNING] Noise reduction failed: {e}")

@app.route('/')
def homepage():
    """Render the index page with a list of recorded MP3 files."""
    recorded_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.mp3')]
    return render_template('index.html', audio_files=recorded_files)

@app.route('/upload', methods=['POST'])
def handle_audio_upload():
    """
    1) Receive an audio file from the user.
    2) Convert webm -> wav -> (noise reduce) -> mp3.
    3) Call Vertex AI (Gemini) to get transcript & sentiment in a single step.
    4) Save transcript & sentiment to text files.
    """
    if 'audio_data' not in request.files:
        return jsonify({'error': 'No audio data received'}), 400

    file = request.files['audio_data']
    if file.filename == '' or not is_audio_file(file.filename):
        return jsonify({'error': 'Invalid file type or empty filename'}), 400

    # Savint the initial webm file
    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.webm")
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)
    print(f"[INFO] Uploaded file: {file_path}")

    # Converting WebM to WAV
    wav_file = webm_to_wav(file_path)
    if not wav_file:
        return jsonify({'error': 'WebM to WAV conversion failed'}), 500

    # Applying noise reduction (optional)
    remove_background_noise(wav_file)

    # Converting  WAV to MP3 for playback
    mp3_file = wav_to_mp3(wav_file)
    if not mp3_file:
        return jsonify({'error': 'WAV to MP3 conversion failed'}), 500

    # Single call to Vertex AI for transcript + sentiment
    try:
        with open(wav_file, 'rb') as f:
            audio_bytes = f.read()

        # Wrapping the audio in a Part object and attach the prompt
        audio_part = Part.from_data(audio_bytes, mime_type="audio/wav")
        contents = [audio_part, MODEL_PROMPT]

        response = model.generate_content(contents)
        print("[INFO] LLM response:", response.text)

        # Parsing the response; expected format:
        # "Text: <transcript>"
        # "Sentiment Analysis: <positive|neutral|negative>"
        transcript_line, sentiment_line = "", ""
        for line in response.text.splitlines():
            if line.startswith("Text:"):
                transcript_line = line.replace("Text:", "").strip()
            elif line.startswith("Sentiment Analysis:"):
                sentiment_line = line.replace("Sentiment Analysis:", "").strip()

        # Saving the transcript to a text file
        transcript_path = wav_file.replace('.wav', '.txt')
        with open(transcript_path, 'w') as txt_file:
            txt_file.write(transcript_line)

        # Saving the sentiment analysis to a separate text file
        sentiment_path = transcript_path.replace('.txt', '_sentiment.txt')
        with open(sentiment_path, 'w') as s_file:
            s_file.write(f"Text: {transcript_line}\n")
            s_file.write(f"Sentiment: {sentiment_line}\n")

        return jsonify({
            'processed_file': os.path.basename(mp3_file),
            'transcription_file': os.path.basename(transcript_path),
            'sentiment': sentiment_line,
            'sentiment_analysis_file': os.path.basename(sentiment_path)
        }), 200

    except Exception as e:
        print(f"[ERROR] Vertex AI processing failed: {e}")
        return jsonify({'error': 'Vertex AI processing failed'}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve files (MP3, .txt) from the uploads directory."""
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    print("[INFO] Starting Flask on port 8080...")
    app.run(host='0.0.0.0', port=8080, debug=True)
