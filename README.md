# Network Monitor

A Premium Windows-only network monitoring application designed for detailed usage analytics. Continuously monitors internet traffic, provides a stunning glassmorphism dashboard, and runs efficiently in the background with system tray integration.

## Features

- **Premium Glassmorphism UI**: High-end design with blur effects and vibrant gradients.
- **Accurate Per-Process Tracking**: Advanced connection-based attribution for precise process-level network measurement on Windows.
- **Interactive Reports Page**: Dedicated analytics view with:
    - **Usage Summary**: Total Data, Daily Average, Peak, and Lowest usage days.
    - **Advanced Bar Charts**: Switch views between Day, Week, and Month instantly.
    - **Drill-down Analytics**: Click any daily bar to see hourly traffic breakdowns.
- **Real-time Monitoring**: LIVE bandwidth graphs with 1-second updates.
- **System Tray Integration**: Live speed display in the tray icon for quick status checks.
- **Privacy-First**: All data is stored locally in an encrypted SQL database—no external telemetry.
- **Auto-Start**: Seamless Windows startup integration via Task Scheduler.

## Screenshots

### Main Dashboard
![Main Dashboard](Screenshot%202026-03-24%20050950.png)
*Premium Glassmorphism Dashboard with Real-time Network Usage and KPI Metrics*

### Reports Page
![Reports Page](Screenshot%202026-03-24%20051042.png)
*Comprehensive Reports Page with Interactive Charts and Summary Analytics*

## Requirements

- **Windows 10 or Windows 11**
- **Python 3.10 or higher** (Recommended)

## Installation

### Step 1: Clone or Download
Download the project to your desired location.

### Step 2: Install Dependencies
```batch
pip install -r requirements.txt
```

### Step 3: Run the Application
```batch
python main.py
```
*Note: Use --headless to run without the console window.*

### Step 4: Setup Windows Auto-Start
To make the application start automatically when you log in:
```batch
python main.py --setup-startup
```
To remove the auto-start task:
```batch
python main.py --remove-startup
```

### Step 5: Access the Dashboards
- **Main Dashboard**: http://127.0.0.1:5000
- **Reports Page**: http://127.0.0.1:5000/reports

## Project Structure

```
NetworkMonitor/
├── main.py              # Application entry point & service manager
├── app.py               # Flask API & WebSocket server
├── monitor.py           # Core network monitoring engine
├── database.py          # SQLite database & reporting logic
├── tray.py              # System tray UI & speed display
├── requirements.txt     # Dependency list
├── templates/           # UI Layouts (Dashboard & Reports)
├── data/
│   └── network_monitor.db   # Local data storage
└── README.md            # Documentation
```

## Privacy & Performance

- **100% Local**: No data ever leaves your computer.
- **Low Footprint**: Typically < 2% CPU and < 100MB RAM.
- **Smart Retention**: Automatic cleanup of high-resolution data keeps the database size optimized.

## Troubleshooting

### Missing Process Data
Ensure you are running the application with standard user permissions. Some system processes might require higher privileges for connection tracking.

### Port 5000 Busy
If another application is using port 5000, you can modify the port in app.py or main.py.

## Credits

Built with **Flask**, **psutil**, **Chart.js**, and **Tailwind CSS**. Designed for visibility and performance.
