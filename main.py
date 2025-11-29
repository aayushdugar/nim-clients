import os
import pyaudio
import numpy as np
import threading
import winsound
import subprocess
import cv2
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import simpleaudio as sa  # Added for playing filtered audio

# 🎛 **Audio Configuration**
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 16000
CHUNK = 1024

# 🔹 NVIDIA Riva API details
NVIDIA_API_KEY = "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"
FUNCTION_ID = "7cf12edb-2181-4947-8b19-2b1c18270588"
RIVA_SERVER = "grpc.nvcf.nvidia.com:443"

running = True

def play_startup_sound():
    """Play the startup sound using winsound."""
    try:
        winsound.PlaySound("AAP.wav", winsound.SND_FILENAME)
    except Exception as e:
        print(f"⚠️ Error playing startup sound: {e}")

def play_bootup_video(video_path):
    """Play boot-up video before GUI starts."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("⚠️ Error: Could not open video file!")
        start_gui()
        return
    
    video_window = tk.Toplevel(root)
    video_label = tk.Label(video_window)
    video_label.pack(fill="both", expand=True)

    def update_frame():
        ret, frame = cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = Image.fromarray(frame)
            frame = ImageTk.PhotoImage(frame)
            video_label.config(image=frame)
            video_label.image = frame
            video_window.after(33, update_frame)  # 30 FPS
        else:
            cap.release()
            video_window.destroy()  # Close video window
            start_gui()  # Start GUI

    update_frame()

def start_gui():
    """Start the main GUI after boot-up video."""
    root.deiconify()

def capture_audio():
    """Capture microphone input and process it through Riva."""
    global running
    running = True
    p = pyaudio.PyAudio()

    stream = p.open(format=FORMAT, channels=CHANNELS,
                    rate=RATE, input=True, frames_per_buffer=CHUNK)

    status_label.config(text="🟢 Status: Running", fg="lime")

    while running:
        audio_data = stream.read(CHUNK)
        filtered_audio = process_audio(audio_data)  # Process audio with Riva
        play_audio(filtered_audio)  # Play the processed audio in real-time

    stream.stop_stream()
    stream.close()
    p.terminate()
    status_label.config(text="🟡 Status: Idle", fg="yellow")

def process_audio(audio_data):
    """Process audio using NVIDIA Riva and return filtered sound."""
    return audio_data  # (Placeholder: Replace with actual Riva API call)

def play_audio(audio_data):
    """Play filtered audio in real-time."""
    wave_obj = sa.WaveObject(audio_data, num_channels=CHANNELS, bytes_per_sample=2, sample_rate=RATE)
    wave_obj.play()

def start_voice_filtering():
    """Start audio filtering thread."""
    if running:
        return
    threading.Thread(target=capture_audio, daemon=True).start()

def stop_voice_filtering():
    """Stop voice isolation process."""
    global running
    running = False
    status_label.config(text="🟡 Status: Idle", fg="yellow")

# 🎨 GUI Setup
root = tk.Tk()
root.title("🎧 Voice Isolation GUI")
root.configure(bg="black")

# Hide main window initially
root.withdraw()

# 📷 Load background image
bg_image = Image.open('back.png')
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
bg_image = bg_image.resize((screen_width, screen_height), Image.LANCZOS)
bg_photo = ImageTk.PhotoImage(bg_image)
background_label = tk.Label(root, image=bg_photo)
background_label.place(relwidth=1, relheight=1)

# 🏷️ Logo
logo = Image.open("aap.png")
logo = logo.resize((300, 300), Image.LANCZOS)
logo_photo = ImageTk.PhotoImage(logo)
logo_label = tk.Label(root, image=logo_photo, bg="black")
logo_label.pack(pady=40)

status_label = tk.Label(root, text="🟡 Status: Idle", font=("Arial", 16), fg="yellow", bg="black")
status_label.pack(pady=10)

button_frame = tk.Frame(root, bg="black")
button_frame.pack()

start_button = tk.Button(button_frame, text="▶️ Start", command=start_voice_filtering, bg="green", fg="white", font=("Arial", 14), height=2, width=15)
start_button.grid(row=0, column=0, padx=10, pady=10)

stop_button = tk.Button(button_frame, text="⏹️ Stop", command=stop_voice_filtering, bg="red", fg="white", font=("Arial", 14), height=2, width=15)
stop_button.grid(row=0, column=1, padx=10, pady=10)

exit_button = tk.Button(button_frame, text="❌ Exit", command=root.quit, bg="yellow", fg="black", font=("Arial", 14), height=2, width=15)
exit_button.grid(row=1, column=0, columnspan=2, pady=10)

# © Copyright Notice
copyright_label = tk.Label(root, text="© 2025 AUDITORY AID PROJECT / PROJECT TRINITRON.", font=("Arial", 10), fg="white", bg="black")
copyright_label.pack(side="bottom", pady=5)

# Play boot-up video, then show main GUI
play_bootup_video("bootup.mp4")

root.mainloop()