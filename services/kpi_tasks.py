import logging

from sqlalchemy import text


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

    insert_value_query = text("""
        INSERT INTO kpi_values (kpi_id, value, date_recorded)
        VALUES (:kpi_id, :value, GETDATE())
    """)

    session.execute(insert_value_query, {"kpi_id": kpi_id, "value": value})
    session.commit()





