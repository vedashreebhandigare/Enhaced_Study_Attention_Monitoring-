from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
import cv2
import numpy as np
import mediapipe as mp
try:
    from tensorflow.keras.models import load_model
except ImportError:
    try:
        from tensorflow import keras
        from keras.models import load_model
    except ImportError:
        import keras
        from keras.models import load_model
import time
from threading import Thread
import json
import os
from datetime import datetime
import google.generativeai as genai
import PyPDF2
from docx import Document
import re
import requests
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Allowed file extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'ppt', 'pptx'}

# Configure Gemini AI
GEMINI_API_KEY = "AIzaSyD3IaCa-CJAHLCDWlOpNDK8SJ4b6-Q0n9s"
genai.configure(api_key=GEMINI_API_KEY)

# YouTube API Configuration
YOUTUBE_API_KEY = "AIzaSyCSsPt25p-K2Q3gShm3PocbDja_EEGIq1Q"

# Optimized generation config for faster, well-formatted responses
generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,
}

# Use Gemini 2.5 Flash - VERIFIED WORKING with your API key
gemini_model = genai.GenerativeModel(
    'gemini-2.5-flash',
    generation_config=generation_config
)

# Document content cache (stores extracted text from uploaded documents)
document_content_cache = {}

# Global variables for status
current_status = {
    'status': 'focused',
    'confidence': 0.0,
    'face_found': False,
    'ear_value': 0.0,
    'yawn_prob': 0.0,
    'timestamp': time.time()
}

# Load model with multiple fallback methods
yawn_model = None
print("Attempting to load yawn model...")

# Method 1: Try standard loading with compile=False
try:
    yawn_model = load_model("yawn_model.h5", compile=False)
    print("✅ Yawn model loaded successfully (method 1)")
except Exception as e1:
    print(f"❌ Method 1 failed: {e1}")
    
    # Method 2: Try with custom_objects
    try:
        yawn_model = load_model("yawn_model.h5", compile=False, custom_objects={})
        print("✅ Yawn model loaded successfully (method 2)")
    except Exception as e2:
        print(f"❌ Method 2 failed: {e2}")
        
        # Method 3: Try loading just weights if architecture is known
        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import Conv2D, MaxPooling2D, Flatten, Dense, Dropout, BatchNormalization
            
            # Recreate the EXACT CNN architecture from yawn.ipynb
            yawn_model = Sequential([
                Conv2D(32, (3, 3), activation='relu', input_shape=(24, 24, 3)),
                BatchNormalization(),
                MaxPooling2D(2, 2),
                Conv2D(64, (3, 3), activation='relu'),
                BatchNormalization(),
                MaxPooling2D(2, 2),
                Conv2D(128, (3, 3), activation='relu'),
                BatchNormalization(),
                MaxPooling2D(2, 2),
                Flatten(),
                Dropout(0.5),
                Dense(512, activation='relu'),
                Dense(1, activation='sigmoid')  # Binary classification for yawn/no-yawn
            ])
            
            yawn_model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
            
            # Try to load weights
            yawn_model.load_weights("yawn_model.h5")
            print("✅ Yawn model architecture recreated and weights loaded (method 3)")
        except Exception as e3:
            print(f"❌ Method 3 failed: {e3}")
            
            # Method 4: Create a dummy model for testing
            print("⚠️  Creating dummy model for testing (yawn detection will be simulated)")
            yawn_model = None

if yawn_model is None:
    print("⚠️  Yawn detection will use fallback method (mouth aspect ratio only)")

# MediaPipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5)

# Constants - Improved drowsiness detection  
YAWN_THRESHOLD = 0.85  # Increased threshold to avoid false positives
YAWN_CONSEC_FRAMES = 17  # Number of consecutive frames for yawn detection
ALERT_COOLDOWN = 5
NOT_ATTENTIVE_THRESHOLD = 3  # Reduced from 6 to 3 seconds for faster detection
DROWSY_EAR_THRESHOLD = 0.27  # More conservative - only very droopy eyes
DROWSY_CONSEC_FRAMES = 10    # Slightly increased for stability
NODDING_THRESHOLD = 15       # Reduced from 25 - more sensitive to subtle head movements

# Landmark indices - UNCHANGED
LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385]
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
CHIN_POINT = 175
NOSE_TIP = 1
FOREHEAD_POINT = 10

