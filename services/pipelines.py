from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import SECONDARY_DATABASE_URL
from kpi.field_team_kpi import calculate_endpoints_patched, calculate_uptime_rolling_30, \
    calculate_reactive_tickets_per_endpoint
from kpi.service_desk_kpi import calculate_sla_met, calculate_csat_rolling_30, calculate_ticket_aging, \
    calculate_support_calls, calculate_avg_response_time, calculate_avg_resolution_time

engine = create_engine(SECONDARY_DATABASE_URL)
Session = sessionmaker(bind=engine)

def run_kpi_pipeline():
    session = Session()
    try:
        calculate_sla_met(session)
        # calculate_csat_rolling_30(session)
        calculate_ticket_aging(session)
        # calculate_support_calls(session)
        calculate_avg_response_time(session)
        calculate_avg_resolution_time(session)
        # calculate_endpoints_patched(session)
        # calculate_uptime_rolling_30(session)
        # calculate_reactive_tickets_per_endpoint(session)
    finally:
        session.close()