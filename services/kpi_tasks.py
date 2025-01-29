from sqlalchemy import text


def kpi_insert(session, kpi_name, category, type_, value):
    kpi_id_query = text("""  -- ✅ Wrap query in text()
        SELECT id FROM kpis WHERE name = :name AND category = :category AND type = :type
    """)

    kpi_id = session.execute(kpi_id_query, {"name": kpi_name, "category": category, "type": type_}).scalar()

    if not kpi_id:
        insert_kpi_query = text("""
            INSERT INTO kpis (name, category, type) 
            VALUES (:name, :category, :type)
        """)
        session.execute(insert_kpi_query, {"name": kpi_name, "category": category, "type": type_})
        session.commit()  # ✅ Commit after insert
        kpi_id = session.execute(kpi_id_query, {"name": kpi_name, "category": category, "type": type_}).scalar()

    insert_value_query = text("""
        INSERT INTO kpi_values (kpi_id, value, date_recorded)
        VALUES (:kpi_id, :value, GETDATE())
    """)

    session.execute(insert_value_query, {"kpi_id": kpi_id, "value": value})
    session.commit()



