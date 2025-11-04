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

# Constants
YAWN_THRESHOLD = 0.70  
YAWN_CONSEC_FRAMES = 17
ALERT_COOLDOWN = 5
NOT_ATTENTIVE_THRESHOLD = 6
DROWSY_EAR_THRESHOLD = 0.23
DROWSY_CONSEC_FRAMES = 30

# Landmark indices
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# State variables
yawn_counter = 0
last_alert_time = 0
last_attentive_time = time.time()
yawn_probs = []
drowsy_counter = 0
not_present_alerted = False

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

# Eye Aspect Ratio
def eye_aspect_ratio(eye_points):
    A = np.linalg.norm(np.array(eye_points[1]) - np.array(eye_points[5]))
    B = np.linalg.norm(np.array(eye_points[2]) - np.array(eye_points[4]))
    C = np.linalg.norm(np.array(eye_points[0]) - np.array(eye_points[3]))
    if C == 0:
        return 0
    return (A + B) / (2.0 * C)

# Camera 
cap = cv2.VideoCapture(0)

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

        # Drowsiness detection
        try:
            left_eye_pts = [landmark_coords[i] for i in LEFT_EYE]
            right_eye_pts = [landmark_coords[i] for i in RIGHT_EYE]
            left_ear = eye_aspect_ratio(left_eye_pts)
            right_ear = eye_aspect_ratio(right_eye_pts)
            avg_ear = (left_ear + right_ear) / 2.0

            if avg_ear < DROWSY_EAR_THRESHOLD:
                drowsy_counter += 1
            else:
                drowsy_counter = 0

            if drowsy_counter >= DROWSY_CONSEC_FRAMES:
                text = "DROWSINESS"
                cv2.rectangle(frame, (20, 120), (250, 160), (0, 0, 0), -1)
                cv2.putText(frame, text, (30, 150), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                Thread(target=alert_drowsy).start()
        except Exception as e:
            print("Drowsiness detection error:", str(e))

        # Yawning detection with MAR smoothing
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

                    yawn_prob = yawn_model.predict(mouth_img)[0][0]
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
                        cv2.rectangle(frame, (20, 50), (200, 90), (0, 0, 0), -1)
                        cv2.putText(frame, text, (30, 80), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
                        Thread(target=alert_yawn).start()
                else:
                    yawn_counter = 0
        except Exception as e:
            print("Yawn detection error:", str(e))

    #Absence detection
    if not face_found or not face_forward:
        if time.time() - last_attentive_time > NOT_ATTENTIVE_THRESHOLD:
            text = "NOT PRESENT"
            cv2.rectangle(frame, (20, 85), (250, 125), (0, 0, 0), -1)
            cv2.putText(frame, text, (30, 115), cv2.FONT_HERSHEY_COMPLEX, 0.8, (255, 255, 255), 2)
            if not not_present_alerted:
                Thread(target=alert_absence).start()
                not_present_alerted = True

    #Monitoring
    cv2.imshow("Attentiveness Monitoring", frame)

    if cv2.waitKey(1) & 0xFF == 27:  
        break

cap.release()
cv2.destroyAllWindows()
