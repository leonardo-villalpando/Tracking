#!/bin/bash

# AWS EC2 Installation Script for Patient Tracking System
# Run this script on your EC2 instance

echo "=================================="
echo "Patient Tracking System Setup"
echo "=================================="

# Update system
echo "Updating system packages..."
sudo yum update -y

# Install Python 3 and pip
echo "Installing Python 3..."
sudo yum install python3 python3-pip -y

# Install required Python packages
echo "Installing Python dependencies..."
pip3 install --user flask flask-socketio pandas werkzeug

# Create application directory
echo "Setting up application directory..."
mkdir -p ~/patient-tracker
cd ~/patient-tracker

# Create templates directory
mkdir -p templates

# Create uploads and backups directories
mkdir -p uploads backups

# Set permissions
chmod 755 ~/patient-tracker
chmod 755 ~/patient-tracker/templates
chmod 755 ~/patient-tracker/uploads
chmod 755 ~/patient-tracker/backups

echo "=================================="
echo "Setup completed!"
echo "=================================="
echo "Next steps:"
echo "1. Upload your files to ~/patient-tracker/"
echo "2. Place HTML templates in ~/patient-tracker/templates/"
echo "3. Run: cd ~/patient-tracker && python3 server.py"
echo "4. Access via: http://YOUR_EC2_IP:5000"
echo "=================================="