# tempest-air

Air quality logger for the [Tempest weather dashboard](https://github.com/stetho/tempest-dashboard). Runs on a Raspberry Pi with a Pimoroni Enviro+ hat and PMS5003 particulate matter sensor, polling every 60 seconds and sending readings to the dashboard for display.

## What it measures

The PMS5003 sensor provides:

- **PM1.0, PM2.5, PM10** — particulate matter concentrations in µg/m³
- **Particle counts** — number of particles per 0.1L air across six size bands (0.3µm to 10µm)

The dashboard derives US EPA AQI and UK DAQI (1–10) from these readings.

## Hardware

- Raspberry Pi 3B+ (or similar) with GPIO header
- [Pimoroni Enviro+](https://shop.pimoroni.com/products/enviro-plus) HAT
- PMS5003 particulate matter sensor (connected via ribbon cable to the Enviro+ board)

The Enviro+ also has temperature, light, and gas sensors. This project only uses the PMS5003 — the other sensors are ignored.

## How it works

`logger.py` runs as a systemd service and:

1. Polls the PMS5003 every 60 seconds
2. Stores each reading to a local SQLite database (`air.db`)
3. Every 5 minutes, flushes unsent readings to the dashboard ingest endpoint via HTTP POST
4. Readings that fail to send are buffered locally and retried on the next flush cycle
5. Successfully sent readings older than 7 days are purged from the local buffer

This means the Pi can lose network connectivity for extended periods without losing data.

## Setup

### Prerequisites

```bash
pip3 install pms5003 requests --break-system-packages
```

The Pi also requires UART enabled for the PMS5003. On Pi 3, Bluetooth must be moved to the mini UART to free up the hardware UART for the sensor. Add the following to `/boot/firmware/config.txt`:

```
enable_uart=1
dtoverlay=pi3-miniuart-bt
```

### Installation

```bash
cd ~
git clone https://github.com/stetho/tempest-air.git Projects/tempest-air
```

Edit `tempest-air.service` and set `INGEST_SECRET` to the shared secret configured on the dashboard.

```bash
sudo cp ~/Projects/tempest-air/tempest-air.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tempest-air
sudo systemctl start tempest-air
```

### Updating

```bash
cd ~/Projects/tempest-air
git pull
sudo systemctl restart tempest-air
```

## Configuration

All configuration is via environment variables set in `tempest-air.service`:

| Variable | Default | Description |
|---|---|---|
| `INGEST_URL` | `http://192.168.1.5:5001/api/ingest/air` | Dashboard ingest endpoint |
| `INGEST_SECRET` | *(empty)* | Shared secret — must match `AIR_INGEST_SECRET` on the dashboard |
| `POLL_INTERVAL` | `60` | Seconds between sensor readings |
| `FLUSH_INTERVAL` | `300` | Seconds between flush attempts |
| `FLUSH_BATCH` | `100` | Maximum readings per flush |
| `PURGE_DAYS` | `7` | Days to retain sent readings in the local buffer |

## Monitoring

```bash
# Live logs
sudo journalctl -u tempest-air -f

# Service status
sudo systemctl status tempest-air
```

Normal log output looks like:

```
2026-07-10T15:53:51 INFO Reading 122 stored — PM2.5: 9.0 µg/m³  PM10: 9.0 µg/m³
2026-07-10T15:55:00 INFO Flushing 2 reading(s) to proliant1
2026-07-10T15:55:01 INFO Flushed 2 reading(s) successfully
```

## Dashboard integration

The dashboard side is handled by `air_db.py` in [tempest-dashboard](https://github.com/stetho/tempest-dashboard). The Pi POSTs to `/api/ingest/air` and the dashboard exposes `/api/air/current` and `/api/air/history/24h` for the frontend.
