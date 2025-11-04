import cv2
import numpy as np
import mediapipe as mp
from tensorflow.keras.models import load_model
import time
from threading import Thread
import winsound 

#model
yawn_model = load_model("yawn_model.h5")

#MediaPipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5)

# Constants - IMPROVED THRESHOLDS
YAWN_THRESHOLD = 0.70  
YAWN_CONSEC_FRAMES = 17
ALERT_COOLDOWN = 5
NOT_ATTENTIVE_THRESHOLD = 6
DROWSY_EAR_THRESHOLD = 0.25  # Increased threshold (was 0.23)
DROWSY_CONSEC_FRAMES = 20     # Reduced frames (was 30)
NODDING_THRESHOLD = 25        # NEW: Increased threshold for less sensitivity (was 15)

# Landmark indices - IMPROVED EYE LANDMARKS
LEFT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385]
RIGHT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]

# NEW: Landmark indices for nodding detection
CHIN_POINT = 175
NOSE_TIP = 1
FOREHEAD_POINT = 10

# State variables
yawn_counter = 0
last_alert_time = 0
last_attentive_time = time.time()
yawn_probs = []
drowsy_counter = 0
not_present_alerted = False

# NEW: Nodding detection variables
chin_positions = []
nodding_counter = 0
previous_chin_y = None

# Sound alert function
def sound_alert():
    frequency = 900  # Hz
    duration = 100    # milliseconds
    winsound.Beep(frequency, duration)

# Alert functions
def alert_yawn():
    global last_alert_time
    if time.time() - last_alert_time > ALERT_COOLDOWN:
        print("ALERT: Yawning Detected")
        sound_alert()
        last_alert_time = time.time()

def alert_drowsy():
    global last_alert_time
    if time.time() - last_alert_time > ALERT_COOLDOWN:
        print("ALERT: Drowsiness Detected")
        sound_alert()
        last_alert_time = time.time()

def alert_absence():
    global last_alert_time
    if time.time() - last_alert_time > ALERT_COOLDOWN:
        print("ALERT: User Not Present")
        sound_alert()
        last_alert_time = time.time()

# NEW: Nodding alert function
def alert_nodding():
    global last_alert_time
    if time.time() - last_alert_time > ALERT_COOLDOWN:
        print("ALERT: Nodding Detected")
        sound_alert()
        last_alert_time = time.time()

# Mouth Aspect Ratio
def mouth_aspect_ratio(landmark_coords):
    A = np.linalg.norm(np.array(landmark_coords[13]) - np.array(landmark_coords[14]))
    B = np.linalg.norm(np.array(landmark_coords[78]) - np.array(landmark_coords[82]))
    if B == 0:
        return 0
    return A / B

# MAR smoothing
mar_list = []

def smoothed_mar(current_mar, window=5):
    global mar_list
    mar_list.append(current_mar)
    if len(mar_list) > window:
        mar_list.pop(0)
    return sum(mar_list) / len(mar_list)

# IMPROVED: Eye Aspect Ratio with better calculation
def eye_aspect_ratio(eye_points):
    if len(eye_points) < 6:
        return 0
    
    # Vertical eye landmarks
    A = np.linalg.norm(np.array(eye_points[1]) - np.array(eye_points[5]))
    B = np.linalg.norm(np.array(eye_points[2]) - np.array(eye_points[4]))
    
    # Horizontal eye landmark
    C = np.linalg.norm(np.array(eye_points[0]) - np.array(eye_points[3]))
    
    if C == 0:
        return 0
    return (A + B) / (2.0 * C)

# NEW: Nodding detection function
def detect_nodding(landmark_coords):
    global chin_positions, nodding_counter, previous_chin_y
    
    try:
        chin_y = landmark_coords[CHIN_POINT][1]
        
        # Track chin movement over time
        chin_positions.append(chin_y)
        if len(chin_positions) > 10:  # Keep last 10 positions
            chin_positions.pop(0)
        
        if len(chin_positions) >= 5:
            # Calculate vertical movement
            recent_positions = chin_positions[-5:]
            movement_range = max(recent_positions) - min(recent_positions)
            
            # Detect rhythmic up-down movement
            if movement_range > NODDING_THRESHOLD:
                nodding_counter += 1
            else:
                nodding_counter = max(0, nodding_counter - 1)
            
            return nodding_counter > 8  # Trigger after more sustained nodding (was 3)
        
    except Exception as e:
        print(f"Nodding detection error: {e}")
    
    return False

# Camera 
cap = cv2.VideoCapture(0)

