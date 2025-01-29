def kpi_insert(session, kpi_name, category, type_, result_value):
    kpi_id_query = """
    SELECT id FROM kpis WHERE name = :name AND category = :category AND type = :type;
    """
    kpi_id = session.execute(kpi_id_query, {"name": kpi_name, "category": category, "type": type_}).scalar()

    if kpi_id:
        insert_query = """
        INSERT INTO kpi_values (kpi_id, value, date_recorded)
        VALUES (:kpi_id, :value, GETDATE());
        """
        session.execute(insert_query, {"kpi_id": kpi_id, "value": result_value})
        session.commit()



