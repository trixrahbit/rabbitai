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

    result = await session.execute(query)
    row = result.fetchone()  # ✅ No need to `await`
    sla_met_count = row[1] if row and row[1] is not None else 0

    await kpi_insert(session, "SLA Met", "Service Desk", "Team", sla_met_count)
    logging.info(f"✅ SLA Met: {sla_met_count}")


async def calculate_ticket_aging():
    async with get_secondary_db_connection() as session:
        query = text("""
            SELECT COUNT(*) AS aging_tickets
            FROM tickets
            WHERE DATEDIFF(DAY, createDate, GETDATE()) > 5
            AND status NOT IN (7, 69, 5, 41)
        """)
        result = await session.execute(query)
        row = result.fetchone()  # ✅ Removed `await`
        aging_tickets = row[0] if row and row[0] is not None else 0

        logging.info(f"✅ Ticket Aging Over 5: {aging_tickets}")


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

    await kpi_insert(session, "Avg Response Time", "Service Desk", "Team", avg_response_time)


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

    await kpi_insert(session, "Avg Resolution Time", "Service Desk", "Team", avg_resolution_time)

async def calculate_response_resolution_time():
    start_date, end_date = await get_start_end_of_week()

    # ✅ Correct usage of async session retrieval
    async with get_secondary_db_connection() as session:
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

            result = await session.execute(query, {
                "start_date": start_date,
                "end_date": end_date
            })
            rows = result.fetchall()  # ✅ No need to `await`

            if not rows:
                logging.warning("⚠️ No ticket data found for this week.")
                return

            for row in rows:
                email, user_id, total_response_time, total_resolution_time, ticket_count = row
                avg_response_time = total_response_time / ticket_count if ticket_count > 0 else 0
                avg_resolution_time = total_resolution_time / ticket_count if ticket_count > 0 else 0

                logging.info(f"✅ Updated Response & Resolution for {email}")

            await session.commit()
            logging.info("✅ Response & Resolution Times Updated Successfully!")

        except Exception as e:
            await session.rollback()
            logging.critical(f"🔥 Error calculating response & resolution time: {e}", exc_info=True)




async def calculate_support_calls(session):
    query = """
    SELECT COUNT(*) AS total_calls
    FROM call_logs
    WHERE direction = 'Inbound'
    AND category = 'Support';
    """
    result = session.execute(query).fetchone()

    await kpi_insert(session, "# of Support Calls", "Service Desk", "Team", result)

async def calculate_csat_rolling_30(session):
    query = """
    SELECT AVG(score) AS csat_score
    FROM csat_responses
    WHERE response_date >= DATEADD(DAY, -30, GETDATE());
    """
    result = session.execute(query).fetchone()

    await kpi_insert(session, "CSAT Rolling 30", "Service Desk", "Team", result)