# State variables - Enhanced for gradual drowsiness detection
yawn_counter = 0
last_alert_time = 0
last_attentive_time = time.time()
yawn_probs = []
drowsy_counter = 0
drowsiness_score = 0  # Accumulates gradually over time
recent_ear_values = []  # Track recent EAR values for smoother detection

# Distraction alert system
last_distraction_alert = 0
distraction_alert_count = 0
DISTRACTION_ALERT_INTERVAL = 10  # Alert every 10 seconds when distracted

# Motivational messages for distraction alerts
MOTIVATIONAL_MESSAGES = [
    "🎯 Stay focused! You've got this!",
    "💪 Remember your goals - keep pushing forward!",
    "🌟 Every moment of focus brings you closer to success!",
    "🔥 You're capable of amazing things - stay concentrated!",
    "⚡ Focus is your superpower - use it wisely!",
    "🎊 Great minds focus on what matters - like yours!",
    "🚀 Your future self will thank you for staying focused!",
    "💎 Diamonds are formed under pressure - stay strong!",
    "🏆 Champions are made through focused effort!",
    "🌅 Each focused minute is an investment in your dreams!"
]
not_present_alerted = False

# Session Statistics Tracking
session_stats = {
    'yawn_count': 0,
    'drowsy_count': 0,
    'distraction_count': 0,
    'not_present_count': 0,
    'focused_time': 0,
    'distracted_time': 0,
    'drowsy_time': 0,
    'not_present_time': 0,
    'last_state': 'focused',
    'state_start_time': time.time()
}
chin_positions = []
nodding_counter = 0
previous_chin_y = None
mar_list = []

# All detection functions - UNCHANGED from original
def mouth_aspect_ratio(landmark_coords):
    A = np.linalg.norm(np.array(landmark_coords[13]) - np.array(landmark_coords[14]))
    B = np.linalg.norm(np.array(landmark_coords[78]) - np.array(landmark_coords[82]))
    if B == 0:
        return 0
    return A / B

def smoothed_mar(current_mar, window=5):
    global mar_list
    mar_list.append(current_mar)
    if len(mar_list) > window:
        mar_list.pop(0)
    return sum(mar_list) / len(mar_list)

def eye_aspect_ratio(eye_points):
    if len(eye_points) < 6:
        return 0
    
    A = np.linalg.norm(np.array(eye_points[1]) - np.array(eye_points[5]))
    B = np.linalg.norm(np.array(eye_points[2]) - np.array(eye_points[4]))
    C = np.linalg.norm(np.array(eye_points[0]) - np.array(eye_points[3]))
    
    if C == 0:
        return 0
    return (A + B) / (2.0 * C)

def detect_nodding(landmark_coords):
    global chin_positions, nodding_counter, previous_chin_y
    
    try:
        chin_y = landmark_coords[CHIN_POINT][1]
        
        chin_positions.append(chin_y)
        if len(chin_positions) > 10:
            chin_positions.pop(0)
        
        if len(chin_positions) >= 5:
            recent_positions = chin_positions[-5:]
            movement_range = max(recent_positions) - min(recent_positions)
            
            if movement_range > NODDING_THRESHOLD:
                nodding_counter += 1
            else:
                nodding_counter = max(0, nodding_counter - 1)
            
            # Reduced threshold for more gradual detection
            return nodding_counter > 5
        
    except Exception as e:
        print(f"Nodding detection error: {e}")
    
    return False

# ============= DOCUMENT PARSING HELPER FUNCTIONS =============

