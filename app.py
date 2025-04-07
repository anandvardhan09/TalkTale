import gradio as gr
import whisper
from gtts import gTTS
import base64
from groq import Groq
from tempfile import NamedTemporaryFile
import os
from pydub import AudioSegment
import numpy as np
from scipy.io import wavfile
import language_tool_python
from flask import Flask, render_template, request, jsonify
import uuid
import json

app = Flask(__name__, static_folder='static')

# Initialize APIs and tools
client = Groq(api_key="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")
model = whisper.load_model("base")
language_tool = language_tool_python.LanguageToolPublicAPI('en-US')

# System prompt with interest integration
def TUTOR_PROMPT(interests):
    return {
        "role": "system",
        "content": f"""You are an English conversation partner. Follow these rules:
1. Keep responses conversational (1-2 sentences max).
2. Focus on {interests} when possible.
3. After each response, add:
##Improvements: [1-2 key areas].
##Suggestions: [better alternatives].
4. Always ask engaging questions.
5. Be supportive and friendly."""
    }

# Store chat histories in memory (in production, use a database)
chat_sessions = {}

def speech_to_text(audio_path):
    result = model.transcribe(audio_path)
    return result["text"]

def text_to_speech(text):
    tts = gTTS(text=text, lang='en', slow=False)
    filename = f"static/audio/response_{uuid.uuid4()}.mp3"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    tts.save(filename)
    return filename

def calculate_fluency_metrics(audio_path, transcription):
    # Calculate speech rate and other metrics
    try:
        audio = AudioSegment.from_file(audio_path)
        duration = len(audio) / 1000  # Convert to seconds
        
        # Word count
        words = transcription.split()
        word_count = len(words)
        
        # Calculate speech rate (words per minute)
        speech_rate = (word_count / duration) * 60 if duration > 0 else 0
        
        # Convert audio to numpy array for pause analysis
        sample_rate, audio_data = wavfile.read(audio_path)
        if len(audio_data.shape) > 1:  # If stereo, convert to mono
            audio_data = np.mean(audio_data, axis=1)
            
        # Normalize audio
        audio_data = audio_data / np.max(np.abs(audio_data)) if np.max(np.abs(audio_data)) > 0 else audio_data
        
        # Detect pauses (simplified)
        is_speech = np.abs(audio_data) > 0.1
        pauses = np.diff(is_speech.astype(int))
        pause_count = np.sum(pauses == 1)
        
        # Error analysis
        matches = language_tool.check(transcription)
        error_rate = len(matches) / word_count if word_count > 0 else 0
        
        return {
            "speech_rate": round(speech_rate, 1),  # Words per minute
            "speaking_time": round(duration, 1),   # Seconds
            "pause_count": pause_count,
            "error_rate": round(error_rate * 100, 1)  # Error percentage
        }
    except Exception as e:
        return {
            "speech_rate": 0,
            "speaking_time": 0,
            "pause_count": 0,
            "error_rate": 0,
            "error": str(e)
        }

def generate_response(user_input, chat_history, interests):
    system_msg = TUTOR_PROMPT(interests)
    messages = [system_msg] + chat_history + [{"role": "user", "content": user_input}]
    
    try:
        response = client.chat.completions.create(
            messages=messages,
            model="llama3-8b-8192",
            temperature=0.7
        )
        full_response = response.choices[0].message.content
        return parse_response(full_response)
    except Exception as e:
        return {"main": "Sorry, I couldn't process your request.", "improvements": "", "suggestions": ""}

def parse_response(response):
    parts = {"main": "", "improvements": "", "suggestions": ""}
    current_section = "main"
    
    for line in response.split('\n'):
        if "##Improvements:" in line:
            current_section = "improvements"
            line = line.replace("##Improvements:", "").strip()
        elif "##Suggestions:" in line:
            current_section = "suggestions"
            line = line.replace("##Suggestions:", "").strip()
        
        parts[current_section] += line + "\n"
    
    # Ensure all parts are populated
    parts = {key: value.strip() if value.strip() else "No feedback provided." for key, value in parts.items()}
    return parts

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/new-chat', methods=['POST'])
def new_chat():
    chat_id = str(uuid.uuid4())
    user_interests = request.json.get('interests', 'general topics')
    chat_sessions[chat_id] = {
        'history': [],
        'interests': user_interests,
        'title': f"Chat {len(chat_sessions) + 1}"
    }
    return jsonify({
        'chatId': chat_id,
        'title': chat_sessions[chat_id]['title']
    })

