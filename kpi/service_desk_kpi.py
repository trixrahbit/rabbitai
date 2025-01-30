import logging

from sqlalchemy import text, bindparam

from config import get_secondary_db_connection
from services.kpi_tasks import kpi_insert, get_start_end_of_week

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


def calculate_avg_response_time(session):
    query = text("""
    SELECT 
        AVG(CAST(DATEDIFF(MINUTE, createDate, firstResponseDateTime) AS FLOAT)) AS avg_response_time_minutes
    FROM tickets
    WHERE firstResponseDateTime IS NOT NULL
    AND queueID IN :queue_ids;
    """).bindparams(bindparam("queue_ids", expanding=True))

    result = session.execute(query, {"queue_ids": QUEUE_IDS}).fetchone()

    avg_response_time = int(result[0]) if result and result[0] is not None else 0  # ✅ Store minutes as an integer

    kpi_insert(session, "Avg Response Time", "Service Desk", "Team", avg_response_time)


def calculate_avg_resolution_time(session):
    query = text("""
    SELECT 
        AVG(CAST(DATEDIFF(MINUTE, createDate, resolvedDateTime) AS FLOAT)) AS avg_resolution_time_minutes
    FROM tickets
    WHERE resolvedDateTime IS NOT NULL
    AND queueID IN :queue_ids;
    """).bindparams(bindparam("queue_ids", expanding=True))

    result = session.execute(query, {"queue_ids": QUEUE_IDS}).fetchone()

    avg_resolution_time = int(result[0]) if result and result[0] is not None else 0  # ✅ Store minutes as an integer

    kpi_insert(session, "Avg Resolution Time", "Service Desk", "Team", avg_resolution_time)

def calculate_response_resolution_time():
    """Calculate response and resolution times per resource per week and update database."""
    start_date, end_date = get_start_end_of_week()
    session = get_secondary_db_connection()  # Get SQLAlchemy session

    try:
        logging.info(f"🔍 Fetching ticket data for {start_date} - {end_date}")

        query = text("""
            SELECT 
                r.email AS emailAddress,
                t.assignedResourceID,
                COUNT(t.id) AS ticketCount,
                SUM(DATEDIFF(SECOND, t.createDate, t.firstResponseDateTime)) / 3600.0 AS totalResponseTime,  -- Convert seconds to hours
                SUM(DATEDIFF(SECOND, t.createDate, t.resolvedDateTime)) / 3600.0 AS totalResolutionTime  -- Convert seconds to hours
            FROM dbo.Tickets t
            LEFT JOIN dbo.resources r ON t.assignedResourceID = r.id
            WHERE t.createDate BETWEEN :start_date AND :end_date
            GROUP BY r.email, t.assignedResourceID
        """)

        result = session.execute(query, {
            "start_date": start_date,
            "end_date": end_date
        }).fetchall()

        if not result:
            logging.warning("⚠️ No tickets found for this week.")
            return

        with session.begin():  # Use transaction
            for row in result:
                email, resource_id, ticket_count, total_response_time, total_resolution_time = row
                avg_response_time = total_response_time / ticket_count if ticket_count else 0
                avg_resolution_time = total_resolution_time / ticket_count if ticket_count else 0

                upsert_query = text("""
                    MERGE INTO dbo.ResourceResponseResolution AS target
                    USING (SELECT :resourceID AS resourceID, :weekStartDate AS weekStartDate) AS source
                    ON target.resourceID = source.resourceID AND target.weekStartDate = source.weekStartDate
                    WHEN MATCHED THEN
                        UPDATE SET totalResponseTime = :totalResponseTime, totalResolutionTime = :totalResolutionTime,
                                   avgResponseTime = :avgResponseTime, avgResolutionTime = :avgResolutionTime,
                                   ticketCount = :ticketCount, emailAddress = :email
                    WHEN NOT MATCHED THEN
                        INSERT (resourceID, emailAddress, weekStartDate, weekEndDate, totalResponseTime, totalResolutionTime, 
                                avgResponseTime, avgResolutionTime, ticketCount)
                        VALUES (:resourceID, :email, :weekStartDate, :weekEndDate, :totalResponseTime, :totalResolutionTime,
                                :avgResponseTime, :avgResolutionTime, :ticketCount);
                """)

                session.execute(upsert_query, {
                    "resourceID": resource_id,
                    "email": email,
                    "weekStartDate": start_date,
                    "weekEndDate": end_date,
                    "totalResponseTime": total_response_time,
                    "totalResolutionTime": total_resolution_time,
                    "avgResponseTime": avg_response_time,
                    "avgResolutionTime": avg_resolution_time,
                    "ticketCount": ticket_count
                })

        logging.info("✅ Weekly Response & Resolution Time Data Updated Successfully!")

    except Exception as e:
        logging.critical(f"🔥 Error calculating response & resolution time: {e}", exc_info=True)

    finally:
        session.close()  # Close session






def calculate_support_calls(session):
    query = """
    SELECT COUNT(*) AS total_calls
    FROM call_logs
    WHERE direction = 'Inbound'
    AND category = 'Support';
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "# of Support Calls", "Service Desk", "Team", result)

def calculate_csat_rolling_30(session):
    query = """
    SELECT AVG(score) AS csat_score
    FROM csat_responses
    WHERE response_date >= DATEADD(DAY, -30, GETDATE());
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "CSAT Rolling 30", "Service Desk", "Team", result)