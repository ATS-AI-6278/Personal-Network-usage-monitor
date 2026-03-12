"""
Network Monitor - Main Application Entry Point
Combines monitoring, web dashboard, and system tray.
"""

import sys
import os
import threading
import time
import argparse
from datetime import datetime
import schedule
import subprocess
import platform

# Ensure we can find our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database, db
from monitor import NetworkMonitor
from tray import TrayIcon
from app import app, socketio, monitor, run_server as run_flask_server

# Setup logging to file
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'startup.log')

def log(message):
    try:
        with open(log_file_path, 'a') as f:
            f.write(f"[{datetime.now()}] {message}\n")
    except:
        pass

# Redirect stdout and stderr to the log file for background silence
class Logger:
    def write(self, message):
        if message.strip():
            log(message.strip())
    def flush(self):
        pass

sys.stdout = Logger()
sys.stderr = Logger()

class NetworkMonitorApp:
    def __init__(self):
        self.db = db
        self.monitor = monitor
        self.tray = TrayIcon(monitor_callback=self._tray_callback)
        self.running = False
        self.cleanup_thread: threading.Thread = None
        
    def _tray_callback(self, action: str):
        """Handle tray menu actions"""
        if action == 'pause':
            log("Monitoring paused")
            self.monitor.running = False
        elif action == 'resume':
            log("Monitoring resumed")
            self.monitor.start()
        elif action == 'reset':
            log("Statistics reset requested")
            # Clear today's data
            self._reset_statistics()
        elif action == 'exit':
            log("Exit requested from tray")
            self.stop()
            os._exit(0)
    
    def _reset_statistics(self):
        """Reset today's statistics"""
        try:
            # Database cleanup will happen through normal cleanup
            self.db.add_alert('reset', 'Statistics have been reset by user', 'info')
        except Exception as e:
            log(f"Error resetting statistics: {e}")
    
    def _cleanup_job(self):
        """Scheduled cleanup job"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    
    def _update_tray_from_monitor(self):
        """Update tray with current speeds from monitor"""
        while self.running:
            if self.monitor.running:
                self.tray.update_speeds(
                    self.monitor.prev_io_counters[0] if self.monitor.prev_io_counters else 0,
                    self.monitor.prev_io_counters[1] if self.monitor.prev_io_counters else 0
                )
            time.sleep(1)
    
    def start(self, headless: bool = False):
        """Start the complete application"""
        log(f"Starting Network Monitor (headless={headless})...")
        
        self.running = True
        
        # Start monitoring
        log("Starting monitor...")
        self.monitor.start()
        
        # Schedule cleanup
        log("Scheduling cleanup...")
        schedule.every().day.at("00:00").do(self.db.cleanup_old_data)
        self.cleanup_thread = threading.Thread(target=self._cleanup_job, daemon=True)
        self.cleanup_thread.start()
        
        if not headless:
            log("Starting tray icon...")
            # Start tray in background thread
            tray_thread = threading.Thread(target=self.tray.start, daemon=True)
            tray_thread.start()
        
        # Start update thread for tray speeds
        log("Starting tray update thread...")
        update_thread = threading.Thread(target=self._update_tray_from_monitor, daemon=True)
        update_thread.start()
        
        log(f"Dashboard available at http://127.0.0.1:5000")
        
        try:
            log("Running Flask server...")
            # Run Flask server (this blocks)
            run_flask_server(host='127.0.0.1', port=5000, debug=False)
        except Exception as e:
            log(f"Flask server error: {e}")
        finally:
            log("Stopping application...")
            self.stop()
    
    def stop(self):
        """Stop the application"""
        log("Stopping Network Monitor...")
        self.running = False
        
        # Stop monitoring
        self.monitor.stop()
        
        # Stop tray
        self.icon.stop() if hasattr(self, 'icon') else self.tray.stop()
        
        log("Network Monitor stopped")

def setup_task_scheduler():
    """Register the application in Windows Task Scheduler"""
    if platform.system() != 'Windows':
        print("Task Scheduler integration is only available on Windows.")
        return

    app_path = os.path.abspath(sys.argv[0])
    pythonw_exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        pythonw_exe = sys.executable

    task_name = "NetworkMonitor"
    # Create task to run on login, hidden (pythonw), with highest privileges (needed for some monitor functions)
    command = f'schtasks /create /tn "{task_name}" /tr "\'{pythonw_exe}\' \'{app_path}\' --headless" /sc onlogon /rl highest /f'
    
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Successfully registered '{task_name}' in Task Scheduler.")
        print(f"The application will now start automatically when you log in.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to register task: {e}")
        print("Note: You may need to run this command as Administrator.")

def remove_task_scheduler():
    """Remove the application from Windows Task Scheduler"""
    task_name = "NetworkMonitor"
    command = f'schtasks /delete /tn "{task_name}" /f'
    
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Successfully removed '{task_name}' from Task Scheduler.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to remove task: {e}")

def main():
    parser = argparse.ArgumentParser(description='Network Monitor - Personal network usage monitoring')
    parser.add_argument('--headless', action='store_true', help='Run without system tray (for startup)')
    parser.add_argument('--setup-startup', action='store_true', help='Register application in Task Scheduler to start on login')
    parser.add_argument('--remove-startup', action='store_true', help='Remove application from Task Scheduler')
    
    args = parser.parse_args()
    
    if args.setup_startup:
        setup_task_scheduler()
        return
    
    if args.remove_startup:
        remove_task_scheduler()
        return
    
    # Run the application
    app_instance = NetworkMonitorApp()
    app_instance.start(headless=args.headless)

if __name__ == '__main__':
    main()
