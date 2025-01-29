from sqlalchemy import text

from services.kpi_tasks import kpi_insert

QUEUE_IDS = [8, 29683537, 29683539, 29683540, 29683555]

def calculate_sla_met(session):
    query = text("""
    SELECT COUNT(*) AS total_tickets,
           SUM(CASE WHEN serviceLevelAgreementHasBeenMet = 1 THEN 1 ELSE 0 END) AS sla_met_count
    FROM tickets
    """)
    result = session.execute(query).fetchone()

    sla_met_count = result[1] if result and result[1] is not None else 0  # ✅ Extract second value

    kpi_insert(session, "SLA Met", "Service Desk", "Team", sla_met_count)


def calculate_csat_rolling_30(session):
    query = """
    SELECT AVG(score) AS csat_score
    FROM csat_responses
    WHERE response_date >= DATEADD(DAY, -30, GETDATE());
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "CSAT Rolling 30", "Service Desk", "Team", result)
def calculate_ticket_aging(session):
    query = text("""  -- ✅ Wrap query in text()
        SELECT COUNT(*) AS aging_tickets
        FROM tickets
        WHERE DATEDIFF(DAY, createDate, GETDATE()) > 5
        AND status NOT IN (7, 69, 5, 41)  -- Assuming these are waiting statuses
    """)

    result = session.execute(query).fetchone()

    aging_tickets = result[0] if result and result[0] is not None else 0  # ✅ Extract scalar

    kpi_insert(session, "Ticket Aging Over 5", "Service Desk", "Team", aging_tickets)


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
    query = text("""
    SELECT 
        AVG(CAST(DATEDIFF(SECOND, createDate, firstResponseDateTime) AS FLOAT)) AS avg_response_time_seconds
    FROM tickets
    WHERE firstResponseDateTime IS NOT NULL
    AND queueID IN :queue_ids;
    """).bindparams(queue_ids=QUEUE_IDS)  # ✅ Correct binding of multiple values

    result = session.execute(query).fetchone()

    if result and result[0] is not None:
        avg_seconds = result[0]
        avg_response_time = f"{int(avg_seconds // 3600):02}:{int((avg_seconds % 3600) // 60):02}"  # Convert to HH:MM format
    else:
        avg_response_time = "00:00"

    kpi_insert(session, "Avg Response Time", "Service Desk", "Team", avg_response_time)


def calculate_avg_resolution_time(session):
    query = text("""
    SELECT 
        AVG(CAST(DATEDIFF(SECOND, createDate, resolvedDateTime) AS FLOAT)) AS avg_resolution_time_seconds
    FROM tickets
    WHERE resolvedDateTime IS NOT NULL
    AND queueID IN :queue_ids;
    """).bindparams(queue_ids=QUEUE_IDS)  # ✅ Correct binding of multiple values

    result = session.execute(query).fetchone()

    if result and result[0] is not None:
        avg_seconds = result[0]
        avg_resolution_time = f"{int(avg_seconds // 3600):02}:{int((avg_seconds % 3600) // 60):02}"  # Convert to HH:MM format
    else:
        avg_resolution_time = "00:00"

    kpi_insert(session, "Avg Resolution Time", "Service Desk", "Team", avg_resolution_time)
