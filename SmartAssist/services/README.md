# Services Architecture

## Service List

| Service | Type | Purpose |
|---------|------|---------|
| gpio-export | oneshot | Export GPIO pins |
| can-init | oneshot | Init CAN0 250Kbps |
| can-server | daemon | CAN communication |
| time-sync | oneshot (hourly) | Sync time from GPS |
| camera-init | oneshot | Detect cameras |
| pipeline | daemon | Main AI app |
| gpio-monitor | timer (5s) | Monitor IGNITION |
| health-monitor | timer (30s) | Check services |

## Dependencies

```
gpio-export → gpio-monitor
can-init → can-server → time-sync
can-init → pipeline
camera-init → pipeline
```

## Monitoring

```
# Check all
systemctl status smartassist-*

# View health
cat /var/lib/smartassist/service_status.json

# Logs
journalctl -t smartassist-*
```

## Individual Service Docs

See each service's README:
- `gpio-export/README.md`
- `gpio-monitor/README.md`
- `can-init/README.md`
- `time-sync/README.md`
- `can-server/README.md`
- `health-monitor/README.md`