print("Starting Attention Monitoring System...")
print("IMPROVEMENTS:")
print("- Increased drowsiness threshold to 0.25 (was 0.23)")
print("- Reduced drowsy frames requirement to 20 (was 30)")
print("- Added head nodding detection")
print("- Improved eye landmark detection")
print("- Added debug information")
print("Press ESC to exit")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Could not access webcam.")
        break

    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    face_found = False
    face_forward = True

    if results.multi_face_landmarks:
        face_found = True
        face_landmarks = results.multi_face_landmarks[0]
        landmark_coords = [(int(p.x * w), int(p.y * h)) for p in face_landmarks.landmark]

        # Face orientation
        nose_x = landmark_coords[1][0]
        left_eye_x = landmark_coords[33][0]
        right_eye_x = landmark_coords[263][0]
        face_center_x = (left_eye_x + right_eye_x) // 2
        deviation = abs(nose_x - face_center_x)

        if deviation > 40:
            face_forward = False

        if face_forward:
            last_attentive_time = time.time()
            not_present_alerted = False

        # IMPROVED: Drowsiness detection with better error handling and debug info
        try:
            # Get eye landmarks
            left_eye_pts = [landmark_coords[i] for i in LEFT_EYE[:6]]  # Take first 6 points
            right_eye_pts = [landmark_coords[i] for i in RIGHT_EYE[:6]]  # Take first 6 points
            
            left_ear = eye_aspect_ratio(left_eye_pts)
            right_ear = eye_aspect_ratio(right_eye_pts)
            avg_ear = (left_ear + right_ear) / 2.0

            # Debug: Display EAR value
            cv2.putText(frame, f"EAR: {round(avg_ear, 3)}", (10, h - 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            if avg_ear < DROWSY_EAR_THRESHOLD:
                drowsy_counter += 1
            else:
                drowsy_counter = 0

            # Debug: Display drowsy counter
            cv2.putText(frame, f"Drowsy Count: {drowsy_counter}/{DROWSY_CONSEC_FRAMES}", (10, h - 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

            if drowsy_counter >= DROWSY_CONSEC_FRAMES:
                text = "DROWSINESS"
                cv2.rectangle(frame, (20, 120), (250, 160), (0, 0, 255), -1)
                cv2.putText(frame, text, (30, 150), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                Thread(target=alert_drowsy).start()
                drowsy_counter = 0  # Reset counter after alert
        except Exception as e:
            print(f"Drowsiness detection error: {e}")

        # NEW: Head nodding detection
        try:
            if detect_nodding(landmark_coords):
                text = "NODDING"
                cv2.rectangle(frame, (20, 160), (200, 200), (0, 165, 255), -1)
                cv2.putText(frame, text, (30, 190), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                Thread(target=alert_nodding).start()
                nodding_counter = 0  # Reset counter after alert
        except Exception as e:
            print(f"Nodding detection error: {e}")

        # Yawning detection with MAR smoothing (UNCHANGED)
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
                    mouth_img = cv2.cvtColor(mouth_img, cv2.COLOR_BGR2RGB)
                    mouth_img = cv2.resize(mouth_img, (64, 64)) / 255.0
                    mouth_img = np.expand_dims(mouth_img, axis=0)

                    yawn_prob = yawn_model.predict(mouth_img, verbose=0)[0][0]
                    yawn_probs.append(yawn_prob)
                    if len(yawn_probs) > 10:
                        yawn_probs.pop(0)

                    avg_prob = sum(yawn_probs) / len(yawn_probs)
                    cv2.putText(frame, f"Yawn Prob: {round(avg_prob, 2)}", (10, h - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

                    if avg_prob > YAWN_THRESHOLD:
                        yawn_counter += 1
                    else:
                        yawn_counter = 0

                    if yawn_counter >= YAWN_CONSEC_FRAMES:
                        text = "YAWNING"
                        cv2.rectangle(frame, (20, 50), (200, 90), (0, 255, 255), -1)
                        cv2.putText(frame, text, (30, 80), cv2.FONT_HERSHEY_COMPLEX, 0.8, (0, 0, 0), 2)
                        Thread(target=alert_yawn).start()
                        yawn_counter = 0  # Reset counter after alert
                else:
                    yawn_counter = 0
        except Exception as e:
            print(f"Yawn detection error: {e}")

    # Absence detection (UNCHANGED)
    if not face_found or not face_forward:
        if time.time() - last_attentive_time > NOT_ATTENTIVE_THRESHOLD:
            text = "NOT PRESENT"
            cv2.rectangle(frame, (20, 85), (250, 125), (255, 0, 0), -1)
            cv2.putText(frame, text, (30, 115), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
            if not not_present_alerted:
                Thread(target=alert_absence).start()
                not_present_alerted = True

    # Display status info
    cv2.putText(frame, f"Face Found: {face_found}", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    # Monitoring
    cv2.imshow("IMPROVED Attentiveness Monitoring", frame)

    if cv2.waitKey(1) & 0xFF == 27:  # ESC key
        break

cap.release()
cv2.destroyAllWindows()
print("Attention monitoring stopped.")