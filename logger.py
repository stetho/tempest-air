"""
tempest-air logger
Polls the PMS5003 sensor every 60 seconds, stores to local SQLite,
and flushes buffered readings to proliant1 when network is available.
"""

import os
import time
import logging
import requests
from datetime import datetime, timezone
from pms5003 import PMS5003, ReadTimeoutError

import db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLL_INTERVAL   = int(os.getenv("POLL_INTERVAL", "60"))       # seconds
FLUSH_INTERVAL  = int(os.getenv("FLUSH_INTERVAL", "300"))     # seconds (5 min)
INGEST_URL      = os.getenv("INGEST_URL", "http://192.168.1.5:5001/api/ingest/air")
INGEST_SECRET   = os.getenv("INGEST_SECRET", "")
FLUSH_BATCH     = int(os.getenv("FLUSH_BATCH", "100"))         # readings per flush
PURGE_DAYS      = int(os.getenv("PURGE_DAYS", "7"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensor
# ---------------------------------------------------------------------------

def read_sensor(pms: PMS5003) -> dict | None:
    """Read PMS5003 and return a dict, or None on failure."""
    try:
        data = pms.read()
        return {
            "timestamp":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pm1_0":       data.pm_ug_per_m3(1.0),
            "pm2_5":       data.pm_ug_per_m3(2.5),
            "pm10":        data.pm_ug_per_m3(10),
            "p03um":       data.pm_per_1l_air(0.3),
            "p05um":       data.pm_per_1l_air(0.5),
            "p10um":       data.pm_per_1l_air(1.0),
            "p25um":       data.pm_per_1l_air(2.5),
            "p50um":       data.pm_per_1l_air(5.0),
            "p100um":      data.pm_per_1l_air(10),
        }
    except ReadTimeoutError:
        logger.warning("PMS5003 read timeout")
        return None
    except Exception as e:
        logger.error("Sensor read error: %s", e)
        return None

# ---------------------------------------------------------------------------
# Flush
# ---------------------------------------------------------------------------

def flush_to_proliant() -> None:
    """Send unsent readings to proliant1. Marks sent on success."""
    unsent = db.get_unsent(limit=FLUSH_BATCH)
    if not unsent:
        return

    logger.info("Flushing %d reading(s) to proliant1", len(unsent))

    try:
        response = requests.post(
            INGEST_URL,
            json={"readings": unsent},
            headers={"X-Air-Secret": INGEST_SECRET},
            timeout=15,
        )
        if response.status_code == 200:
            ids = [r["id"] for r in unsent]
            db.mark_sent(ids)
            logger.info("Flushed %d reading(s) successfully", len(ids))
        else:
            logger.warning(
                "Ingest endpoint returned %d: %s",
                response.status_code,
                response.text[:200],
            )
    except requests.exceptions.ConnectionError:
        logger.warning("proliant1 unreachable — readings buffered (%d unsent)", db.count_unsent())
    except requests.exceptions.Timeout:
        logger.warning("Ingest request timed out")
    except Exception as e:
        logger.error("Flush error: %s", e)

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    if not INGEST_SECRET:
        logger.warning("INGEST_SECRET is not set — ingest endpoint will reject requests")

    db.init_db()

    pms = PMS5003()
    logger.info("PMS5003 initialised")

    last_flush = 0.0

    try:
        while True:
            loop_start = time.monotonic()

            # Poll sensor
            reading = read_sensor(pms)
            if reading:
                row_id = db.insert_reading(reading)
                logger.info(
                    "Reading %d stored — PM2.5: %.1f µg/m³  PM10: %.1f µg/m³",
                    row_id, reading["pm2_5"], reading["pm10"],
                )
            else:
                logger.warning("Skipping store — no valid reading")

            # Flush on interval
            now = time.monotonic()
            if now - last_flush >= FLUSH_INTERVAL:
                flush_to_proliant()
                purged = db.purge_old(PURGE_DAYS)
                if purged:
                    logger.info("Purged %d old sent reading(s)", purged)
                last_flush = time.monotonic()

            # Sleep for remainder of interval
            elapsed = time.monotonic() - loop_start
            sleep_for = max(0.0, POLL_INTERVAL - elapsed)
            time.sleep(sleep_for)

    except KeyboardInterrupt:
        logger.info("Shutting down")
    except Exception as e:
        logger.error("Fatal error: %s", e)
        raise


if __name__ == "__main__":
    main()
