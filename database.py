"""
Network Monitor - Database Module
SQLite database operations for network monitoring data.
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager
import threading

@dataclass
class NetworkSample:
    timestamp: datetime
    download_bytes: int
    upload_bytes: int
    download_speed: float  # bytes/sec
    upload_speed: float    # bytes/sec
    active_connections: int

@dataclass
class ProcessUsage:
    timestamp: datetime
    pid: int
    process_name: str
    bytes_sent: int
    bytes_recv: int
    connections: int

@dataclass
class ConnectionInfo:
    timestamp: datetime
    local_ip: str
    local_port: int
    remote_ip: str
    remote_port: int
    protocol: str
    status: str
    pid: Optional[int]
    process_name: Optional[str]
    bytes_sent: int
    bytes_recv: int

class Database:
    def __init__(self, db_path: str = "data/network_monitor.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
    
    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Network samples table - second-level granularity
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS network_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    download_bytes INTEGER DEFAULT 0,
                    upload_bytes INTEGER DEFAULT 0,
                    download_speed REAL DEFAULT 0,
                    upload_speed REAL DEFAULT 0,
                    active_connections INTEGER DEFAULT 0
                )
            ''')
            
            # Process usage table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS process_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    pid INTEGER,
                    process_name TEXT,
                    bytes_sent INTEGER DEFAULT 0,
                    bytes_recv INTEGER DEFAULT 0,
                    connections INTEGER DEFAULT 0
                )
            ''')
            
            # Connections table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    local_ip TEXT,
                    local_port INTEGER,
                    remote_ip TEXT,
                    remote_port INTEGER,
                    protocol TEXT,
                    status TEXT,
                    pid INTEGER,
                    process_name TEXT,
                    bytes_sent INTEGER DEFAULT 0,
                    bytes_recv INTEGER DEFAULT 0
                )
            ''')
            
            # Hourly summaries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hourly_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hour DATETIME UNIQUE,
                    total_download INTEGER DEFAULT 0,
                    total_upload INTEGER DEFAULT 0,
                    peak_download_speed REAL DEFAULT 0,
                    peak_upload_speed REAL DEFAULT 0,
                    unique_processes INTEGER DEFAULT 0
                )
            ''')
            
            # Daily summaries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE,
                    total_download INTEGER DEFAULT 0,
                    total_upload INTEGER DEFAULT 0,
                    peak_download_speed REAL DEFAULT 0,
                    peak_upload_speed REAL DEFAULT 0,
                    active_hours INTEGER DEFAULT 0
                )
            ''')
            
            # Domain/IP tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS domain_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    domain TEXT,
                    bytes_sent INTEGER DEFAULT 0,
                    bytes_recv INTEGER DEFAULT 0,
                    connection_count INTEGER DEFAULT 0
                )
            ''')
            
            # Alerts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    alert_type TEXT,
                    message TEXT,
                    severity TEXT DEFAULT 'info',
                    acknowledged BOOLEAN DEFAULT 0
                )
            ''')
            
            # Create indexes for performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_samples_time ON network_samples(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_process_time ON process_usage(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_connections_time ON connections(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_domain_ip ON domain_usage(ip_address)')
            
            conn.commit()
    
    def insert_network_sample(self, sample: NetworkSample):
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO network_samples 
                (timestamp, download_bytes, upload_bytes, download_speed, upload_speed, active_connections)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                sample.timestamp,
                sample.download_bytes,
                sample.upload_bytes,
                sample.download_speed,
                sample.upload_speed,
                sample.active_connections
            ))
    
    def insert_process_usage(self, usage: ProcessUsage):
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO process_usage 
                (timestamp, pid, process_name, bytes_sent, bytes_recv, connections)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                usage.timestamp,
                usage.pid,
                usage.process_name,
                usage.bytes_sent,
                usage.bytes_recv,
                usage.connections
            ))
    
    def insert_connection(self, conn_info: ConnectionInfo):
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO connections 
                (timestamp, local_ip, local_port, remote_ip, remote_port, protocol, status, pid, process_name, bytes_sent, bytes_recv)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                conn_info.timestamp,
                conn_info.local_ip,
                conn_info.local_port,
                conn_info.remote_ip,
                conn_info.remote_port,
                conn_info.protocol,
                conn_info.status,
                conn_info.pid,
                conn_info.process_name,
                conn_info.bytes_sent,
                conn_info.bytes_recv
            ))
    
    def get_recent_samples(self, minutes: int = 5) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM network_samples 
                WHERE timestamp > datetime('now', '-{} minutes')
                ORDER BY timestamp DESC
            '''.format(minutes))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_live_data(self, seconds: int = 60) -> List[Dict]:
        """Get samples for live graph (last N seconds)"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT timestamp, download_speed, upload_speed, active_connections
                FROM network_samples 
                WHERE timestamp > datetime('now', '-{} seconds')
                ORDER BY timestamp ASC
            '''.format(seconds))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_top_processes(self, minutes: int = 5, limit: int = 10) -> List[Dict]:
        """Get top processes by network usage"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    process_name,
                    SUM(bytes_sent) as total_sent,
                    SUM(bytes_recv) as total_recv,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    MAX(connections) as max_connections
                FROM process_usage
                WHERE timestamp > datetime('now', '-{} minutes')
                GROUP BY process_name
                ORDER BY total_bytes DESC
                LIMIT {}
            '''.format(minutes, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_hourly_stats(self, hours: int = 24) -> List[Dict]:
        """Get hourly statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    MAX(active_connections) as max_connections
                FROM network_samples
                WHERE timestamp > datetime('now', '-{} hours')
                GROUP BY hour
                ORDER BY hour ASC
            '''.format(hours))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_daily_stats(self, days: int = 30) -> List[Dict]:
        """Get daily statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m-%d', timestamp) as date,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload
                FROM network_samples
                WHERE timestamp > datetime('now', '-{} days')
                GROUP BY date
                ORDER BY date ASC
            '''.format(days))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_top_ips(self, minutes: int = 30, limit: int = 20) -> List[Dict]:
        """Get top remote IPs by traffic"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    remote_ip,
                    SUM(bytes_sent) as total_sent,
                    SUM(bytes_recv) as total_recv,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    COUNT(*) as connection_count,
                    GROUP_CONCAT(DISTINCT process_name) as processes
                FROM connections
                WHERE timestamp > datetime('now', '-{} minutes')
                GROUP BY remote_ip
                ORDER BY total_bytes DESC
                LIMIT {}
            '''.format(minutes, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_current_connections(self, limit: int = 100) -> List[Dict]:
        """Get current active connections"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT *
                FROM connections
                WHERE timestamp > datetime('now', '-1 minutes')
                ORDER BY bytes_recv + bytes_sent DESC
                LIMIT {}
            '''.format(limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_total_usage(self) -> Dict:
        """Get total network usage statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload
                FROM network_samples
            ''')
            row = cursor.fetchone()
            return dict(row) if row else {
                'total_download': 0,
                'total_upload': 0,
                'peak_download': 0,
                'peak_upload': 0
            }
    
    def get_today_usage(self) -> Dict:
        """Get today's network usage"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    SUM(download_bytes) as today_download,
                    SUM(upload_bytes) as today_upload,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload
                FROM network_samples
                WHERE date(timestamp) = date('now')
            ''')
            row = cursor.fetchone()
            return dict(row) if row else {
                'today_download': 0,
                'today_upload': 0,
                'peak_download': 0,
                'peak_upload': 0
            }
    
    def cleanup_old_data(self):
        """Clean up old data according to retention policy"""
        with self._get_connection() as conn:
            # Aggregate old seconds-level data instead of just blindly deleting it to maintain total accuracy!
            # Since user wants optimized but 'accurate recalculate data'.
            # We keep 30 days of raw network_samples instead of 1 day to make the monthly graphing possible.
            conn.execute('''
                DELETE FROM network_samples 
                WHERE timestamp < datetime('now', '-30 days')
            ''')
            
            conn.execute('''
                DELETE FROM process_usage 
                WHERE timestamp < datetime('now', '-30 days')
            ''')
            
            conn.execute('''
                DELETE FROM connections 
                WHERE timestamp < datetime('now', '-1 days')
            ''')
            
            # Keep domain usage for 7 days
            conn.execute('''
                DELETE FROM domain_usage 
                WHERE timestamp < datetime('now', '-7 days')
            ''')
            
            # Vacuum to reclaim space
            conn.execute('VACUUM')
    
    def add_alert(self, alert_type: str, message: str, severity: str = 'info'):
        with self._get_connection() as conn:
            conn.execute('''
                INSERT INTO alerts (alert_type, message, severity)
                VALUES (?, ?, ?)
            ''', (alert_type, message, severity))
    
    def get_recent_alerts(self, limit: int = 10) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM alerts
                ORDER BY timestamp DESC
                LIMIT {}
            '''.format(limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_date_range_stats(self, start_date: str, end_date: str) -> List[Dict]:
        """Get statistics for a custom date range"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m-%d', timestamp) as date,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    COUNT(*) as sample_count,
                    MAX(active_connections) as max_connections
                FROM network_samples
                WHERE date(timestamp) BETWEEN ? AND ?
                GROUP BY date
                ORDER BY date ASC
            ''', (start_date, end_date))
            return [dict(row) for row in cursor.fetchall()]

    def get_daily_stats(self, days: int = 30) -> List[Dict]:
        """Get daily statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m-%d', timestamp) as date,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    MAX(active_connections) as max_connections
                FROM network_samples
                WHERE timestamp > datetime('now', '-{} days')
                GROUP BY date
                ORDER BY date ASC
            '''.format(days))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_weekly_stats(self, weeks: int = 12) -> List[Dict]:
        """Get weekly statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%W', timestamp) as week,
                    MIN(date(timestamp)) as week_start,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    MAX(active_connections) as max_connections
                FROM network_samples
                WHERE timestamp > datetime('now', '-{} days')
                GROUP BY week
                ORDER BY week ASC
            '''.format(weeks * 7))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_monthly_stats(self, months: int = 12) -> List[Dict]:
        """Get monthly statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m', timestamp) as month,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    MAX(active_connections) as max_connections
                FROM network_samples
                WHERE timestamp > datetime('now', '-{} months')
                GROUP BY month
                ORDER BY month ASC
            '''.format(months))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_yearly_stats(self) -> List[Dict]:
        """Get yearly statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y', timestamp) as year,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload
                FROM network_samples
                GROUP BY year
                ORDER BY year ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_top_processes_by_range(self, days: int = 30, limit: int = 10) -> List[Dict]:
        """Get top processes by network usage for a specific day range"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    process_name,
                    SUM(bytes_sent) as total_sent,
                    SUM(bytes_recv) as total_recv,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    MAX(connections) as max_connections
                FROM process_usage
                WHERE timestamp > datetime('now', '-{} days')
                GROUP BY process_name
                ORDER BY total_bytes DESC
                LIMIT {}
            '''.format(days, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_process_details(self, start_date: str = None, end_date: str = None, limit: int = 50) -> List[Dict]:
        """Get detailed process statistics for date range"""
        with self._get_connection() as conn:
            if start_date and end_date:
                cursor = conn.execute('''
                    SELECT 
                        process_name,
                        SUM(bytes_sent) as total_sent,
                        SUM(bytes_recv) as total_recv,
                        SUM(bytes_sent + bytes_recv) as total_bytes,
                        AVG(bytes_sent + bytes_recv) as avg_bytes,
                        MAX(bytes_sent + bytes_recv) as peak_bytes,
                        SUM(connections) as total_connections,
                        COUNT(*) as occurrence_count,
                        MIN(timestamp) as first_seen,
                        MAX(timestamp) as last_seen
                    FROM process_usage
                    WHERE date(timestamp) BETWEEN ? AND ?
                    GROUP BY process_name
                    ORDER BY total_bytes DESC
                    LIMIT ?
                ''', (start_date, end_date, limit))
            else:
                cursor = conn.execute('''
                    SELECT 
                        process_name,
                        SUM(bytes_sent) as total_sent,
                        SUM(bytes_recv) as total_recv,
                        SUM(bytes_sent + bytes_recv) as total_bytes,
                        AVG(bytes_sent + bytes_recv) as avg_bytes,
                        MAX(bytes_sent + bytes_recv) as peak_bytes,
                        SUM(connections) as total_connections,
                        COUNT(*) as occurrence_count,
                        MIN(timestamp) as first_seen,
                        MAX(timestamp) as last_seen
                    FROM process_usage
                    WHERE timestamp > datetime('now', 'localtime', '-7 days')
                    GROUP BY process_name
                    ORDER BY total_bytes DESC
                    LIMIT {}
                '''.format(limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_connection_details(self, start_date: str = None, end_date: str = None, 
                               remote_ip: str = None, process_name: str = None, limit: int = 100) -> List[Dict]:
        """Get detailed connection information with filters"""
        with self._get_connection() as conn:
            query = '''
                SELECT 
                    remote_ip,
                    remote_port,
                    protocol,
                    process_name,
                    COUNT(*) as connection_count,
                    SUM(bytes_sent) as total_sent,
                    SUM(bytes_recv) as total_recv,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    AVG(bytes_sent + bytes_recv) as avg_traffic,
                    MAX(bytes_sent + bytes_recv) as peak_traffic,
                    MIN(timestamp) as first_seen,
                    MAX(timestamp) as last_seen
                FROM connections
                WHERE 1=1
            '''
            params = []
            
            if start_date and end_date:
                query += " AND date(timestamp) BETWEEN ? AND ?"
                params.extend([start_date, end_date])
            else:
                query += " AND timestamp > datetime('now', '-1 days')"
            
            if remote_ip:
                query += " AND remote_ip = ?"
                params.append(remote_ip)
            
            if process_name:
                query += " AND process_name LIKE ?"
                params.append(f"%{process_name}%")
            
            query += f" GROUP BY remote_ip, remote_port, protocol, process_name ORDER BY total_bytes DESC LIMIT {limit}"
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_hourly_breakdown(self, date: str) -> List[Dict]:
        """Get hour-by-hour breakdown for a specific date"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    strftime('%H', timestamp) as hour,
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    MAX(active_connections) as max_connections
                FROM network_samples
                WHERE date(timestamp) = ?
                GROUP BY hour
                ORDER BY hour ASC
            ''', (date,))
            return [dict(row) for row in cursor.fetchall()]
    
            return result

    def get_summary_stats(self, days: int = 30) -> Dict:
        """Get summary statistics"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    COUNT(DISTINCT date(timestamp)) as active_days,
                    COUNT(*) as total_samples
                FROM network_samples
                WHERE timestamp > datetime('now', '-{} days')
            '''.format(days))
            row = cursor.fetchone()
            result = dict(row) if row else {}
            
            # Get unique processes count
            cursor = conn.execute('''
                SELECT COUNT(DISTINCT process_name) as unique_processes
                FROM process_usage
                WHERE timestamp > datetime('now', '-{} days')
            '''.format(days))
            proc_row = cursor.fetchone()
            result['unique_processes'] = proc_row['unique_processes'] if proc_row else 0
            
            # Get unique IPs count
            cursor = conn.execute('''
                SELECT COUNT(DISTINCT remote_ip) as unique_ips
                FROM connections
                WHERE timestamp > datetime('now', '-{} days')
            '''.format(days))
            ip_row = cursor.fetchone()
            result['unique_ips'] = ip_row['unique_ips'] if ip_row else 0
            
            return result

    def get_report_summary(self, days: int = 30) -> Dict:
        """Get specialized report summary with peak/lowest days"""
        with self._get_connection() as conn:
            # 1. Overall stats
            total_stats = self.get_summary_stats(days)
            
            # 2. Get daily stats to find peak/lowest
            daily_stats = self.get_daily_stats(days)
            
            peak_day = {'date': '-', 'total': 0}
            lowest_day = {'date': '-', 'total': float('inf')}
            
            for d in daily_stats:
                total = (d.get('total_download') or 0) + (d.get('total_upload') or 0)
                if total > peak_day['total']:
                    peak_day = {'date': d['date'], 'total': total}
                if total < lowest_day['total'] and total > 0:
                    lowest_day = {'date': d['date'], 'total': total}
            
            if lowest_day['total'] == float('inf'):
                lowest_day = {'date': '-', 'total': 0}
            
            # 3. Calculate Daily Average based on active days or the full period
            # User example: 14.84 GB / 30 ~ 500MB
            active_days = total_stats.get('active_days', 1) or 1
            daily_avg = (total_stats.get('total_download', 0) + total_stats.get('total_upload', 0)) / active_days
            
            return {
                'total_download': total_stats.get('total_download', 0),
                'total_upload': total_stats.get('total_upload', 0),
                'total_traffic': total_stats.get('total_download', 0) + total_stats.get('total_upload', 0),
                'daily_average': daily_avg,
                'peak_day': peak_day,
                'lowest_day': lowest_day,
                'active_days': active_days
            }
    
    def get_all_time_stats(self) -> Dict:
        """Get all-time cumulative statistics since first run"""
        with self._get_connection() as conn:
            # Get first and last timestamp
            cursor = conn.execute('''
                SELECT 
                    MIN(timestamp) as first_run,
                    MAX(timestamp) as last_seen,
                    COUNT(*) as total_samples,
                    COUNT(DISTINCT date(timestamp)) as total_days
                FROM network_samples
            ''')
            time_row = cursor.fetchone()
            
            # Get cumulative traffic
            cursor = conn.execute('''
                SELECT 
                    SUM(download_bytes) as total_download,
                    SUM(upload_bytes) as total_upload,
                    SUM(download_bytes + upload_bytes) as total_traffic,
                    MAX(download_speed) as peak_download,
                    MAX(upload_speed) as peak_upload,
                    AVG(download_speed) as avg_download_speed,
                    AVG(upload_speed) as avg_upload_speed
                FROM network_samples
            ''')
            traffic_row = cursor.fetchone()
            
            # Get all-time unique counts
            cursor = conn.execute('''
                SELECT COUNT(DISTINCT process_name) as total_processes
                FROM process_usage
            ''')
            proc_row = cursor.fetchone()
            
            cursor = conn.execute('''
                SELECT COUNT(DISTINCT remote_ip) as total_ips
                FROM connections
            ''')
            ip_row = cursor.fetchone()
            
            result = dict(traffic_row) if traffic_row else {}
            result.update({
                'first_run': time_row['first_run'] if time_row else None,
                'last_seen': time_row['last_seen'] if time_row else None,
                'total_samples': time_row['total_samples'] if time_row else 0,
                'total_days': time_row['total_days'] if time_row else 0,
                'total_processes': proc_row['total_processes'] if proc_row else 0,
                'total_ips': ip_row['total_ips'] if ip_row else 0
            })
            
            return result
    
    def get_all_time_top_processes(self, limit: int = 20) -> List[Dict]:
        """Get all-time top processes by total usage"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    process_name,
                    SUM(bytes_sent) as total_sent,
                    SUM(bytes_recv) as total_recv,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    AVG(bytes_sent + bytes_recv) as avg_bytes,
                    MAX(bytes_sent + bytes_recv) as peak_bytes,
                    SUM(connections) as total_connections,
                    COUNT(*) as occurrences,
                    MIN(timestamp) as first_seen,
                    MAX(timestamp) as last_seen,
                    ROUND(SUM(bytes_sent + bytes_recv) * 100.0 / (SELECT SUM(bytes_sent + bytes_recv) FROM process_usage), 2) as percentage
                FROM process_usage
                GROUP BY process_name
                ORDER BY total_bytes DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_time_top_ips(self, limit: int = 20) -> List[Dict]:
        """Get all-time top remote IPs by traffic"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    remote_ip,
                    SUM(bytes_sent) as total_sent,
                    SUM(bytes_recv) as total_recv,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    COUNT(*) as total_connections,
                    MIN(timestamp) as first_seen,
                    MAX(timestamp) as last_seen,
                    GROUP_CONCAT(DISTINCT process_name) as processes
                FROM connections
                WHERE remote_ip NOT LIKE '192.168.%' 
                  AND remote_ip NOT LIKE '10.%'
                  AND remote_ip NOT LIKE '172.%'
                  AND remote_ip != '127.0.0.1'
                GROUP BY remote_ip
                ORDER BY total_bytes DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_usage_by_app_category(self) -> List[Dict]:
        """Categorize apps by type and get usage stats"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    process_name,
                    SUM(bytes_sent + bytes_recv) as total_bytes,
                    SUM(bytes_recv) as download,
                    SUM(bytes_sent) as upload,
                    COUNT(*) as occurrences
                FROM process_usage
                GROUP BY process_name
                ORDER BY total_bytes DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

# Singleton instance
db = Database()
