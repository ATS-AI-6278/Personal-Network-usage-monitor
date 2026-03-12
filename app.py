"""
Network Monitor - Flask API Server
RESTful API for the dashboard UI.
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import json
from datetime import datetime
import os

from database import Database, db
from monitor import NetworkMonitor

app = Flask(__name__)
app.config['SECRET_KEY'] = 'network-monitor-secret-key'

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global monitor instance
monitor = NetworkMonitor(db, callback=lambda data: socketio.emit('network_update', data, namespace='/'))

@socketio.on('connect')
def handle_connect():
    monitor.active_clients += 1

@socketio.on('disconnect')
def handle_disconnect():
    monitor.active_clients = max(0, monitor.active_clients - 1)

# Latest real-time data
latest_data = {
    'download_speed': 0,
    'upload_speed': 0,
    'connections': 0,
    'processes': 0
}

def update_callback(data):
    global latest_data
    latest_data = {
        'download_speed': data.get('download_speed', 0),
        'upload_speed': data.get('upload_speed', 0),
        'connections': data.get('connections', 0),
        'processes': data.get('processes', 0),
        'local_ip': data.get('local_ip'),
        'ping_ms': data.get('ping_ms')
    }
    socketio.emit('network_update', latest_data, namespace='/')

monitor.callback = update_callback

def get_ip_info():
    """Get local IP address info"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip
    except:
        return '127.0.0.1'

def get_ping():
    """Get ping to 8.8.8.8"""
    try:
        import subprocess
        import platform
        import re
        system = platform.system().lower()
        if system == 'windows':
            cmd = ['ping', '-n', '1', '-w', '1000', '8.8.8.8']
        else:
            cmd = ['ping', '-c', '1', '-W', '1', '8.8.8.8']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            if system == 'windows':
                match = re.search(r'time[<=](\d+)ms', result.stdout)
            else:
                match = re.search(r'time=(\d+\.?\d*) ms', result.stdout)
            if match:
                return float(match.group(1))
    except:
        pass
    return None

@app.route('/')
def index():
    return render_template('premium.html')

@app.route('/reports')
def reports():
    return render_template('reports.html')

@app.route('/api/current')
def api_current():
    """Get current network statistics"""
    today = db.get_today_usage()
    total = db.get_total_usage()
    
    return jsonify({
        'download_speed': latest_data.get('download_speed', 0),
        'upload_speed': latest_data.get('upload_speed', 0),
        'connections': latest_data.get('connections', 0),
        'today_download': today.get('today_download', 0),
        'today_upload': today.get('today_upload', 0),
        'peak_download': today.get('peak_download', 0),
        'peak_upload': today.get('peak_upload', 0),
        'total_download': total.get('total_download', 0),
        'total_upload': total.get('total_upload', 0),
        'local_ip': latest_data.get('local_ip') or get_ip_info(),
        'ping_ms': latest_data.get('ping_ms') or get_ping()
    })

@app.route('/api/live')
def api_live():
    """Get live data for charts (last 60 seconds)"""
    seconds = request.args.get('seconds', 60, type=int)
    data = db.get_live_data(seconds)
    
    # Format for Chart.js
    timestamps = []
    download_speeds = []
    upload_speeds = []
    
    for row in data:
        timestamps.append(row['timestamp'])
        download_speeds.append(row['download_speed'])
        upload_speeds.append(row['upload_speed'])
    
    return jsonify({
        'timestamps': timestamps,
        'download_speeds': download_speeds,
        'upload_speeds': upload_speeds
    })

@app.route('/api/processes')
def api_processes():
    """Get top processes by network usage"""
    minutes = request.args.get('minutes', 5, type=int)
    data = db.get_top_processes(minutes)
    return jsonify(data)

@app.route('/api/hourly')
def api_hourly():
    """Get hourly statistics"""
    hours = request.args.get('hours', 24, type=int)
    data = db.get_hourly_stats(hours)
    return jsonify(data)

@app.route('/api/daily')
def api_daily():
    """Get daily statistics"""
    days = request.args.get('days', 30, type=int)
    data = db.get_daily_stats(days)
    return jsonify(data)

@app.route('/api/connections')
def api_connections():
    """Get current connections"""
    limit = request.args.get('limit', 100, type=int)
    data = db.get_current_connections(limit)
    return jsonify(data)

@app.route('/api/top-ips')
def api_top_ips():
    """Get top remote IPs"""
    minutes = request.args.get('minutes', 30, type=int)
    limit = request.args.get('limit', 20, type=int)
    data = db.get_top_ips(minutes, limit)
    return jsonify(data)

@app.route('/api/alerts')
def api_alerts():
    """Get recent alerts"""
    limit = request.args.get('limit', 10, type=int)
    data = db.get_recent_alerts(limit)
    return jsonify(data)

