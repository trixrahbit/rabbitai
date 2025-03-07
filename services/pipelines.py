import logging
import time
from threading import Thread

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import SECONDARY_DATABASE_URL, get_secondary_db_connection
from kpi.field_team_kpi import calculate_endpoints_patched, calculate_uptime_rolling_30, \
    calculate_reactive_tickets_per_endpoint
from kpi.service_desk_kpi import calculate_sla_met, calculate_csat_rolling_30, calculate_ticket_aging, \
    calculate_support_calls, calculate_avg_response_time, calculate_avg_resolution_time, \
    calculate_response_resolution_time
from services.kpi_tasks import calculate_utilization

engine = create_engine(SECONDARY_DATABASE_URL)
Session = sessionmaker(bind=engine)

async def run_kpi_pipeline():
    """Continuously runs KPI calculations every 30 minutes."""
    while True:
        logging.info("🚀 Running KPI calculations...")
        session = get_secondary_db_connection()  # ✅ Get a new session per cycle

        try:
            calculate_utilization()
            calculate_response_resolution_time()
            calculate_sla_met(session)
            # calculate_csat_rolling_30(session)
            calculate_ticket_aging(session)
            # calculate_support_calls(session)
            calculate_avg_response_time(session)
            calculate_avg_resolution_time(session)
            # calculate_endpoints_patched(session)
            # calculate_uptime_rolling_30(session)
            # calculate_reactive_tickets_per_endpoint(session)

            logging.info("✅ KPI calculations completed successfully!")

        except Exception as e:
            logging.critical(f"🔥 KPI pipeline error: {e}", exc_info=True)

        finally:
            session.close()  # ✅ Always close session after each run

        logging.info("⏳ Sleeping for 30 minutes before next update...")
        time.sleep(1800)  # ✅ Sleep before restarting the loop


async def start_kpi_background_update():
    thread = Thread(target=run_kpi_pipeline, daemon=True)
    thread.start()