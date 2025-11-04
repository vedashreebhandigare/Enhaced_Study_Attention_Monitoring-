## Attention_monitoring_system
This project is a real-time attentiveness monitoring system that detects signs of inattention using a webcam. Built using Python, OpenCV, MediaPipe, and TensorFlow, it detects:

- **Yawning** using a trained CNN model
- **Drowsiness** using Eye Aspect Ratio (EAR)
- **Face absence** or distraction
- **Head nodding** using chin movement

Alerts are visual (on screen) and auditory (beep).

---

## Features
- Real-time webcam-based detection
- CNN-powered yawning detection (pre-trained `.h5` model)
- Drowsiness detection with EAR
- Face absence or head-turn detection
- Sound alerts for all conditions
- Live feedback overlay on webcam feed

---

##Project Structure
```
├── yawn_dataset               # Dataset with images yawn and not_yawn
├── yawn_model.h5              # Trained CNN model for yawning detection
├── attention_monitoring.py    # Main Python script
└── README.md                  # Project documentation
```

---

## Requirements
- Python 3.7+
- OpenCV (`cv2`)
- MediaPipe
- NumPy
- TensorFlow / Keras
- Windows OS (for `winsound` alerts)

###Install dependencies:
```bash
pip install opencv-python mediapipe numpy tensorflow
```

---

## How the System Works

### 1. Yawning Detection (CNN)
- Mouth landmarks are extracted using MediaPipe.
- If **MAR (Mouth Aspect Ratio)** > 0.4, the cropped mouth image is passed to the CNN.
- If average yawning probability > 0.7 for 17 consecutive frames, it raises a **YAWNING ALERT**.

### 2. Drowsiness Detection (EAR)
- EAR is calculated from eye landmarks.
- If EAR < 0.23 for 30 consecutive frames → **DROWSINESS ALERT**.

### 3. Absence or Distraction
- Checks if the nose is aligned with eye midpoints.
- If not aligned or face is not detected for 6 seconds → **NOT PRESENT ALERT**.


### 4. Alerts
- Alerts are shown on screen with bounding boxes and labels.
- Beeps via `winsound.Beep()`.

---

## Running the Project
```bash
python attention_monitoring.py
```
> Ensure that `yawn_model.h5` is present in the same directory.

Press `ESC` to exit.

---

## Output Example
- **On-screen alerts:** "YAWNING", "DROWSINESS", "NOT PRESENT", "NODDING"
- **Bottom-left:** live yawning probability
- **Beep sound** triggered for each detected alert

---

## CNN Model for Yawning Detection
- Input: 64x64 RGB mouth image
- Architecture:
```text
Conv2D → MaxPooling → Conv2D → MaxPooling → Flatten → Dense → Output (Sigmoid)
```
- Output: Probability of yawning (0 to 1)

---

##  Notes
- The model performs best in well-lit environments.
- Works for one user at a time.
- Designed for student monitoring in online class,online meetings, can be extended to drivers, employees, etc.

---

##  Future Improvements
- Add head pose estimation for robust attention detection
- Replace `winsound` with cross-platform audio module
- Save logs of inattention for analytics
- Add GUI interface

---

## Author
Developed as a internship project to monitor attention levels using deep learning and computer vision.