def update_session_stats(new_status):
    """Update session statistics based on status changes"""
    global session_stats
    
    current_time = time.time()
    time_in_state = current_time - session_stats['state_start_time']
    
    # Update time for previous state
    if session_stats['last_state'] == 'focused':
        session_stats['focused_time'] += time_in_state
    elif session_stats['last_state'] in ['not_present', 'distracted']:
        session_stats['distracted_time'] += time_in_state
    elif session_stats['last_state'] == 'drowsy':
        session_stats['drowsy_time'] += time_in_state
    elif session_stats['last_state'] == 'yawning':
        session_stats['drowsy_time'] += time_in_state  # Count yawning as drowsy time
    
    # Increment event counters when transitioning TO these states
    if new_status != session_stats['last_state']:
        if new_status == 'yawning':
            session_stats['yawn_count'] += 1
        elif new_status == 'drowsy':
            session_stats['drowsy_count'] += 1
        elif new_status == 'not_present':
            session_stats['distraction_count'] += 1
    
    # Update state tracking
    session_stats['last_state'] = new_status
    session_stats['state_start_time'] = current_time

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF file"""
    try:
        text = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return None

def extract_text_from_docx(docx_path):
    """Extract text from DOCX file"""
    try:
        doc = Document(docx_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        print(f"Error extracting DOCX text: {e}")
        return None

def extract_text_from_txt(txt_path):
    """Extract text from TXT file"""
    try:
        with open(txt_path, 'r', encoding='utf-8') as file:
            return file.read().strip()
    except Exception as e:
        print(f"Error reading TXT file: {e}")
        return None

def extract_document_content(filename):
    """Extract content from uploaded document based on file type"""
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(file_path):
        return None
    
    # Get file extension
    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    # Extract based on file type
    if file_ext == 'pdf':
        return extract_text_from_pdf(file_path)
    elif file_ext in ['doc', 'docx']:
        return extract_text_from_docx(file_path)
    elif file_ext == 'txt':
        return extract_text_from_txt(file_path)
    else:
        return None

def get_all_documents_content():
    """Get combined content from all uploaded documents in session"""
    uploaded_files = session.get('uploaded_files', [])
    
    if not uploaded_files:
        return None
    
    combined_content = []
    for filename in uploaded_files:
        # Check cache first
        if filename in document_content_cache:
            content = document_content_cache[filename]
        else:
            # Extract and cache
            content = extract_document_content(filename)
            if content:
                document_content_cache[filename] = content
        
        if content:
            combined_content.append(f"=== Content from {filename} ===\n{content}\n")
    
    return "\n\n".join(combined_content) if combined_content else None

# ============= END OF DOCUMENT PARSING FUNCTIONS =============


def generate_frames():
    global current_status, yawn_counter, last_alert_time, last_attentive_time
    global yawn_probs, drowsy_counter, not_present_alerted, drowsiness_score, recent_ear_values
    global last_distraction_alert, distraction_alert_count, session_stats
    
    cap = cv2.VideoCapture(0)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        face_found = False
        face_forward = True
        status = 'focused'
        confidence = 0.0

        if results.multi_face_landmarks:
            face_found = True
            face_landmarks = results.multi_face_landmarks[0]
            landmark_coords = [(int(p.x * w), int(p.y * h)) for p in face_landmarks.landmark]

            # Face orientation check - IMPROVED sensitivity
            nose_x = landmark_coords[1][0]
            left_eye_x = landmark_coords[33][0]
            right_eye_x = landmark_coords[263][0]
            face_center_x = (left_eye_x + right_eye_x) // 2
            deviation = abs(nose_x - face_center_x)

            # More sensitive detection - reduced from 40 to 25 pixels
            if deviation > 25:
                face_forward = False

            if face_forward:
                last_attentive_time = time.time()
                not_present_alerted = False

            # Gradual drowsiness detection - Improved logic
            try:
                left_eye_pts = [landmark_coords[i] for i in LEFT_EYE[:6]]
                right_eye_pts = [landmark_coords[i] for i in RIGHT_EYE[:6]]
                
                left_ear = eye_aspect_ratio(left_eye_pts)
                right_ear = eye_aspect_ratio(right_eye_pts)
                avg_ear = (left_ear + right_ear) / 2.0

                current_status['ear_value'] = round(avg_ear, 3)

                # Track recent EAR values for smoother detection
                global recent_ear_values, drowsiness_score
                recent_ear_values.append(avg_ear)
                if len(recent_ear_values) > 10:
                    recent_ear_values.pop(0)
                
                # Calculate average EAR over recent frames
                avg_recent_ear = sum(recent_ear_values) / len(recent_ear_values) if recent_ear_values else avg_ear
                
                # Improved drowsiness scoring with better reset logic
                if avg_recent_ear < DROWSY_EAR_THRESHOLD:  # Eyes very droopy (EAR < 0.30)
                    drowsiness_score += 3  # Increase score faster for clearly closed/droopy eyes
                    drowsy_counter += 1
                elif avg_recent_ear < 0.32:  # Eyes slightly droopy
                    drowsiness_score += 1  # Gradual increase for borderline cases
                    drowsy_counter += 1
                elif avg_recent_ear > 0.35:  # Eyes clearly open
                    drowsiness_score = max(0, drowsiness_score - 3)  # Aggressive reset when eyes are open
                    drowsy_counter = 0
                else:  # Normal range (0.32-0.35)
                    drowsiness_score = max(0, drowsiness_score - 1)  # Slow decrease in normal range
                    drowsy_counter = 0

                # Only trigger drowsiness with stricter conditions
                if (drowsiness_score > 20 and avg_recent_ear < 0.32) or drowsy_counter >= DROWSY_CONSEC_FRAMES:
                    status = 'drowsy'
                    confidence = min(1.0, drowsiness_score / 25.0)  # Confidence based on score
                    cv2.rectangle(frame, (20, 120), (250, 160), (0, 0, 255), -1)
                    cv2.putText(frame, "DROWSINESS", (30, 150), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                else:
                    # Reset drowsiness when not detected to prevent accumulation
                    if avg_recent_ear > 0.33:
                        drowsiness_score = max(0, drowsiness_score - 2)
                    
            except Exception as e:
                print(f"Drowsiness detection error: {e}")

            # Nodding detection - UNCHANGED logic
            try:
                if detect_nodding(landmark_coords):
                    status = 'drowsy'  # Nodding is considered drowsiness
                    confidence = 1.0
                    cv2.rectangle(frame, (20, 160), (200, 200), (0, 165, 255), -1)
                    cv2.putText(frame, "NODDING", (30, 190), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                    nodding_counter = 0
            except Exception as e:
                print(f"Nodding detection error: {e}")

            # Yawning detection - UNCHANGED logic
            try:
                mouth_indices = [13, 14, 15, 16, 17, 78, 79, 80, 81, 82]
                mouth_points = [landmark_coords[i] for i in mouth_indices]

                x_min = max(min([p[0] for p in mouth_points]) - 10, 0)
                x_max = min(max([p[0] for p in mouth_points]) + 10, w)
                y_min = max(min([p[1] for p in mouth_points]) - 10, 0)
                y_max = min(max([p[1] for p in mouth_points]) + 10, h)

                mouth_img = frame[y_min:y_max, x_min:x_max]
                cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 0), 1)

                if mouth_img.size != 0:
                    mar = mouth_aspect_ratio(landmark_coords)
                    mar = smoothed_mar(mar)

                    if mar > 0.4:
                        if yawn_model is not None:
                            try:
                                mouth_img_processed = cv2.cvtColor(mouth_img, cv2.COLOR_BGR2RGB)
                                mouth_img_processed = cv2.resize(mouth_img_processed, (24, 24)) / 255.0
                                mouth_img_processed = np.expand_dims(mouth_img_processed, axis=0)
                                yawn_prob = float(yawn_model.predict(mouth_img_processed, verbose=0)[0][0])
                                        
                            except Exception as e:
                                print(f"Model prediction error: {e}")
                                yawn_prob = min(1.0, max(0.0, (mar - 0.5) * 2.0))
                        else:
                            yawn_prob = min(1.0, max(0.0, (mar - 0.5) * 2.0))

                        yawn_probs.append(yawn_prob)
                        if len(yawn_probs) > 10:
                            yawn_probs.pop(0)

                        avg_prob = sum(yawn_probs) / len(yawn_probs)
                        current_status['yawn_prob'] = round(avg_prob, 3)

                        if avg_prob > YAWN_THRESHOLD:
                            yawn_counter += 1
                        else:
                            yawn_counter = 0

                        if yawn_counter >= YAWN_CONSEC_FRAMES:
                            status = 'yawning'
                            confidence = avg_prob
                            cv2.rectangle(frame, (20, 50), (200, 90), (0, 255, 255), -1)
                            cv2.putText(frame, "YAWNING", (30, 80), cv2.FONT_HERSHEY_COMPLEX, 0.8, (0, 0, 0), 2)
                            yawn_counter = 0
                    else:
                        yawn_counter = 0
                else:
                    yawn_counter = 0
            except Exception as e:
                print(f"Yawn detection error: {e}")

        # Absence detection - UNCHANGED logic
        if not face_found or not face_forward:
            if time.time() - last_attentive_time > NOT_ATTENTIVE_THRESHOLD:
                status = 'not_present'
                confidence = 1.0
                cv2.rectangle(frame, (20, 85), (250, 125), (255, 0, 0), -1)
                cv2.putText(frame, "NOT PRESENT", (30, 115), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                
                # Distraction Alert System
                global last_distraction_alert, distraction_alert_count
                current_time = time.time()
                if current_time - last_distraction_alert >= DISTRACTION_ALERT_INTERVAL:
                    distraction_alert_count += 1
                    last_distraction_alert = current_time

        # Update global status with additional debug info
        update_session_stats(status)  # Track statistics
        
        current_status.update({
            'status': status,
            'confidence': confidence,
            'face_found': face_found,
            'face_forward': face_forward,
            'time_since_attentive': round(time.time() - last_attentive_time, 1),
            'drowsiness_score': drowsiness_score,  # Debug info
            'avg_recent_ear': round(avg_recent_ear if 'avg_recent_ear' in locals() else 0, 3),  # Debug info
            'distraction_alert_count': distraction_alert_count,  # Alert count
            'should_show_alert': status == 'not_present' and time.time() - last_distraction_alert < 3,  # Show alert for 3 seconds
            'timestamp': time.time()
        })

        # Encode frame
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    cap.release()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def home():
    return render_template('start.html')

@app.route('/start_session', methods=['POST'])
def start_session():
    global session_stats
    
    # Reset session statistics
    session_stats = {
        'yawn_count': 0,
        'drowsy_count': 0,
        'distraction_count': 0,
        'not_present_count': 0,
        'focused_time': 0,
        'distracted_time': 0,
        'drowsy_time': 0,
        'not_present_time': 0,
        'last_state': 'focused',
        'state_start_time': time.time()
    }
    
    # Get user information
    username = request.form.get('username')
    session_purpose = request.form.get('session_purpose')
    session_duration = request.form.get('session_duration', '30')
    
    if not username:
        flash('Please enter your name to continue.')
        return redirect(url_for('home'))
    
    try:
        session_duration = int(session_duration)
        if session_duration < 1 or session_duration > 300:
            raise ValueError()
    except ValueError:
        flash('Please enter a valid session duration (1-300 minutes).')
        return redirect(url_for('home'))
    
    # Handle file uploads
    uploaded_files = []
    if 'documents' in request.files:
        files = request.files.getlist('documents')
        for file in files:
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Add timestamp to avoid conflicts
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                uploaded_files.append(filename)
    
    # Store session information
    session['username'] = username
    session['session_purpose'] = session_purpose
    session['session_duration'] = session_duration
    session['uploaded_files'] = uploaded_files
    session['session_start_time'] = datetime.now().isoformat()
    
    flash(f'Welcome {username}! Session started successfully.')
    return redirect(url_for('monitor'))

@app.route('/monitor')
def monitor():
    if 'username' not in session:
        flash('Please start a session first.')
        return redirect(url_for('home'))
    
    return render_template('index.html', 
                         username=session.get('username'),
                         session_purpose=session.get('session_purpose'),
                         session_duration=session.get('session_duration', 30),
                         uploaded_files=session.get('uploaded_files', []),
                         session_start_time=session.get('session_start_time'))

@app.route('/end_session')
def end_session():
    global session_stats
    
    if 'username' not in session:
        flash('No active session found.')
        return redirect(url_for('home'))
    
    # Calculate final statistics
    current_time = time.time()
    time_in_state = current_time - session_stats['state_start_time']
    
    # Update time for current state
    if session_stats['last_state'] == 'focused':
        session_stats['focused_time'] += time_in_state
    elif session_stats['last_state'] in ['not_present', 'distracted']:
        session_stats['distracted_time'] += time_in_state
    elif session_stats['last_state'] == 'drowsy':
        session_stats['drowsy_time'] += time_in_state
    elif session_stats['last_state'] == 'yawning':
        session_stats['drowsy_time'] += time_in_state
    
    # Store stats in session before clearing
    session['final_stats'] = session_stats.copy()
    
    # Calculate session duration
    if 'session_start_time' in session:
        start_time = datetime.fromisoformat(session['session_start_time'])
        end_time = datetime.now()
        session['actual_duration'] = (end_time - start_time).total_seconds() / 60  # in minutes
    
    return redirect(url_for('analytics'))

@app.route('/analytics')
def analytics():
    """Display session analytics dashboard"""
    if 'final_stats' not in session:
        flash('No session data available. Please complete a session first.')
        return redirect(url_for('home'))
    
    stats = session.get('final_stats', {})
    username = session.get('username', 'User')
    session_purpose = session.get('session_purpose', 'Study Session')
    actual_duration = session.get('actual_duration', 0)
    
    # Calculate total time
    total_time = stats.get('focused_time', 0) + stats.get('distracted_time', 0) + \
                 stats.get('drowsy_time', 0)
    
    # Prevent division by zero
    if total_time == 0:
        total_time = 1
    
    # Calculate percentages
    focus_percentage = (stats.get('focused_time', 0) / total_time) * 100
    distraction_percentage = (stats.get('distracted_time', 0) / total_time) * 100
    drowsy_percentage = (stats.get('drowsy_time', 0) / total_time) * 100
    
    # Format times to minutes and seconds
    def format_time(seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    
    analytics_data = {
        'username': username,
        'session_purpose': session_purpose,
        'duration_minutes': round(actual_duration, 1),
        'yawn_count': stats.get('yawn_count', 0),
        'drowsy_count': stats.get('drowsy_count', 0),
        'distraction_count': stats.get('distraction_count', 0),
        'focused_time': format_time(stats.get('focused_time', 0)),
        'distracted_time': format_time(stats.get('distracted_time', 0)),
        'drowsy_time': format_time(stats.get('drowsy_time', 0)),
        'focus_percentage': round(focus_percentage, 1),
        'distraction_percentage': round(distraction_percentage, 1),
        'drowsy_percentage': round(drowsy_percentage, 1),
        'total_time': format_time(total_time)
    }
    
    return render_template('analytics.html', **analytics_data)

@app.route('/finish_analytics')
def finish_analytics():
    """Clear session and return to home"""
    session.clear()
    flash('Thank you for using the Attention Monitoring System!')
    return redirect(url_for('home'))

@app.route('/download_analytics_pdf')
def download_analytics_pdf():
    """Generate and download analytics as PDF"""
    if 'final_stats' not in session:
        flash('No session data available.')
        return redirect(url_for('home'))
    
    # Get session data
    stats = session.get('final_stats', {})
    username = session.get('username', 'User')
    session_purpose = session.get('session_purpose', 'Study Session')
    actual_duration = session.get('actual_duration', 0)
    session_start = session.get('session_start_time', datetime.now().isoformat())
    
    # Calculate statistics
    total_time = stats.get('focused_time', 0) + stats.get('distracted_time', 0) + stats.get('drowsy_time', 0)
    if total_time == 0:
        total_time = 1
    
    focus_percentage = (stats.get('focused_time', 0) / total_time) * 100
    distraction_percentage = (stats.get('distracted_time', 0) / total_time) * 100
    drowsy_percentage = (stats.get('drowsy_time', 0) / total_time) * 100
    
    def format_time(seconds):
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    
    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Container for PDF elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#8b5cf6'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#3b82f6'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=8
    )
    
    # Title
    elements.append(Paragraph("📊 Session Analytics Report", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Session Information Table
    session_data = [
        ['Session Information', ''],
        ['Student Name:', username],
        ['Session Purpose:', session_purpose],
        ['Session Date:', datetime.fromisoformat(session_start).strftime('%B %d, %Y at %I:%M %p')],
        ['Total Duration:', f"{actual_duration:.1f} minutes"],
    ]
    
    session_table = Table(session_data, colWidths=[2.5*inch, 4*inch])
    session_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8b5cf6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f3f4f6')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#d1d5db')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    
    elements.append(session_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Focus Score Section
    elements.append(Paragraph("Overall Focus Score", heading_style))
    
    focus_data = [
        ['Focus Percentage', f"{focus_percentage:.1f}%"],
        ['Performance Rating', 
         '🌟 Outstanding!' if focus_percentage >= 80 else
         '👍 Good' if focus_percentage >= 60 else
         '⚡ Moderate' if focus_percentage >= 40 else
         '💪 Needs Improvement']
    ]
    
    focus_table = Table(focus_data, colWidths=[2.5*inch, 4*inch])
    focus_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#dbeafe')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#3b82f6')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))
    
    elements.append(focus_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Statistics Summary
    elements.append(Paragraph("📈 Detailed Statistics", heading_style))
    
    stats_data = [
        ['Metric', 'Count/Time', 'Percentage'],
        ['✅ Focused Time', format_time(stats.get('focused_time', 0)), f"{focus_percentage:.1f}%"],
        ['😴 Drowsy Episodes', str(stats.get('drowsy_count', 0)), f"{drowsy_percentage:.1f}%"],
        ['👀 Distractions', str(stats.get('distraction_count', 0)), f"{distraction_percentage:.1f}%"],
        ['🥱 Yawns Detected', str(stats.get('yawn_count', 0)), 'N/A'],
    ]
    
    stats_table = Table(stats_data, colWidths=[2.2*inch, 2.2*inch, 2.1*inch])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10b981')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#10b981')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
    ]))
    
    elements.append(stats_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Time Distribution
    elements.append(Paragraph("⏱️ Time Distribution", heading_style))
    
    time_data = [
        ['Activity', 'Duration', 'Percentage'],
        ['Focused', format_time(stats.get('focused_time', 0)), f"{focus_percentage:.1f}%"],
        ['Drowsy', format_time(stats.get('drowsy_time', 0)), f"{drowsy_percentage:.1f}%"],
        ['Distracted', format_time(stats.get('distracted_time', 0)), f"{distraction_percentage:.1f}%"],
        ['Total Session', format_time(total_time), '100%'],
    ]
    
    time_table = Table(time_data, colWidths=[2.2*inch, 2.2*inch, 2.1*inch])
    time_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#6366f1')),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#eef2ff')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0e7ff')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    
    elements.append(time_table)
    elements.append(Spacer(1, 0.4*inch))
    
    # Recommendations
    elements.append(Paragraph("💡 Recommendations", heading_style))
    
    recommendations = []
    if focus_percentage < 60:
        recommendations.append("• Consider taking regular short breaks to maintain focus")
        recommendations.append("• Try the Pomodoro Technique: 25 minutes focused work, 5 minutes break")
    if stats.get('drowsy_count', 0) > 5:
        recommendations.append("• Ensure you're getting adequate sleep (7-9 hours)")
        recommendations.append("• Take a short walk or do light exercise during breaks")
    if stats.get('distraction_count', 0) > 10:
        recommendations.append("• Minimize distractions by turning off notifications")
        recommendations.append("• Create a dedicated study space")
    if focus_percentage >= 80:
        recommendations.append("• Excellent focus! Keep up the great work!")
        recommendations.append("• Consider sharing your study techniques with others")
    
    if not recommendations:
        recommendations.append("• Maintain your current study habits")
        recommendations.append("• Continue monitoring your attention patterns")
    
    for rec in recommendations:
        elements.append(Paragraph(rec, normal_style))
    
    elements.append(Spacer(1, 0.3*inch))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", footer_style))
    elements.append(Paragraph("Attention Monitoring System - Focus on Excellence", footer_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF data
    pdf_data = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = app.response_class(
        pdf_data,
        mimetype='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename=Session_Analytics_{username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        }
    )
    
    return response

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/music/<filename>')
def serve_music(filename):
    """Serve music files from the server directory"""
    return send_from_directory('server', filename)

@app.route('/view_files')
def view_files():
    if 'username' not in session:
        flash('Please start a session first.')
        return redirect(url_for('home'))
    
    uploaded_files = session.get('uploaded_files', [])
    return render_template('view_files.html', 
                         username=session.get('username'),
                         uploaded_files=uploaded_files)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status')
def get_status():
    # Convert NumPy types to native Python types for JSON serialization
    safe_status = {}
    for key, value in current_status.items():
        if hasattr(value, 'item'):  # NumPy scalar
            safe_status[key] = value.item()
        elif isinstance(value, (np.floating, np.integer)):
            safe_status[key] = value.item()
        else:
            safe_status[key] = value
    return jsonify(safe_status)

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chatbot requests with two modes: Ask Anything or Ask from Document"""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        chat_mode = data.get('mode', 'ask_anything')  # 'ask_anything' or 'ask_document'
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': 'Message cannot be empty'
            }), 400
        
        # Mode 1: Ask Anything (General Gemini AI)
        if chat_mode == 'ask_anything':
            try:
                # Add formatting instructions to prompt
                formatted_prompt = f"""{user_message}

Please format your response clearly with:
- Use **bold** for important terms
- Use bullet points (-) or numbered lists (1., 2.) for multiple items
- Use clear paragraphs for better readability
- Keep responses concise but informative"""
                
                response = gemini_model.generate_content(formatted_prompt)
                ai_response = response.text
                
                return jsonify({
                    'success': True,
                    'response': ai_response,
                    'mode': 'ask_anything'
                })
            except Exception as e:
                print(f"Gemini API error: {e}")
                return jsonify({
                    'success': False,
                    'error': f'AI service error: {str(e)}'
                }), 500
        
        # Mode 2: Ask from Document (Context-based)
        elif chat_mode == 'ask_document':
            # Get uploaded documents content
            documents_content = get_all_documents_content()
            
            if not documents_content:
                return jsonify({
                    'success': False,
                    'error': 'No documents uploaded. Please upload documents first or switch to "Ask Anything" mode.'
                }), 400
            
            # Create context-aware prompt
            context_prompt = f"""You are an AI assistant helping a student understand their study materials.

Below is the content from the uploaded documents:

{documents_content}

Based ONLY on the above document content, please answer the following question:

Question: {user_message}

Instructions:
- Answer based on the document content provided above
- If the answer is not in the documents, say "I cannot find this information in the uploaded documents."
- Be clear, concise, and helpful
- If relevant, quote specific parts from the documents
- Format your response clearly with:
  * Use **bold** for important terms
  * Use bullet points (-) or numbered lists (1., 2.) for multiple items
  * Use clear paragraphs for better readability
"""
            
            try:
                response = gemini_model.generate_content(context_prompt)
                ai_response = response.text
                
                return jsonify({
                    'success': True,
                    'response': ai_response,
                    'mode': 'ask_document',
                    'documents_used': len(session.get('uploaded_files', []))
                })
            except Exception as e:
                print(f"Gemini API error: {e}")
                return jsonify({
                    'success': False,
                    'error': f'AI service error: {str(e)}'
                }), 500
        
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid chat mode. Use "ask_anything" or "ask_document".'
            }), 400
    
    except Exception as e:
        print(f"Chat endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@app.route('/get_video_recommendations', methods=['POST'])
def get_video_recommendations():
    """Fetch YouTube video recommendations based on user's topic"""
    try:
        data = request.get_json()
        topic = data.get('topic', '').strip()
        
        if not topic:
            return jsonify({
                'success': False,
                'error': 'Please provide a topic'
            }), 400
        
        # YouTube Data API v3 - Search endpoint
        youtube_api_url = "https://www.googleapis.com/youtube/v3/search"
        
        params = {
            'part': 'snippet',
            'q': topic,
            'key': YOUTUBE_API_KEY,
            'type': 'video',
            'maxResults': 12,  # Get 12 videos
            'order': 'relevance',  # Most relevant videos first
            'videoDefinition': 'high',  # Prefer HD videos
            'videoEmbeddable': 'true',  # Only embeddable videos
            'safeSearch': 'strict'  # Family-friendly content
        }
        
        response = requests.get(youtube_api_url, params=params, timeout=10)
        
        if response.status_code != 200:
            error_data = response.json()
            error_message = error_data.get('error', {}).get('message', 'Unknown error')
            print(f"YouTube API error: {error_message}")
            return jsonify({
                'success': False,
                'error': f'YouTube API error: {error_message}'
            }), response.status_code
        
        data = response.json()
        videos = []
        
        # Parse video results
        for item in data.get('items', []):
            video_id = item['id'].get('videoId')
            if not video_id:
                continue
                
            snippet = item['snippet']
            video_info = {
                'id': video_id,
                'title': snippet.get('title', 'No title'),
                'description': snippet.get('description', 'No description'),
                'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url', ''),
                'channel': snippet.get('channelTitle', 'Unknown channel'),
                'publishedAt': snippet.get('publishedAt', ''),
                'url': f'https://www.youtube.com/watch?v={video_id}',
                'embedUrl': f'https://www.youtube.com/embed/{video_id}'
            }
            videos.append(video_info)
        
        if not videos:
            return jsonify({
                'success': False,
                'error': 'No videos found for this topic. Try a different search term.'
            }), 404
        
        return jsonify({
            'success': True,
            'videos': videos,
            'topic': topic,
            'count': len(videos)
        })
        
    except requests.exceptions.Timeout:
        return jsonify({
            'success': False,
            'error': 'Request timed out. Please try again.'
        }), 504
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to connect to YouTube API'
        }), 503
    except Exception as e:
        print(f"Video recommendations error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

if __name__ == '__main__':
    # Print all registered routes for debugging
    print("\n=== Registered Routes ===")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
    print("========================\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)