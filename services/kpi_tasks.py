import logging
from datetime import datetime, timedelta

from sqlalchemy import text

from config import engine


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

    with engine.connect() as conn:
        query = text(f"""
            SELECT 
                r.email AS emailAddress,
                t.assignedResource AS resource_name,
                t.resourceID,
                SUM(t.hoursWorked) AS total_hours
            FROM v_Time_Entries t
            LEFT JOIN resources r ON t.resourceID = r.id  -- ✅ Get email
            WHERE t.dateWorked BETWEEN '{start_date}' AND '{end_date}'
            GROUP BY r.email, t.assignedResource, t.resourceID
        """)
        result = conn.execute(query).fetchall()

        if not result:
            print("No time entries found for this week.")
            return

        for row in result:
            email, resource_name, resource_id, total_hours = row
            utilization_percentage = (total_hours / 40) * 100  # Based on 40-hour workweek

            upsert_query = text("""
                MERGE INTO ResourceUtilization AS target
                USING (SELECT :resourceID AS resourceID, :weekStartDate AS weekStartDate) AS source
                ON target.resourceID = source.resourceID AND target.weekStartDate = source.weekStartDate
                WHEN MATCHED THEN
                    UPDATE SET totalHoursWorked = :totalHours, utilizationPercentage = :utilization, emailAddress = :email, assignedResource = :resourceName
                WHEN NOT MATCHED THEN
                    INSERT (resourceID, assignedResource, emailAddress, weekStartDate, weekEndDate, totalHoursWorked, utilizationPercentage)
                    VALUES (:resourceID, :resourceName, :email, :weekStartDate, :weekEndDate, :totalHours, :utilization);
            """)

            conn.execute(upsert_query, {
                "resourceID": resource_id,
                "resourceName": resource_name,
                "email": email,
                "weekStartDate": start_date,
                "weekEndDate": end_date,
                "totalHours": total_hours,
                "utilization": utilization_percentage
            })

        conn.commit()
        print("✅ Weekly Utilization Data Updated with Emails!")





