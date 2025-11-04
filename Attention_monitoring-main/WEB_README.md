# Attention Monitoring Web Application

This web application provides a real-time attention monitoring system with a clean, professional interface. The webcam feed is displayed in the top corner, and the analysis results are shown prominently below.

## Features

- **Real-time webcam feed** displayed in the top corner
- **Live status updates** showing:
  - 😊 **FOCUSED** - User is attentive and alert
  - 🥱 **YAWNING DETECTED** - Yawning behavior detected
  - 😴 **DROWSINESS DETECTED** - Eyes closing or head nodding
  - ❌ **NOT PRESENT** - No face detected or user not looking at camera
- **Detailed metrics panel** with:
  - Face detection status
  - Eye Aspect Ratio (EAR) values
  - Yawn probability scores
  - Confidence levels
- **Responsive design** that works on desktop and mobile
- **Real-time updates** every 500ms for smooth monitoring

## Installation

1. Install the required packages:

```bash
pip install -r requirements.txt
```

## Running the Application

1. Make sure your webcam is connected and working
2. Run the Flask application:

```bash
python app.py
```

3. Open your web browser and navigate to:

```
http://localhost:5000
```

The application will start and you should see:

- Your live webcam feed in the top-left corner
- Real-time attention monitoring status on the right side
- Detailed metrics showing detection values

## How It Works

The application uses the same detection logic as the original attention monitoring system:

- **Face Detection**: Uses MediaPipe to detect face landmarks
- **Yawn Detection**: Analyzes mouth aspect ratio and uses a pre-trained model
- **Drowsiness Detection**: Monitors eye aspect ratio and head nodding
- **Attention Tracking**: Detects when user is not present or looking away

All detection thresholds and algorithms remain **exactly the same** as the original system - only the interface has been changed to a web-based format.

## Status Indicators

- **Green (FOCUSED)**: User is alert and attentive
- **Orange (YAWNING)**: Yawning detected with pulsing animation
- **Red (DROWSY)**: Drowsiness or nodding detected with pulsing animation
- **Gray (NOT PRESENT)**: User not detected or not facing camera

## Metrics Explained

- **Face Detection**: Shows if a face is currently detected
- **Eye Aspect Ratio**: Current EAR value (lower values indicate closed eyes)
- **Yawn Probability**: ML model confidence for yawn detection
- **Confidence Level**: Overall confidence in the current status

## Troubleshooting

- **Webcam not working**: Check if another application is using the camera
- **Poor detection**: Ensure good lighting and face the camera directly
- **Slow performance**: Close other applications that might use the camera

The web interface provides the same reliable attention monitoring as the original system with an improved, user-friendly display.
