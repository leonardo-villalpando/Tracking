#!/usr/bin/env python3
"""
Multi-User Patient Tracking System
Supports up to 35 concurrent users with shared login
Saves data persistently and allows CSV upload/update
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
import pandas as pd
import json
import os
import csv
from datetime import datetime
import hashlib
import secrets
from werkzeug.utils import secure_filename
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize SocketIO for real-time updates
socketio = SocketIO(app, cors_allowed_origins="*")

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global configuration
SHARED_USERNAME = "patienttracker"
SHARED_PASSWORD = "tracker2025"  # Change this to your desired password
DATA_FILE = "patient_data.json"
BACKUP_DIR = "backups"
MAX_CONCURRENT_USERS = 35

# Ensure backup directory exists
os.makedirs(BACKUP_DIR, exist_ok=True)

# Active users tracking
active_users = {}
user_sessions = {}

def load_patient_data():
    """Load patient data from JSON file"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        print(f"Error loading data: {e}")
        return []

def save_patient_data(data):
    """Save patient data to JSON file with backup"""
    try:
        # Create backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(BACKUP_DIR, f"patient_data_backup_{timestamp}.json")
        
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                backup_data = f.read()
            with open(backup_file, 'w', encoding='utf-8') as f:
                f.write(backup_data)
        
        # Save current data
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Emit update to all connected clients
        socketio.emit('data_updated', {'patients': data}, room='tracker_room')
        
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def csv_to_patients(csv_file_path):
    """Convert CSV file to patient data format"""
    try:
        df = pd.read_csv(csv_file_path)
        patients = []
        
        for _, row in df.iterrows():
            patient = {
                "Patient_Name": str(row.get('Patient Name', '')),
                "DOB": str(row.get('DOB', '')),
                "Sex": str(row.get('Sex', '')),
                "Age": str(row.get('Age', '')),
                "Tel_No": str(row.get('Tel No.', '')),
                "Acc_No": str(row.get('Acc #', '')),
                "Called": bool(row.get('Called', False)),
                "Call_Date": str(row.get('Call_Date', '')),
                "Call_Time": str(row.get('Call_Time', '')),
                "Contact_Status": str(row.get('Contact_Status', '')),
                "Appointment_Scheduled": bool(row.get('Appointment_Scheduled', False)),
                "Appointment_Date": str(row.get('Appointment_Date', '')),
                "Appointment_Time": str(row.get('Appointment_Time', '')),
                "Declined_Reason": str(row.get('Declined_Reason', '')),
                "Notes": str(row.get('Notes', '')),
                "Staff_Member": str(row.get('Staff_Member', '')),
                "Follow_Up_Needed": bool(row.get('Follow_Up_Needed', False)),
                "Follow_Up_Date": str(row.get('Follow_Up_Date', ''))
            }
            patients.append(patient)
        
        return patients
    except Exception as e:
        print(f"Error converting CSV: {e}")
        return None

@app.route('/')
def index():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == SHARED_USERNAME and password == SHARED_PASSWORD:
            if len(active_users) >= MAX_CONCURRENT_USERS:
                flash(f'Maximum number of users ({MAX_CONCURRENT_USERS}) already logged in. Please try again later.')
                return render_template('login.html')
            
            session_id = secrets.token_hex(16)
            session['logged_in'] = True
            session['session_id'] = session_id
            session['login_time'] = datetime.now().isoformat()
            
            # Add to active users
            active_users[session_id] = {
                'login_time': datetime.now(),
                'last_activity': datetime.now()
            }
            
            flash('Login successful!')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session_id = session.get('session_id')
    if session_id and session_id in active_users:
        del active_users[session_id]
    
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/api/patients')
def get_patients():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    # Update last activity
    session_id = session.get('session_id')
    if session_id in active_users:
        active_users[session_id]['last_activity'] = datetime.now()
    
    patients = load_patient_data()
    return jsonify(patients)

