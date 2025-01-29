import logging
import time
from threading import Thread
from typing import List, Dict
from datetime import datetime, timedelta
import httpx
import pandas as pd
from fastapi import HTTPException
from config import logger, APP_SECRET, get_secondary_db_connection, secondary_engine
from models import DeviceData, TicketData
from datetime import datetime
from typing import List, Dict
import logging
from models import DeviceData
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from config import engine



# Set up a session factory for database interactions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=secondary_engine)
def generate_analytics(device_data: List[DeviceData]) -> Dict[str, dict]:
    now = datetime.utcnow()

    # Define full match sets
    FULL_MATCH_SETS = [
        {"Datto_RMM", "Huntress", "Workstation_AD", "ImmyBot", "CyberCNS", "ITGlue"},
        {"Datto_RMM", "Huntress", "Server_AD", "ImmyBot", "CyberCNS", "ITGlue"},
    ]

    analytics = {
        "counts": {
            "total_devices": len(device_data),
            "manufacturers": {},  # Dictionary to track device count per manufacturer
            "inactive_devices": 0,
            "no_antivirus": 0,
            "no_last_reboot": 0,
        },
        "integration_matches": {
            "full_matches": [],
            "partial_matches": [],
            "single_integrations": []
        },
        "issues": {
            "no_antivirus_installed": [],
            "missing_defender_on_workstation": [],
            "missing_sentinel_one_on_server": [],
            "not_seen_recently": [],
            "reboot_required": [],
            "expired_warranty": []
        },
        "integrations": {key: 0 for key in [
            "Datto_RMM", "Huntress", "Workstation_AD", "Server_AD",
            "ImmyBot", "Auvik", "CyberCNS", "ITGlue"
        ]}
    }

    for device in device_data:
        device_name = device.device_name or "Unnamed Device"
        manufacturer = device.manufacturer_name

        # Count manufacturers
        if manufacturer and manufacturer != "N/A":
            analytics["counts"]["manufacturers"][manufacturer] = (
                    analytics["counts"]["manufacturers"].get(manufacturer, 0) + 1
            )

        device_integrations = []

        for integration in [
            {"name": "Datto_RMM", "id_attr": "datto_id"},
            {"name": "Huntress", "id_attr": "huntress_id"},
            {"name": "Workstation_AD", "id_attr": "Workstation_AD"},
            {"name": "Server_AD", "id_attr": "Server_AD"},
            {"name": "ImmyBot", "id_attr": "immy_id"},
            {"name": "Auvik", "id_attr": "auvik_id"},
            {"name": "CyberCNS", "id_attr": "cybercns_id"},
            {"name": "ITGlue", "id_attr": "itglue_id"}
        ]:
            integration_name = integration["name"]

            if getattr(device, integration_name, False):
                analytics["integrations"][integration_name] += 1
                device_integrations.append(integration_name)

        # Convert device integrations to a set for comparison
        device_integration_set = set(device_integrations)

        # Determine match type
        if any(device_integration_set == full_match for full_match in FULL_MATCH_SETS):
            analytics["integration_matches"]["full_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations
            })
        elif len(device_integrations) == 1:
            analytics["integration_matches"]["single_integrations"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations
            })
        elif len(device_integrations) > 1:
            analytics["integration_matches"]["partial_matches"].append({
                "device_name": device_name,
                "matched_integrations": device_integrations
            })

        # Track inactive devices
        if device.Inactive_Computer:
            analytics["counts"]["inactive_devices"] += 1
            analytics["issues"]["not_seen_recently"].append({"device_name": device_name})

    return analytics

async def handle_mytickets(data: str) -> dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("http://127.0.0.1:8001/tickets", json={"data": data})
            response.raise_for_status()
            tickets_result = response.json()
            return {"response": f"Processed {len(tickets_result.get('tickets', []))} tickets"}
        except httpx.HTTPStatusError as e:
            return {"response": f"HTTP error: {e.response.status_code} - {str(e)}"}

def count_open_tickets(tickets: List[TicketData]) -> int:
    return sum(1 for ticket in tickets if ticket.status is not None and ticket.status != 5)


# This section is for getting contracts, units, pricing, ticket counts, aggrevating and saving the results to a db on a timer so its always up to date


