# Service Startup Guide

## Service Dependency Order

**Correct startup sequence:**
```bash
1. smartassist-gpio-export        # Export GPIO pins
2. smartassist-can-init           # Initialize CAN0
3. smartassist-can-server         # Start CAN daemon
4. smartassist-time-sync.timer    # Enable time sync (hourly)
5. smartassist-camera-init        # Detect cameras
6. smartassist-pipeline           # Main application
7. smartassist-gpio-monitor.timer # Enable IGNITION monitoring
8. smartassist-health-monitor.timer # Enable health checks
```

## Manual Startup

```bash
# Start all services
sudo systemctl start smartassist-gpio-export
sudo systemctl start smartassist-can-init
sudo systemctl start smartassist-can-server
sudo systemctl start smartassist-time-sync.timer
sudo systemctl start smartassist-camera-init
sudo systemctl start smartassist-pipeline
sudo systemctl start smartassist-gpio-monitor.timer
sudo systemctl start smartassist-health-monitor.timer

# Verify all started
systemctl status smartassist-* --no-pager | grep Active
```

## Enable Auto-Start

```bash
# Enable all
sudo systemctl enable smartassist-gpio-export
sudo systemctl enable smartassist-can-init  
sudo systemctl enable smartassist-can-server
sudo systemctl enable smartassist-time-sync.timer
sudo systemctl enable smartassist-camera-init
sudo systemctl enable smartassist-pipeline
sudo systemctl enable smartassist-gpio-monitor.timer
sudo systemctl enable smartassist-health-monitor.timer
```

## Restart Order

```bash
# Restart main pipeline
sudo systemctl restart smartassist-pipeline

# Restart CAN stack
sudo systemctl restart smartassist-can-init
sudo systemctl restart smartassist-can-server
sudo systemctl restart smartassist-pipeline

# Restart everything
sudo systemctl restart smartassist-*
```

## Troubleshooting

**Pipeline won't start:**
```bash
# Check dependencies
systemctl status smartassist-camera-init
systemctl status smartassist-can-server

# View logs
journalctl -u smartassist-pipeline -n 50
```

**CAN issues:**
```bash
# Restart CAN
sudo systemctl restart smartassist-can-init
ip link show can0  # Should be UP
```