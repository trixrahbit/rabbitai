import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from config import engine, get_secondary_db_connection


def kpi_insert(session, kpi_name, category, type_, value):
    kpi_id_query = text("""
        SELECT id FROM kpis 
        WHERE name = :name AND category = :category AND type = :type
    """)

    kpi_id = session.execute(kpi_id_query, {
        "name": kpi_name,
        "category": category,
        "type": type_
    }).scalar()

    if kpi_id is None:
        logging.warning(f"⚠️ KPI '{kpi_name}' not found! Auto-inserting...")

        insert_kpi_query = text("""
            INSERT INTO kpis (name, description, category, type)
            VALUES (:name, '', :category, :type);
        """)

        session.execute(insert_kpi_query, {
            "name": kpi_name,
            "category": category,
            "type": type_
        })
        session.commit()

        # Fetch the new KPI ID
        kpi_id = session.execute(kpi_id_query, {
            "name": kpi_name,
            "category": category,
            "type": type_
        }).scalar()

    if kpi_id is None:
        raise ValueError(f"❌ Failed to create KPI '{kpi_name}' in database!")

    # ✅ Convert tuple to scalar
    if isinstance(value, tuple):
        value = value[0] if value else 0

    insert_value_query = text("""
        INSERT INTO kpi_values (kpi_id, value, date_recorded)
        VALUES (:kpi_id, :value, GETDATE())
    """)

    session.execute(insert_value_query, {"kpi_id": kpi_id, "value": value})
    session.commit()

    session.execute(insert_value_query, {"kpi_id": kpi_id, "value": value})
    session.commit()


def get_start_end_of_week():
    """Get start (Sunday) and end (Saturday) of the current week."""
    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday() + 1)  # Sunday
    end_of_week = start_of_week + timedelta(days=6)  # Saturday
    return start_of_week.date(), end_of_week.date()


def calculate_utilization():
    """Calculate total hours worked per resource per week and update database."""
    start_date, end_date = get_start_end_of_week()
    session = get_secondary_db_connection()  # Use session from SQLAlchemy

    try:
        logging.info(f"🔍 Fetching time entries for {start_date} - {end_date}")

        query = text("""
            SELECT 
                COALESCE(r.email, '') AS emailAddress,  -- Prevent NULL values
                t.assignedResource AS resource_name,
                t.resourceID,
                COALESCE(SUM(t.hoursWorked), 0) AS total_hours  -- Handle NULL case
            FROM dbo.TimeEntries t  -- ✅ Explicit schema reference
            LEFT JOIN dbo.resources r ON t.resourceID = r.id  -- ✅ Ensure correct schema
            WHERE t.dateWorked BETWEEN :start_date AND :end_date
            GROUP BY r.email, t.creatorUserID, t.resourceID
        """)

        result = session.execute(query, {
            "start_date": start_date,
            "end_date": end_date
        }).fetchall()

        if not result:
            logging.warning("⚠️ No time entries found for this week.")
            return

        with session.begin():  # Use session.begin() for transaction safety
            for row in result:
                email, resource_name, resource_id, total_hours = row
                utilization_percentage = (total_hours / 40) * 100  # Based on 40-hour workweek

                upsert_query = text("""
                    MERGE INTO dbo.ResourceUtilization AS target
                    USING (SELECT :resourceID AS resourceID, :weekStartDate AS weekStartDate) AS source
                    ON target.resourceID = source.resourceID AND target.weekStartDate = source.weekStartDate
                    WHEN MATCHED THEN
                        UPDATE SET totalHoursWorked = :totalHours, utilizationPercentage = :utilization, 
                                   emailAddress = :email, assignedResource = :resourceName
                    WHEN NOT MATCHED THEN
                        INSERT (resourceID, assignedResource, emailAddress, weekStartDate, weekEndDate, totalHoursWorked, utilizationPercentage)
                        VALUES (:resourceID, :resourceName, :email, :weekStartDate, :weekEndDate, :totalHours, :utilization);
                """)

                session.execute(upsert_query, {
                    "resourceID": resource_id,
                    "resourceName": resource_name,
                    "email": email,
                    "weekStartDate": start_date,
                    "weekEndDate": end_date,
                    "totalHours": total_hours,
                    "utilization": utilization_percentage
                })

        logging.info("✅ Weekly Utilization Data Updated Successfully!")

    except Exception as e:
        logging.critical(f"🔥 Error calculating utilization: {e}", exc_info=True)

    finally:
        session.close()  # Ensure session is closed





