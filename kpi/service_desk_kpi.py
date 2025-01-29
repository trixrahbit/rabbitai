from sqlalchemy import text

from services.kpi_tasks import kpi_insert


def calculate_sla_met(session):
    query = text("""
    SELECT COUNT(*) AS total_tickets,
           SUM(CASE WHEN sla_met = 1 THEN 1 ELSE 0 END) AS sla_met_count
    FROM tickets
    """)
    result = session.execute(query).fetchone()
def calculate_csat_rolling_30(session):
    query = """
    SELECT AVG(score) AS csat_score
    FROM csat_responses
    WHERE response_date >= DATEADD(DAY, -30, GETDATE());
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "CSAT Rolling 30", "Service Desk", "Team", result)
def calculate_ticket_aging(session):
    query = """
    SELECT COUNT(*) AS aged_tickets
    FROM tickets
    WHERE DATEDIFF(DAY, created_date, GETDATE()) > 5
    AND status NOT IN ('Waiting Client', 'Closed');
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "Ticket Aging Over 5", "Service Desk", "Team", result)
def calculate_support_calls(session):
    query = """
    SELECT COUNT(*) AS total_calls
    FROM call_logs
    WHERE direction = 'Inbound'
    AND category = 'Support';
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "# of Support Calls", "Service Desk", "Team", result)
def calculate_avg_response_time(session):
    query = """
    SELECT AVG(DATEDIFF(MINUTE, created_date, first_response_date)) AS avg_response_time
    FROM tickets
    WHERE first_response_date IS NOT NULL;
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "Avg Response Time", "Service Desk", "Team", result)
def calculate_avg_resolution_time(session):
    query = """
    SELECT AVG(DATEDIFF(HOUR, created_date, resolution_date)) AS avg_resolution_time
    FROM tickets
    WHERE resolution_date IS NOT NULL;
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "Avg Resolution Time", "Service Desk", "Team", result)