@app.route('/api/weekly')
def api_weekly():
    """Get weekly statistics"""
    weeks = request.args.get('weeks', 12, type=int)
    data = db.get_weekly_stats(weeks)
    return jsonify(data)

@app.route('/api/monthly')
def api_monthly():
    """Get monthly statistics"""
    months = request.args.get('months', 12, type=int)
    data = db.get_monthly_stats(months)
    return jsonify(data)

@app.route('/api/yearly')
def api_yearly():
    """Get yearly statistics"""
    data = db.get_yearly_stats()
    return jsonify(data)

@app.route('/api/date-range')
def api_date_range():
    """Get statistics for custom date range"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    if not start_date or not end_date:
        return jsonify({'error': 'start and end dates required'}), 400
    data = db.get_date_range_stats(start_date, end_date)
    return jsonify(data)

@app.route('/api/hourly-breakdown')
def api_hourly_breakdown():
    """Get hour-by-hour breakdown for a specific date"""
    date = request.args.get('date')
    if not date:
        return jsonify({'error': 'date required'}), 400
    data = db.get_hourly_breakdown(date)
    return jsonify(data)

@app.route('/api/summary')
def api_summary():
    """Get summary statistics"""
    days = request.args.get('days', 30, type=int)
    data = db.get_summary_stats(days)
    return jsonify(data)

@app.route('/api/report-summary')
def api_report_summary():
    """Get specialized report summary"""
    days = request.args.get('days', 30, type=int)
    data = db.get_report_summary(days)
    return jsonify(data)

@app.route('/api/process-details')
def api_process_details():
    """Get detailed process statistics"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    limit = request.args.get('limit', 50, type=int)
    data = db.get_process_details(start_date, end_date, limit)
    return jsonify(data)

@app.route('/api/connection-details')
def api_connection_details():
    """Get detailed connection information with filters"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    remote_ip = request.args.get('ip')
    process_name = request.args.get('process')
    limit = request.args.get('limit', 100, type=int)
    data = db.get_connection_details(start_date, end_date, remote_ip, process_name, limit)
    return jsonify(data)

@app.route('/api/total-usage')
def api_total_usage():
    """Get all-time cumulative usage statistics"""
    data = db.get_all_time_stats()
    return jsonify(data)

@app.route('/api/all-time-processes')
def api_all_time_processes():
    """Get all-time top processes by total usage"""
    limit = request.args.get('limit', 20, type=int)
    data = db.get_all_time_top_processes(limit)
    return jsonify(data)

@app.route('/api/all-time-ips')
def api_all_time_ips():
    """Get all-time top remote IPs by traffic"""
    limit = request.args.get('limit', 20, type=int)
    data = db.get_all_time_top_ips(limit)
    return jsonify(data)

@app.route('/api/usage-by-period')
def api_usage_by_period():
    """Get usage data for selected time period"""
    period = request.args.get('period', 'today')  # 1h, today, week, month, year
    
    if period == '1h':
        data = db.get_live_data(3600)
        total_download = sum((d.get('download_bytes') or 0) for d in data) if data else 0
        total_upload = sum((d.get('upload_bytes') or 0) for d in data) if data else 0
        chart_data = db.get_live_data(3600)
    elif period == 'week':
        data = db.get_weekly_stats(1)
        total_download = sum((d.get('total_download') or 0) for d in data) if data else 0
        total_upload = sum((d.get('total_upload') or 0) for d in data) if data else 0
        chart_data = db.get_daily_stats(7)
    elif period == 'month':
        data = db.get_monthly_stats(1)
        total_download = sum((d.get('total_download') or 0) for d in data) if data else 0
        total_upload = sum((d.get('total_upload') or 0) for d in data) if data else 0
        chart_data = db.get_daily_stats(30)
    elif period == 'year':
        data = db.get_yearly_stats()
        total_download = sum((d.get('total_download') or 0) for d in data) if data else 0
        total_upload = sum((d.get('total_upload') or 0) for d in data) if data else 0
        chart_data = db.get_monthly_stats(12)
    else:  # today default
        today = db.get_today_usage()
        total_download = today.get('today_download', 0)
        total_upload = today.get('today_upload', 0)
        chart_data = db.get_hourly_stats(24)
    
    return jsonify({
        'period': period,
        'total_download': total_download or 0,
        'total_upload': total_upload or 0,
        'total_traffic': (total_download or 0) + (total_upload or 0),
        'chart_data': chart_data
    })

def run_server(host='127.0.0.1', port=5000, debug=False):
    """Run the Flask server with monitoring"""
    # Start monitoring
    monitor.start()
    
    try:
        # Run Flask-SocketIO
        # allow_unsafe_werkzeug=True is needed to run as a background service
        socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True)
    finally:
        monitor.stop()

if __name__ == '__main__':
    run_server()
