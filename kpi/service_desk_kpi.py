import logging

from sqlalchemy import text, bindparam

from config import get_secondary_db_connection
from services.kpi_tasks import kpi_insert, get_start_end_of_week

QUEUE_IDS = [8, 29683537, 29683539, 29683540, 29683555]

async def calculate_sla_met(session):
    query = text("""
    SELECT COUNT(*) AS total_tickets,
           SUM(CASE WHEN serviceLevelAgreementHasBeenMet = 1 THEN 1 ELSE 0 END) AS sla_met_count
    FROM tickets
    """)
    result = session.execute(query).fetchone()

    sla_met_count = result[1] if result and result[1] is not None else 0  # ✅ Extract second value

    kpi_insert(session, "SLA Met", "Service Desk", "Team", sla_met_count)



async def calculate_ticket_aging(session):
    query = text("""  -- ✅ Wrap query in text()
        SELECT COUNT(*) AS aging_tickets
        FROM tickets
        WHERE DATEDIFF(DAY, createDate, GETDATE()) > 5
        AND status NOT IN (7, 69, 5, 41)  -- Assuming these are waiting statuses
    """)

    result = session.execute(query).fetchone()

    aging_tickets = result[0] if result and result[0] is not None else 0  # ✅ Extract scalar

    kpi_insert(session, "Ticket Aging Over 5", "Service Desk", "Team", aging_tickets)


async def calculate_avg_response_time(session):
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


async def calculate_avg_resolution_time(session):
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

async def calculate_response_resolution_time():
    """Calculates response & resolution times per resource per week and updates the database."""
    start_date, end_date = get_start_end_of_week()
    session = get_secondary_db_connection()

    try:
        logging.info(f"🔍 Fetching ticket data for {start_date} - {end_date}")

        query = text("""
            SELECT 
                COALESCE(r.email, '') AS emailAddress,
                COALESCE(t.assignedResourceID, 0) AS user_id,
                COALESCE(SUM(DATEDIFF(MINUTE, t.createDate, t.firstResponseDateTime)), 0) AS total_response_time,
                COALESCE(SUM(DATEDIFF(MINUTE, t.createDate, t.resolvedDateTime)), 0) AS total_resolution_time,
                COUNT(t.id) AS ticket_count
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
            logging.warning("⚠️ No ticket data found for this week.")
            return

        # ✅ Process each resource's response & resolution time
        for row in result:
            email, user_id, total_response_time, total_resolution_time, ticket_count = row

            # ✅ Ensure `resourceID` is never NULL
            if user_id is None:
                logging.warning(f"⚠️ Skipping entry due to missing resource ID. Email: {email}")
                continue

            avg_response_time = total_response_time / ticket_count if ticket_count > 0 else 0
            avg_resolution_time = total_resolution_time / ticket_count if ticket_count > 0 else 0

            upsert_query = text("""
                MERGE INTO dbo.ResourceResponseResolution AS target
                USING (SELECT :user_id AS resourceID, :weekStartDate AS weekStartDate) AS source
                ON target.resourceID = source.resourceID AND target.weekStartDate = source.weekStartDate
                WHEN MATCHED THEN
                    UPDATE SET totalResponseTime = :totalResponse, totalResolutionTime = :totalResolution, 
                               avgResponseTime = :avgResponse, avgResolutionTime = :avgResolution,
                               ticketCount = :ticketCount, emailAddress = :email
                WHEN NOT MATCHED THEN
                    INSERT (resourceID, emailAddress, weekStartDate, weekEndDate, 
                            totalResponseTime, totalResolutionTime, avgResponseTime, avgResolutionTime, ticketCount)
                    VALUES (:user_id, :email, :weekStartDate, :weekEndDate, 
                            :totalResponse, :totalResolution, :avgResponse, :avgResolution, :ticketCount);
            """)

            session.execute(upsert_query, {
                "user_id": user_id,
                "email": email,
                "weekStartDate": start_date,
                "weekEndDate": end_date,
                "totalResponse": total_response_time,
                "totalResolution": total_resolution_time,
                "avgResponse": avg_response_time,
                "avgResolution": avg_resolution_time,
                "ticketCount": ticket_count
            })

        session.commit()  # ✅ Ensure data is committed
        logging.info("✅ Response & Resolution Times Updated Successfully!")

    except Exception as e:
        session.rollback()  # ✅ Ensure rollback on failure
        logging.critical(f"🔥 Error calculating response & resolution time: {e}", exc_info=True)

    finally:
        session.close()  # ✅ Ensure connection is closed


async def calculate_support_calls(session):
    query = """
    SELECT COUNT(*) AS total_calls
    FROM call_logs
    WHERE direction = 'Inbound'
    AND category = 'Support';
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "# of Support Calls", "Service Desk", "Team", result)

async def calculate_csat_rolling_30(session):
    query = """
    SELECT AVG(score) AS csat_score
    FROM csat_responses
    WHERE response_date >= DATEADD(DAY, -30, GETDATE());
    """
    result = session.execute(query).fetchone()

    kpi_insert(session, "CSAT Rolling 30", "Service Desk", "Team", result)