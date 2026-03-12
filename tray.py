"""
Network Monitor - System Tray Integration
Windows system tray icon with real-time speed display.
"""

import pystray
from PIL import Image, ImageDraw, ImageFont
import threading
import time
from typing import Callable, Optional

class TrayIcon:
    def __init__(self, monitor_callback: Optional[Callable] = None):
        self.icon = None
        self.monitor_callback = monitor_callback
        self.current_download = 0
        self.current_upload = 0
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        
        # Menu state
        self.monitoring_paused = False
        
    def _create_image(self, text: str = "NM") -> Image.Image:
        """Create tray icon image with network speed indicator"""
        width = 64
        height = 64
        
        # Create gradient background
        image = Image.new('RGBA', (width, height), (30, 41, 59, 255))
        dc = ImageDraw.Draw(image)
        
        # Draw circle background
        dc.ellipse([4, 4, 60, 60], fill=(59, 130, 246, 255), outline=(139, 92, 246, 255), width=2)
        
        # Try to use a font, fallback to default
        try:
            font = ImageFont.truetype("segoeui.ttf", 16)
        except:
            font = ImageFont.load_default()
        
        # Draw text
        bbox = dc.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        position = ((width - text_width) // 2, (height - text_height) // 2 - 2)
        dc.text(position, text, fill=(255, 255, 255, 255), font=font)
        
        return image
    
    def _create_speed_image(self, download_speed: float, upload_speed: float) -> Image.Image:
        """Create icon showing current speeds"""
        width = 64
        height = 64
        
        image = Image.new('RGBA', (width, height), (15, 23, 42, 255))
        dc = ImageDraw.Draw(image)
        
        # Determine color based on activity
        total_speed = download_speed + upload_speed
        if total_speed > 1024 * 1024:  # > 1 MB/s
            color = (239, 68, 68, 255)  # Red (high activity)
        elif total_speed > 100 * 1024:  # > 100 KB/s
            color = (245, 158, 11, 255)  # Orange (medium activity)
        else:
            color = (16, 185, 129, 255)  # Green (low activity)
        
        # Draw activity indicator circle
        dc.ellipse([8, 8, 56, 56], fill=color, outline=(255, 255, 255, 100), width=2)
        
        # Draw speed indicator
        try:
            font = ImageFont.truetype("segoeui.ttf", 10)
        except:
            font = ImageFont.load_default()
        
        # Format speeds
        def format_speed_small(speed):
            if speed > 1024 * 1024:
                return f"{speed / (1024 * 1024):.0f}M"
            elif speed > 1024:
                return f"{speed / 1024:.0f}K"
            else:
                return f"{speed:.0f}"
        
        # Draw download arrow and speed
        dc.text((18, 15), "↓", fill=(255, 255, 255, 255), font=font)
        dc.text((28, 16), format_speed_small(download_speed), fill=(255, 255, 255, 255), font=font)
        
        # Draw upload arrow and speed
        dc.text((18, 32), "↑", fill=(255, 255, 255, 200), font=font)
        dc.text((28, 33), format_speed_small(upload_speed), fill=(255, 255, 255, 200), font=font)
        
        return image
    
    def _format_speed(self, speed: float) -> str:
        """Format speed for display"""
        if speed > 1024 * 1024:
            return f"{speed / (1024 * 1024):.2f} MB/s"
        elif speed > 1024:
            return f"{speed / 1024:.2f} KB/s"
        else:
            return f"{speed:.2f} B/s"
    
    def _update_tooltip(self):
        """Update tooltip with current speeds"""
        if self.icon:
            download_str = self._format_speed(self.current_download)
            upload_str = self._format_speed(self.current_upload)
            status = "PAUSED" if self.monitoring_paused else "Active"
            self.icon.title = f"Network Monitor [{status}]\nDownload: {download_str}\nUpload: {upload_str}"
    
    def _update_icon_loop(self):
        """Background thread to update icon"""
        while self.running:
            if self.icon and not self.monitoring_paused:
                try:
                    # Create new icon with current speeds
                    new_image = self._create_speed_image(self.current_download, self.current_upload)
                    self.icon.icon = new_image
                    self._update_tooltip()
                except Exception as e:
                    pass # Silence tray icon update errors in background
            time.sleep(1)
    
    def update_speeds(self, download: float, upload: float):
        """Update current speeds (called from monitor)"""
        self.current_download = download
        self.current_upload = upload
    
    def _on_open_dashboard(self):
        """Open dashboard in browser"""
        import webbrowser
        webbrowser.open('http://127.0.0.1:5000')
    
    def _on_pause_resume(self):
        """Pause or resume monitoring"""
        self.monitoring_paused = not self.monitoring_paused
        if self.monitor_callback:
            self.monitor_callback('pause' if self.monitoring_paused else 'resume')
        self._update_tooltip()
    
    def _on_reset_stats(self):
        """Reset statistics"""
        if self.monitor_callback:
            self.monitor_callback('reset')
    
    def _on_exit(self):
        """Exit application"""
        self.running = False
        if self.icon:
            self.icon.stop()
        if self.monitor_callback:
            self.monitor_callback('exit')
    
    def _create_menu(self):
        """Create system tray menu"""
        from pystray import Menu, MenuItem
        
        return Menu(
            MenuItem(
                lambda text: f"Download: {self._format_speed(self.current_download)}",
                lambda: None,
                enabled=False
            ),
            MenuItem(
                lambda text: f"Upload: {self._format_speed(self.current_upload)}",
                lambda: None,
                enabled=False
            ),
            MenuItem("Open Dashboard", self._on_open_dashboard),
            MenuItem(
                lambda text: "Resume Monitoring" if self.monitoring_paused else "Pause Monitoring",
                self._on_pause_resume
            ),
            MenuItem("Reset Statistics", self._on_reset_stats),
            MenuItem("Exit", self._on_exit)
        )
    
    def start(self):
        """Start the system tray icon"""
        self.running = True
        
        # Create initial icon
        image = self._create_image("NM")
        
        # Create menu
        menu = self._create_menu()
        
        # Create icon
        self.icon = pystray.Icon(
            "network_monitor",
            image,
            "Network Monitor",
            menu
        )
        
        # Start update thread
        self.update_thread = threading.Thread(target=self._update_icon_loop, daemon=True)
        self.update_thread.start()
        
        # Run icon (blocks until stopped)
        self.icon.run()
    
    def stop(self):
        """Stop the system tray icon"""
        self.running = False
        if self.icon:
            self.icon.stop()

# Standalone test
if __name__ == '__main__':
    tray = TrayIcon()
    
    # Simulate speed updates
    def simulate_speeds():
        import random
        while tray.running:
            tray.update_speeds(
                random.uniform(100000, 5000000),
                random.uniform(50000, 1000000)
            )
            time.sleep(1)
    
    sim_thread = threading.Thread(target=simulate_speeds, daemon=True)
    sim_thread.start()
    
    tray.start()
