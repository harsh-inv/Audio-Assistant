import os
import base64
import time
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image
from io import BytesIO
from gen_ai_hub.proxy.native.google_vertexai.clients import GenerativeModel
from gen_ai_hub.proxy.core.proxy_clients import get_proxy_client

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

# Environment variables
AICORE_AUTH_URL = os.getenv('AICORE_AUTH_URL')
AICORE_CLIENT_ID = os.getenv('AICORE_CLIENT_ID')
AICORE_CLIENT_SECRET = os.getenv('AICORE_CLIENT_SECRET')
AICORE_BASE_URL = os.getenv('AICORE_BASE_URL')
AICORE_RESOURCE_GROUP = os.getenv('AICORE_RESOURCE_GROUP')

# Load model
def load_model():
    try:
        proxy_client = get_proxy_client("gen-ai-hub")
        return GenerativeModel(
            deployment_id="d0f921fd2fef0484",
            model_name="gemini-2.0-flash",
            proxy_client=proxy_client
        )
    except Exception as e:
        print(f"Model loading error: {e}")
        return None

model = load_model()

# Session storage
sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/init_session', methods=['POST'])
def init_session():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id not in sessions:
        sessions[session_id] = {
            'messages': [],
            'files': [],
            'ticket_counter': 0,
            'feedback': []
        }
    
    return jsonify({
        'success': True,
        'files': sessions[session_id]['files'],
        'ticket_counter': sessions[session_id]['ticket_counter']
    })

@app.route('/upload', methods=['POST'])
def upload_file():
    session_id = request.form.get('session_id')
    
    if session_id not in sessions:
        sessions[session_id] = {
            'messages': [],
            'files': [],
            'ticket_counter': 0,
            'feedback': []
        }
    
    uploaded_files = []
    files = request.files.getlist('files')
    
    for file in files:
        if file:
            filename = f"{int(time.time())}_{file.filename}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            sessions[session_id]['files'].append(filename)
            uploaded_files.append(filename)
    
    return jsonify({
        'success': True,
        'files': uploaded_files
    })

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    session_id = data.get('session_id')
    message = data.get('message')
    is_voice_input = data.get('is_voice_input', False)
    
    if session_id not in sessions:
        sessions[session_id] = {
            'messages': [],
            'files': [],
            'ticket_counter': 0,
            'feedback': []
        }
    
    try:
        # Add user message to session
        sessions[session_id]['messages'].append({
            'role': 'user',
            'content': message,
            'timestamp': datetime.now().isoformat()
        })
        
        # Generate response
        if model:
            user_parts = []
            
            # Add text message
            if message:
                user_parts.append({"text": message})
            
            # Add uploaded audio files in the correct format
            for filename in sessions[session_id]['files']:
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.exists(filepath):
                    # Check if it's an audio file
                    if filename.lower().endswith(('.wav', '.mp3', '.aiff', '.aac', '.ogg', '.flac')):
                        with open(filepath, 'rb') as audio_file:
                            audio_data = audio_file.read()
                            # Encode as base64
                            encoded_audio = base64.b64encode(audio_data).decode('utf-8')
                            
                            # Determine MIME type based on extension
                            if filename.lower().endswith('.wav'):
                                mime_type = 'audio/wav'
                            elif filename.lower().endswith('.mp3'):
                                mime_type = 'audio/mp3'
                            elif filename.lower().endswith('.aiff'):
                                mime_type = 'audio/aiff'
                            elif filename.lower().endswith('.aac'):
                                mime_type = 'audio/aac'
                            elif filename.lower().endswith('.ogg'):
                                mime_type = 'audio/ogg'
                            elif filename.lower().endswith('.flac'):
                                mime_type = 'audio/flac'
                            
                            # Add audio in correct format (audio goes first)
                            user_parts.insert(0, {
                                "inline_data": {
                                    "mime_type": mime_type,
                                    "data": encoded_audio
                                }
                            })
            
            # Generate content with properly formatted parts
            response = model.generate_content([
                {"role": "user", "parts": user_parts}
            ])
            bot_response = response.text
            
            # Add bot message to session
            sessions[session_id]['messages'].append({
                'role': 'assistant',
                'content': bot_response,
                'timestamp': datetime.now().isoformat()
            })
            
            return jsonify({
                'success': True,
                'response': bot_response,
                'is_voice_input': is_voice_input,  # Pass back to frontend
                'video': None,
                'video_name': None,
                'session_ended': False
            })
        else:
            return jsonify({
                'error': 'Model not available',
                'response': 'I apologize, but the AI model is currently unavailable.'
            })
    
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({
            'error': str(e),
            'response': 'An error occurred while processing your request.'
        })

@app.route('/api/create-ticket', methods=['POST'])
def create_ticket():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id not in sessions:
        sessions[session_id] = {
            'messages': [],
            'files': [],
            'ticket_counter': 0,
            'feedback': []
        }
    
    # Increment ticket counter
    sessions[session_id]['ticket_counter'] += 1
    ticket_number = f"Q{sessions[session_id]['ticket_counter']:03d}"
    
    # Create ticket data
    ticket_data = {
        'ticket_number': ticket_number,
        'timestamp': datetime.now().isoformat(),
        'session_id': session_id,
        'type': 'quality_inspection'
    }
    
    return jsonify({
        'success': True,
        'ticket_number': ticket_number,
        'message': f'Quality Inspection Ticket {ticket_number} created successfully!'
    })

@app.route('/export/json', methods=['POST'])
def export_json():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id in sessions:
        return jsonify({
            'session_id': session_id,
            'messages': sessions[session_id]['messages'],
            'files': sessions[session_id]['files'],
            'ticket_counter': sessions[session_id]['ticket_counter']
        })
    else:
        return jsonify({'error': 'Session not found'})

@app.route('/clear', methods=['POST'])
def clear_chat():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id in sessions:
        # Delete uploaded files from filesystem
        for filename in sessions[session_id]['files']:
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file {filename}: {e}")
        
        # Clear session data
        sessions[session_id]['messages'] = []
        sessions[session_id]['files'] = []
        
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'Session not found'})


@app.route('/feedback', methods=['POST'])
def submit_feedback():
    data = request.json
    session_id = data.get('session_id')
    rating = data.get('rating')
    comment = data.get('comment', '')
    
    if session_id not in sessions:
        sessions[session_id] = {
            'messages': [],
            'files': [],
            'ticket_counter': 0,
            'feedback': []
        }
    
    feedback_entry = {
        'rating': rating,
        'comment': comment,
        'timestamp': datetime.now().isoformat()
    }
    
    sessions[session_id]['feedback'].append(feedback_entry)
    
    return jsonify({'success': True})

@app.route('/export/feedback', methods=['POST'])
def export_feedback():
    data = request.json
    session_id = data.get('session_id')
    
    if session_id in sessions and sessions[session_id]['feedback']:
        csv_data = "Timestamp,Rating,Comment\n"
        for fb in sessions[session_id]['feedback']:
            csv_data += f"{fb['timestamp']},{fb['rating']},\"{fb['comment']}\"\n"
        
        return jsonify({
            'success': True,
            'csv_data': csv_data,
            'filename': f'feedback_{session_id}.csv'
        })
    else:
        return jsonify({
            'success': False,
            'error': 'No feedback data available'
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