def update_contract_summary():
    """Ensures the ContractSummary table stays up to date."""
    session = get_secondary_db_connection()
    try:
        merge_query = text("""
            MERGE INTO dbo.ContractSummary AS target
            USING (
                SELECT 
                    c.id AS ContractID,
                    c.contractName AS ContractName,
                    c.companyID AS CompanyID,
                    cl.companyName AS CompanyName,
                    cs.id AS ServiceID,
                    COALESCE(cs.internalDescription, 'Unknown Service') AS ServiceName,
                    cu.startDate AS StartDate,
                    cu.endDate AS EndDate,
                    COALESCE(cu.units, 0) AS Units,
                    COALESCE(cu.internalCurrencyPrice, 0) AS UnitPrice,
                    COALESCE(cu.internalCurrencyPrice, 0) AS Cost,
                    c.billingPreference AS BillingPreference,
                    (COALESCE(cu.units, 0) * COALESCE(cu.internalCurrencyPrice, 0)) AS TotalRevenue,
                    (COALESCE(cu.units, 0) * COALESCE(cu.internalCurrencyPrice, 0)) AS TotalCost
                FROM dbo.Contracts c
                JOIN dbo.Clients cl ON c.companyID = cl.id
                JOIN dbo.Contract_Services cs ON c.id = cs.contractID
                JOIN dbo.ContractUnits cu ON cs.id = cu.serviceID
                WHERE cs.internalDescription IS NOT NULL
            ) AS source
            ON target.ContractID = source.ContractID AND target.ServiceID = source.ServiceID
            WHEN MATCHED THEN
                UPDATE SET 
                    ContractName = source.ContractName,
                    CompanyID = source.CompanyID,
                    CompanyName = source.CompanyName,
                    ServiceName = source.ServiceName,
                    StartDate = source.StartDate,
                    EndDate = source.EndDate,
                    Units = source.Units,
                    UnitPrice = source.UnitPrice,
                    Cost = source.Cost,
                    BillingPreference = source.BillingPreference,
                    TotalRevenue = source.TotalRevenue,
                    TotalCost = source.TotalCost,
                    LastUpdated = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (
                    ContractID, ContractName, CompanyID, CompanyName, ServiceID, ServiceName, StartDate, EndDate, Units, 
                    UnitPrice, Cost, BillingPreference, TotalRevenue, TotalCost
                )
                VALUES (
                    source.ContractID, source.ContractName, source.CompanyID, source.CompanyName, source.ServiceID, 
                    source.ServiceName, source.StartDate, source.EndDate, source.Units, source.UnitPrice, 
                    source.Cost, source.BillingPreference, source.TotalRevenue, source.TotalCost
                );
        """)

        session.execute(merge_query)
        session.commit()
        logger.info("✅ ContractSummary table updated successfully.")
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Error updating ContractSummary table: {e}")
    finally:
        session.close()


# ✅ Fetch Contract Data & Ticket Counts
def fetch_data():
    """Fetch contract summary data and ticket counts from Azure SQL."""
    conn = get_secondary_db_connection()

    contracts_query = """
    SELECT 
        ContractID, ContractName, CompanyID AS ClientID, CompanyName, ServiceID, ServiceName,
        StartDate, EndDate, Units, UnitPrice, Cost, BillingPreference, TotalRevenue, TotalCost
    FROM dbo.ContractSummary
    """

    tickets_query = """
    SELECT 
        t.companyID AS ClientID,
        cu.ContractID,
        YEAR(t.createDate) AS TicketYear, 
        MONTH(t.createDate) AS TicketMonth, 
        COUNT(t.id) AS TicketCount
    FROM dbo.tickets t
    JOIN dbo.ContractSummary cu 
        ON t.companyID = cu.CompanyID 
        AND t.createDate BETWEEN cu.StartDate AND cu.EndDate
    GROUP BY t.companyID, cu.ContractID, YEAR(t.createDate), MONTH(t.createDate)
    """

    contracts_df = pd.read_sql(contracts_query, conn)
    tickets_df = pd.read_sql(tickets_query, conn)

    logger.info(f"🔍 Contracts Columns: {contracts_df.dtypes}")
    logger.info(f"🔍 Tickets Columns: {tickets_df.dtypes}")

    # ✅ Ensure ContractID & ClientID match formats
    contracts_df["ContractID"] = contracts_df["ContractID"].astype(str)
    contracts_df["ClientID"] = contracts_df["ClientID"].astype(str)

    tickets_df["ContractID"] = tickets_df["ContractID"].astype(str)
    tickets_df["ClientID"] = tickets_df["ClientID"].astype(str)

    conn.close()
    return contracts_df, tickets_df


