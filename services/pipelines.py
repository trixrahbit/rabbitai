import logging
import time
from threading import Thread
import asyncio
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

        async for session in get_secondary_db_connection():  # ✅ Correct async handling
            try:
                await calculate_utilization()
                await calculate_response_resolution_time()
                await calculate_sla_met(session)
                await calculate_ticket_aging(session)
                await calculate_avg_response_time(session)
                await calculate_avg_resolution_time(session)

                logging.info("✅ KPI calculations completed successfully!")

            except Exception as e:
                logging.critical(f"🔥 KPI pipeline error: {e}", exc_info=True)

        logging.info("⏳ Sleeping for 30 minutes before next update...")
        await asyncio.sleep(1800)  # ✅ Correct async sleep



async def start_kpi_background_update():
    loop = asyncio.get_running_loop()
    loop.create_task(run_kpi_pipeline())  # ✅ Run as background task

