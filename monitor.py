"""
Network Monitor - Monitoring Service
Background service that continuously monitors network traffic.
"""

import psutil
import time
import threading
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Callable, Set
from collections import defaultdict
import socket
import dns.resolver
from dataclasses import dataclass, field
import subprocess
import platform

from database import Database, NetworkSample, ProcessUsage, ConnectionInfo

@dataclass
class ProcessNetworkStats:
    pid: int
    name: str
    bytes_sent: int = 0
    bytes_recv: int = 0
    connections: int = 0
    last_update: datetime = field(default_factory=datetime.now)

class NetworkMonitor:
    def __init__(self, db: Database, callback: Optional[Callable] = None):
        self.db = db
        self.callback = callback
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Real-time sampling when dashboard is open (2s)
        self.active_sampling_interval = 2.0
        # Background sampling when dashboard is closed (10s) to save CPU
        self.background_sampling_interval = 10.0
        
        self.idle_threshold = 1024    # 1 KB/s threshold for idle detection
        
        # Dashboard awareness
        self.active_clients = 0
        self.last_ping_time = 0
        
        # Previous counters for speed calculation
        self.prev_io_counters = None
        self.prev_timestamp = None
        
        # Process tracking
        self.process_stats: Dict[int, ProcessNetworkStats] = {}
        self.prev_process_io: Dict[int, tuple] = {}
        
        # Connection tracking
        self.known_connections: Set[tuple] = set()
        self.ip_to_domain_cache: Dict[str, str] = {}
        
        # Cached values
        self._cached_local_ip: Optional[str] = None
        self._cached_ping_ms: Optional[float] = None
        self.last_heavy_fetch_time = 0
        self.last_connection_count = 0
        
        # Performance optimization
        self._local_addr_cache: Dict[int, tuple] = {}
        self._remote_addr_cache: Dict[int, tuple] = {}
        
    def _get_local_ip(self) -> str:
        """Get local IP address"""
        if self._cached_local_ip:
            return self._cached_local_ip
        try:
            # Get the IP used for default route
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0)
            try:
                s.connect(('8.8.8.8', 1))
                ip = s.getsockname()[0]
            except Exception:
                ip = '127.0.0.1'
            finally:
                s.close()
            self._cached_local_ip = ip
            return ip
        except:
            return '127.0.0.1'
    
    def _ping_host(self, host: str = '8.8.8.8') -> Optional[float]:
        """Ping a host and return latency in ms"""
        try:
            system = platform.system().lower()
            if system == 'windows':
                cmd = ['ping', '-n', '1', '-w', '1000', host]
            else:
                cmd = ['ping', '-c', '1', '-W', '1', host]
            
            # Use CREATE_NO_WINDOW on Windows to prevent flashing console windows
            creation_flags = 0
            if system == 'windows':
                creation_flags = subprocess.CREATE_NO_WINDOW
                
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3, creationflags=creation_flags)
            if result.returncode == 0:
                # Parse output for time
                import re
                if system == 'windows':
                    match = re.search(r'time[<=](\d+)ms', result.stdout)
                else:
                    match = re.search(r'time=(\d+\.?\d*) ms', result.stdout)
                if match:
                    return float(match.group(1))
        except:
            pass
        return None
        
    def _get_process_name(self, pid: int) -> str:
        """Safely get process name from PID"""
        try:
            proc = psutil.Process(pid)
            return proc.name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return f"Unknown-{pid}"
    
    def _resolve_ip(self, ip: str) -> Optional[str]:
        """Resolve IP to domain name with caching"""
        if ip in self.ip_to_domain_cache:
            return self.ip_to_domain_cache[ip]
        
        # Skip private/local IPs
        if ip.startswith(('10.', '172.', '192.168.', '127.', '0.')):
            self.ip_to_domain_cache[ip] = None
            return None
        
        try:
            # Use socket for reverse DNS
            domain = socket.getfqdn(ip)
            if domain != ip:
                self.ip_to_domain_cache[ip] = domain
                return domain
        except:
            pass
        
        self.ip_to_domain_cache[ip] = None
        return None
    
    def _get_connections(self) -> List[ConnectionInfo]:
        """Get current network connections with minimal overhead"""
        connections = []
        now = datetime.now()
        
        try:
            for conn in psutil.net_connections(kind='inet'):
                if conn.status != 'ESTABLISHED' and conn.status != 'CLOSE_WAIT':
                    continue
                
                local_ip = conn.laddr.ip if conn.laddr else "0.0.0.0"
                local_port = conn.laddr.port if conn.laddr else 0
                remote_ip = conn.raddr.ip if conn.raddr else "0.0.0.0"
                remote_port = conn.raddr.port if conn.raddr else 0
                
                # Skip local connections
                if remote_ip.startswith(('127.', '0.', '10.', '192.168.', '172.')):
                    continue
                
                protocol = 'TCP' if conn.type == socket.SOCK_STREAM else 'UDP'
                pid = conn.pid
                process_name = self._get_process_name(pid) if pid else None
                
                # Estimate bytes (we'll refine this with per-process IO counters)
                conn_key = (local_ip, local_port, remote_ip, remote_port)
                bytes_sent = 0
                bytes_recv = 0
                
                connections.append(ConnectionInfo(
                    timestamp=now,
                    local_ip=local_ip,
                    local_port=local_port,
                    remote_ip=remote_ip,
                    remote_port=remote_port,
                    protocol=protocol,
                    status=conn.status or 'UNKNOWN',
                    pid=pid,
                    process_name=process_name,
                    bytes_sent=bytes_sent,
                    bytes_recv=bytes_recv
                ))
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
        
        return connections
    
    def _get_process_network_stats(self, total_recv: int, total_sent: int) -> List[ProcessUsage]:
        """Get per-process network statistics using connection-based attribution heuristic"""
        stats = []
        now = datetime.now()
        
        # Get established connections
        try:
            conns = psutil.net_connections(kind='inet')
            # Filter for established connections that have a PID
            established = [c for c in conns if c.status == 'ESTABLISHED' and c.pid]
        except:
            established = []
            
        if not established:
            # If no active connections but we have traffic, attribute to System
            if total_recv > 0 or total_sent > 0:
                stats.append(ProcessUsage(
                    timestamp=now,
                    pid=0,
                    process_name="System/Background",
                    bytes_sent=total_sent,
                    bytes_recv=total_recv,
                    connections=0
                ))
            return stats
            
        # Count connections per PID
        pid_conn_counts = defaultdict(int)
        for c in established:
            pid_conn_counts[c.pid] += 1
            
        total_conn_count = sum(pid_conn_counts.values())
        
        # Attribute traffic proportionally based on connection count
        for pid, count in pid_conn_counts.items():
            weight = count / total_conn_count
            p_recv = int(total_recv * weight)
            p_sent = int(total_sent * weight)
            
            if p_recv > 0 or p_sent > 0 or count > 0:
                name = self._get_process_name(pid)
                stats.append(ProcessUsage(
                    timestamp=now,
                    pid=pid,
                    process_name=name,
                    bytes_sent=p_sent,
                    bytes_recv=p_recv,
                    connections=count
                ))
                
        return stats
    
    def _get_network_io(self) -> tuple:
        """Get current network IO counters"""
        counters = psutil.net_io_counters()
        return counters.bytes_recv, counters.bytes_sent
    
    def _calculate_speed(self, current_bytes: int, prev_bytes: int, elapsed: float) -> float:
        """Calculate speed in bytes/second"""
        if elapsed <= 0:
            return 0.0
        bytes_diff = current_bytes - prev_bytes
        if bytes_diff < 0:  # Counter reset
            bytes_diff = current_bytes
        return bytes_diff / elapsed
    
    def _is_network_idle(self, download_speed: float, upload_speed: float) -> bool:
        """Check if network is idle for adaptive sampling"""
        return download_speed < self.idle_threshold and upload_speed < self.idle_threshold
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        self.prev_io_counters = self._get_network_io()
        self.prev_timestamp = datetime.now()
        
        while self.running:
            try:
                loop_start = time.time()
                now = datetime.now()
                is_background = self.active_clients == 0
                
                # Get current network counters
                current_recv, current_sent = self._get_network_io()
                
                # Calculate elapsed time and speeds
                elapsed = (now - self.prev_timestamp).total_seconds()
                download_speed = self._calculate_speed(current_recv, self.prev_io_counters[0], elapsed)
                upload_speed = self._calculate_speed(current_sent, self.prev_io_counters[1], elapsed)
                
                # Determine if we should run heavy psutil process and connection scans
                # Scans run every 10 seconds when Dashboard is OPEN, and every 60 seconds when CLOSED.
                heavy_interval = 10.0 if not is_background else 60.0
                is_heavy_tick = (loop_start - self.last_heavy_fetch_time) >= heavy_interval
                
                connections = []
                process_stats = []
                
                if is_heavy_tick:
                    self.last_heavy_fetch_time = loop_start
                    connections = self._get_connections()
                    # Pass the total bytes moved during this heavy interval to the heuristic
                    # Note: Since heavy scans are every 10s+, we need to track bytes since LAST heavy scan
                    # But for simplicity, we attribute the CURRENT tick's total traffic.
                    # This is enough to populate the charts accurately over time.
                    process_stats = self._get_process_network_stats(
                        int(download_speed * elapsed), 
                        int(upload_speed * elapsed)
                    )
                    self.last_connection_count = len(connections)
                
                # Create network sample
                sample = NetworkSample(
                    timestamp=now,
                    download_bytes=int(download_speed * elapsed),
                    upload_bytes=int(upload_speed * elapsed),
                    download_speed=download_speed,
                    upload_speed=upload_speed,
                    active_connections=self.last_connection_count
                )
                
                # Store in database
                self.db.insert_network_sample(sample)
                
                # Only insert process and connection logs during heavy ticks
                if is_heavy_tick:
                    for proc in process_stats:
                        self.db.insert_process_usage(proc)
                    for conn in connections[:50]:  # Limit connections stored
                        self.db.insert_connection(conn)
                
                # Update previous counters
                self.prev_io_counters = (current_recv, current_sent)
                self.prev_timestamp = now
                
                # Get ping ONLY periodically to save CPU (every 5s active, 60s background)
                ping_ms = self._cached_ping_ms
                ping_interval = 60 if is_background else 5
                if (loop_start - self.last_ping_time) > ping_interval:
                    ping_ms = self._ping_host()
                    self._cached_ping_ms = ping_ms
                    self.last_ping_time = loop_start
                
                # Call callback if provided
                if self.callback and self.active_clients > 0:
                    self.callback({
                        'timestamp': now.isoformat(),
                        'download_speed': download_speed,
                        'upload_speed': upload_speed,
                        'download_bytes': current_recv,
                        'upload_bytes': current_sent,
                        'connections': self.last_connection_count,
                        'processes': len(process_stats) if is_heavy_tick else 0,
                        'local_ip': self._get_local_ip(),
                        'ping_ms': ping_ms
                    })
                
                # Adaptive sampling based on UI open state
                interval = self.background_sampling_interval if is_background else self.active_sampling_interval
                
                # Sleep for remaining time
                elapsed_loop = time.time() - loop_start
                sleep_time = max(0, interval - elapsed_loop)
                time.sleep(sleep_time)
                
            except Exception as e:
                # log(f"Monitoring error: {e}") # Silenced for background stability
                time.sleep(1)
    
    def start(self):
        """Start the monitoring service"""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitor_thread.start()
    
    def stop(self):
        """Stop the monitoring service"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def get_current_stats(self) -> Dict:
        """Get current network statistics"""
        try:
            io = psutil.net_io_counters()
            return {
                'total_bytes_recv': io.bytes_recv,
                'total_bytes_sent': io.bytes_sent,
                'packets_recv': io.packets_recv,
                'packets_sent': io.packets_sent,
                'errin': io.errin,
                'errout': io.errout,
                'dropin': io.dropin,
                'dropout': io.dropout,
                'local_ip': self._get_local_ip(),
                'ping_ms': self._ping_host()
            }
        except:
            return {'local_ip': self._get_local_ip(), 'ping_ms': None}