@app.route('/api/chats', methods=['GET'])
def get_chats():
    chats = []
    for chat_id, chat_data in chat_sessions.items():
        chats.append({
            'id': chat_id,
            'title': chat_data['title']
        })
    return jsonify(chats)

@app.route('/api/chat/<chat_id>', methods=['GET'])
def get_chat(chat_id):
    if chat_id not in chat_sessions:
        return jsonify({'error': 'Chat not found'}), 404
    
    # Convert the chat history to a format suitable for the frontend
    formatted_history = []
    for i in range(0, len(chat_sessions[chat_id]['history']), 2):
        if i + 1 < len(chat_sessions[chat_id]['history']):
            user_msg = chat_sessions[chat_id]['history'][i]['content']
            assistant_msg = chat_sessions[chat_id]['history'][i+1]['content']
            formatted_history.append({
                'user': user_msg,
                'assistant': assistant_msg
            })
    
    return jsonify({
        'chatId': chat_id,
        'title': chat_sessions[chat_id]['title'],
        'messages': formatted_history
    })

@app.route('/api/send-message', methods=['POST'])
def send_message():
    data = request.json
    chat_id = data.get('chatId')
    message = data.get('message')
    
    if not chat_id or not message:
        return jsonify({'error': 'Missing chatId or message'}), 400
    
    if chat_id not in chat_sessions:
        return jsonify({'error': 'Chat not found'}), 404
    
    chat_history = chat_sessions[chat_id]['history']
    interests = chat_sessions[chat_id]['interests']
    
    # Process text message
    response_parts = generate_response(message, chat_history, interests)
    
    # Update chat history
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": response_parts['main']})
    
    # Generate audio response
    audio_path = text_to_speech(response_parts['main'])
    
    return jsonify({
        'message': message,
        'response': response_parts['main'],
        'improvements': response_parts['improvements'],
        'suggestions': response_parts['suggestions'],
        'audio': '/' + audio_path,
        'fluency': {
            'speech_rate': 0,  # Text input has no speech metrics
            'speaking_time': 0,
            'pause_count': 0,
            'error_rate': 0
        }
    })

@app.route('/api/send-audio', methods=['POST'])
def send_audio():
    if 'audio' not in request.files:
        return jsonify({'error': 'No audio file provided'}), 400
    
    chat_id = request.form.get('chatId')
    if not chat_id:
        return jsonify({'error': 'Missing chatId'}), 400
    
    if chat_id not in chat_sessions:
        return jsonify({'error': 'Chat not found'}), 404
    
    audio_file = request.files['audio']
    audio_path = f"temp_{uuid.uuid4()}.webm"
    audio_file.save(audio_path)
    
    try:
        # Speech to text
        user_text = speech_to_text(audio_path)
        
        # Calculate fluency metrics
        fluency_metrics = calculate_fluency_metrics(audio_path, user_text)
        
        chat_history = chat_sessions[chat_id]['history']
        interests = chat_sessions[chat_id]['interests']
        
        # Get response components
        response_parts = generate_response(user_text, chat_history, interests)
        
        # Update chat history
        chat_history.append({"role": "user", "content": user_text})
        chat_history.append({"role": "assistant", "content": response_parts['main']})
        
        # Generate audio response
        audio_response_path = text_to_speech(response_parts['main'])
        
        # Clean up temporary file
        os.remove(audio_path)
        
        return jsonify({
            'message': user_text,
            'response': response_parts['main'],
            'improvements': response_parts['improvements'],
            'suggestions': response_parts['suggestions'],
            'audio': '/' + audio_response_path,
            'fluency': fluency_metrics
        })
    
    except Exception as e:
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/rename-chat', methods=['PUT'])
def rename_chat():
    data = request.json
    chat_id = data.get('chatId')
    new_title = data.get('title')
    
    if not chat_id or not new_title:
        return jsonify({'error': 'Missing chatId or title'}), 400
    
    if chat_id not in chat_sessions:
        return jsonify({'error': 'Chat not found'}), 404
    
    chat_sessions[chat_id]['title'] = new_title
    return jsonify({'success': True})

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs('static/audio', exist_ok=True)
    app.run(debug=True)