@app.route('/api/patients', methods=['POST'])
def update_patients():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.json
        if save_patient_data(data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_csv', methods=['POST'])
def upload_csv():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file and file.filename.lower().endswith('.csv'):
        try:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Convert CSV to patient data
            patients = csv_to_patients(filepath)
            if patients is not None:
                if save_patient_data(patients):
                    return jsonify({'success': True, 'message': f'Successfully uploaded {len(patients)} patients'})
                else:
                    return jsonify({'error': 'Failed to save patient data'}), 500
            else:
                return jsonify({'error': 'Failed to process CSV file'}), 500
                
        except Exception as e:
            return jsonify({'error': f'Error processing file: {str(e)}'}), 500
    
    return jsonify({'error': 'Invalid file type. Please upload a CSV file.'}), 400

@app.route('/api/export_csv')
def export_csv():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        patients = load_patient_data()
        if not patients:
            return jsonify({'error': 'No data to export'}), 400
        
        # Convert to DataFrame and then CSV
        df = pd.DataFrame(patients)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"patient_export_{timestamp}.csv"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        df.to_csv(filepath, index=False)
        
        return jsonify({
            'success': True, 
            'filename': filename,
            'download_url': f'/download/{filename}'
        })
        
    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/api/stats')
def get_stats():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    patients = load_patient_data()
    
    total_patients = len(patients)
    called_patients = len([p for p in patients if p.get('Called', False)])
    scheduled_appointments = len([p for p in patients if p.get('Appointment_Scheduled', False)])
    follow_ups_needed = len([p for p in patients if p.get('Follow_Up_Needed', False)])
    no_answer = len([p for p in patients if p.get('Contact_Status') == 'No Answer'])
    
    success_rate = (scheduled_appointments / total_patients * 100) if total_patients > 0 else 0
    
    return jsonify({
        'total_patients': total_patients,
        'called_patients': called_patients,
        'scheduled_appointments': scheduled_appointments,
        'success_rate': round(success_rate, 1),
        'follow_ups_needed': follow_ups_needed,
        'no_answer': no_answer,
        'active_users': len(active_users)
    })

# SocketIO events
@socketio.on('connect')
def on_connect():
    if 'logged_in' in session:
        join_room('tracker_room')
        emit('user_count', {'count': len(active_users)}, room='tracker_room')

@socketio.on('disconnect')
def on_disconnect():
    if 'logged_in' in session:
        leave_room('tracker_room')

# Background task to clean up inactive sessions
def cleanup_inactive_sessions():
    while True:
        try:
            current_time = datetime.now()
            inactive_sessions = []
            
            for session_id, user_data in active_users.items():
                # Remove sessions inactive for more than 8 hours
                if (current_time - user_data['last_activity']).total_seconds() > 28800:
                    inactive_sessions.append(session_id)
            
            for session_id in inactive_sessions:
                del active_users[session_id]
            
            if inactive_sessions:
                socketio.emit('user_count', {'count': len(active_users)}, room='tracker_room')
            
        except Exception as e:
            print(f"Error in cleanup task: {e}")
        
        time.sleep(300)  # Check every 5 minutes

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_inactive_sessions, daemon=True)
cleanup_thread.start()

if __name__ == '__main__':
    # Initialize with sample data if no data exists
    if not os.path.exists(DATA_FILE):
        sample_data = [
            {
                "Patient_Name": "Sample,Patient",
                "DOB": "1990-01-01",
                "Sex": "F",
                "Age": "35 Y",
                "Tel_No": "555-123-4567",
                "Acc_No": "12345",
                "Called": False,
                "Call_Date": "",
                "Call_Time": "",
                "Contact_Status": "",
                "Appointment_Scheduled": False,
                "Appointment_Date": "",
                "Appointment_Time": "",
                "Declined_Reason": "",
                "Notes": "",
                "Staff_Member": "",
                "Follow_Up_Needed": False,
                "Follow_Up_Date": ""
            }
        ]
        save_patient_data(sample_data)
    
    # Run the application
    print("=" * 50)
    print("PATIENT TRACKING SYSTEM")
    print("=" * 50)
    print(f"Username: {SHARED_USERNAME}")
    print(f"Password: {SHARED_PASSWORD}")
    print(f"Max concurrent users: {MAX_CONCURRENT_USERS}")
    print("=" * 50)
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)