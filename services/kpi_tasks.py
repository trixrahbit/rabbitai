import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from config import get_secondary_db_connection

async def kpi_insert(session, kpi_name, category, type_, value):
    """Insert or update KPI values in the database."""
    query = text("""
        SELECT id FROM kpis 
        WHERE name = :name AND category = :category AND type = :type
    """)

    result = await session.execute(query, {"name": kpi_name, "category": category, "type": type_})
    kpi_id = result.scalar()

    if kpi_id is None:
        logging.warning(f"⚠️ KPI '{kpi_name}' not found! Auto-inserting...")
        insert_query = text("""
            INSERT INTO kpis (name, description, category, type)
            VALUES (:name, '', :category, :type);
        """)
        await session.execute(insert_query, {"name": kpi_name, "category": category, "type": type_})
        await session.commit()

        result = await session.execute(query, {"name": kpi_name, "category": category, "type": type_})
        kpi_id = result.scalar()

    if kpi_id is None:
        raise ValueError(f"❌ Failed to create KPI '{kpi_name}' in database!")

    insert_value_query = text("""
        INSERT INTO kpi_values (kpi_id, value, date_recorded)
        VALUES (:kpi_id, :value, GETDATE())
    """)
    await session.execute(insert_value_query, {"kpi_id": kpi_id, "value": value})
    await session.commit()

async def get_start_end_of_week():
    """Returns the start (Sunday) and end (Saturday) of the current week."""
    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday() + 1)
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.date(), end_of_week.date()

async def calculate_utilization():
    """Calculate and update weekly utilization data."""
    start_date, end_date = await get_start_end_of_week()

    async with get_secondary_db_connection() as session:
        try:
            query = text("""
                SELECT 
                    COALESCE(r.email, '') AS emailAddress,
                    t.creatorUserID AS user_id,
                    COALESCE(SUM(t.hoursWorked), 0) AS total_hours
                FROM [dbo].[TimeEntries] t
                LEFT JOIN [dbo].[resources] r ON t.creatorUserID = r.id
                WHERE t.dateWorked BETWEEN :start_date AND :end_date
                GROUP BY r.email, t.creatorUserID
            """)

            result = await session.execute(query, {"start_date": start_date, "end_date": end_date})
            rows = result.fetchall()

            for email, user_id, total_hours in rows:
                utilization_percentage = (total_hours / 40) * 100
                await kpi_insert(session, "Utilization", "Service Desk", "Resource", utilization_percentage)

            await session.commit()
            logging.info("✅ Weekly Utilization Data Updated Successfully!")

        except Exception as e:
            await session.rollback()
            logging.critical(f"🔥 Error calculating utilization: {e}", exc_info=True)
