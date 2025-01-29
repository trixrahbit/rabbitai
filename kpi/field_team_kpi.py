from services.kpi_tasks import kpi_insert


def calculate_endpoints_patched(session):
    query = """
    SELECT COUNT(*) AS patched_endpoints
    FROM endpoints
    WHERE patches_missing = 0;
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "Endpoints Patched", "Field Team", "Team", result)
def calculate_uptime_rolling_30(session):
    query = """
    SELECT AVG(uptime_percentage) AS avg_uptime
    FROM system_uptime
    WHERE recorded_date >= DATEADD(DAY, -30, GETDATE());
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "Uptime Rolling 30 Days", "Field Team", "Team", result)
def calculate_reactive_tickets_per_endpoint(session):
    query = """
    SELECT CAST(COUNT(*) AS FLOAT) / NULLIF((SELECT COUNT(*) FROM endpoints), 0) AS tickets_per_endpoint
    FROM tickets
    WHERE category = 'Support Desk';
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "Reactive Ticket per Endpoint", "Field Team", "Team", result)