# ✅ Calculate Monthly Revenue Using ContractSummary
def calculate_monthly_revenue(contracts_df):
    """Generate monthly revenue per client per contract using ContractSummary data."""
    all_rows = []

    logger.info(f"🔍 Processing {len(contracts_df)} contracts for revenue calculation.")

    for _, row in contracts_df.iterrows():
        start_date = pd.to_datetime(row['StartDate'])
        end_date = pd.to_datetime(row['EndDate']) if pd.notnull(row['EndDate']) else pd.Timestamp.now()

        total_revenue = row['TotalRevenue'] if pd.notnull(row['TotalRevenue']) else 0
        total_cost = row['TotalCost'] if pd.notnull(row['TotalCost']) else 0

        current_date = start_date
        while current_date <= end_date:
            all_rows.append([
                row['ClientID'], row['CompanyName'], row['ContractID'], row['ContractName'],
                row['ServiceID'], row['ServiceName'], current_date.strftime("%Y-%m-01"),
                total_revenue, total_cost
            ])
            current_date += pd.DateOffset(months=1)

    revenue_df = pd.DataFrame(all_rows, columns=[
        "ClientID", "CompanyName", "ContractID", "ContractName", "ServiceID", "ServiceName",
        "RevenueMonth", "MonthlyRevenue", "MonthlyCost"
    ])

    logger.info(f"💰 Monthly Revenue Calculated: {revenue_df.shape}")
    return revenue_df


# ✅ Merge Revenue Data with Ticket Counts
def merge_with_tickets(revenue_df, tickets_df):
    """Merge ticket counts with revenue data based on contract start and end dates."""
    tickets_df["RevenueMonth"] = tickets_df.apply(lambda x: f"{x['TicketYear']}-{x['TicketMonth']:02d}-01", axis=1)
    tickets_df.drop(columns=["TicketYear", "TicketMonth"], inplace=True)

    logger.info(f"🔍 Before Merging: RevenueDF={revenue_df.shape}, TicketsDF={tickets_df.shape}")

    final_df = revenue_df.merge(tickets_df, on=["ClientID", "ContractID", "RevenueMonth"], how="left").fillna(0)
    final_df.rename(columns={"TicketCount": "TicketsCreated"}, inplace=True)

    logger.info(f"✅ Merged Data Shape: {final_df.shape}")
    return final_df


# ✅ Store Data in SQL
def store_to_db(final_df):
    """Efficiently stores results in Azure SQL using SQLAlchemy."""
    session = get_secondary_db_connection()
    try:
        insert_query = text("""
            MERGE INTO dbo.ClientMonthlySummary AS target
            USING (VALUES (:ClientID, :ClientName, :ContractID, :ContractName, 
                           :ServiceID, :ServiceName, :RevenueMonth, :MonthlyRevenue, :MonthlyCost, :TicketsCreated))
            AS source (ClientID, ClientName, ContractID, ContractName, 
                       ServiceID, ServiceName, RevenueMonth, MonthlyRevenue, MonthlyCost, TicketsCreated)
            ON target.ClientID = source.ClientID AND target.ContractID = source.ContractID AND target.RevenueMonth = source.RevenueMonth
            WHEN MATCHED THEN
                UPDATE SET MonthlyRevenue = source.MonthlyRevenue, MonthlyCost = source.MonthlyCost, 
                           TicketsCreated = source.TicketsCreated, LastUpdated = GETDATE()
            WHEN NOT MATCHED THEN 
                INSERT (ClientID, ClientName, ContractID, ContractName, ServiceID, ServiceName, 
                        RevenueMonth, MonthlyRevenue, MonthlyCost, TicketsCreated)
                VALUES (source.ClientID, source.ClientName, source.ContractID, source.ContractName, 
                        source.ServiceID, source.ServiceName, source.RevenueMonth, source.MonthlyRevenue, 
                        source.MonthlyCost, source.TicketsCreated);
        """)

        session.execute(insert_query, final_df.to_dict(orient='records'))
        session.commit()
        logger.info("✅ Data updated successfully.")
    except Exception as e:
        session.rollback()
        logger.error(f"❌ Error inserting data: {e}")
    finally:
        session.close()


# ✅ Pipeline Runner (Runs Every 30 Mins)
def run_pipeline():
    while True:
        logging.info("🔄 Updating Contract Summary Table...")
        update_contract_summary()  # ✅ Ensure ContractSummary is up to date before fetching data.

        logging.info("🚀 Fetching Data...")
        contracts_df, tickets_df = fetch_data()

        if contracts_df.empty or tickets_df.empty:
            logging.warning("⚠️ Skipping iteration due to missing data.")
            time.sleep(1800)
            continue

        logging.info("💰 Calculating Monthly Revenue...")
        revenue_df = calculate_monthly_revenue(contracts_df)

        logging.info("📊 Merging with Ticket Data...")
        final_df = merge_with_tickets(revenue_df, tickets_df)

        logging.info("💾 Storing Data in Database...")
        store_to_db(final_df)

        logging.info("⏳ Sleeping for 30 minutes before next update...")
        time.sleep(1800)

# ✅ Run Pipeline in Background
def start_background_update():
    thread = Thread(target=run_pipeline, daemon=True)
    thread.start()

