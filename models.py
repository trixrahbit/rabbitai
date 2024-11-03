from pydantic import BaseModel, Field
from typing import Optional,List, Dict

class DataAggregationRequest(BaseModel):
    data: list[dict]

class EmailRequest(BaseModel):
    email: str


class DataAggregationRequest(BaseModel):
    data: List[Dict[str, str]] = Field(..., description="List of records to aggregate and generate PDF from")
    # Example of the expected structure:
    # [
    #     {"name": "Alice", "age": "30", "occupation": "Engineer"},
    #     {"name": "Bob", "age": "25", "occupation": "Designer"}
    # ]

class EmailRequest(BaseModel):
    email: str = Field(..., description="Email address to send the PDF report to")


class UserDefinedField(BaseModel):
    name: str
    value: Optional[str]

class TicketData(BaseModel):
    id: int
    title: str
    status: int  # Assuming status is represented by integers (e.g., 5 for closed, other values for open)
    priority: int
    description: Optional[str]
    createDate: str
    completedDate: Optional[str] = None
    userDefinedFields: Optional[List[UserDefinedField]] = None

class DeviceData(BaseModel):
    Name: str
    LastLoggedOnUser: str = "N/A"
    IPv4Address: str = "N/A"
    OperatingSystem: str = "N/A"
    antivirusProduct: str = "N/A"
    antivirusStatus: str = "N/A"
    lastReboot: str = "N/A"
    lastSeen: str = "N/A"
    patchStatus: str = "N/A"
    rebootRequired: str = "N/A"
    warrantyDate: str = "N/A"
    datto_id: str = "N/A"
    huntress_id: str = "N/A"
    immy_id: str = "N/A"
    auvik_id: str = "N/A"
    Datto_RMM: str = "No"
    Huntress: str = "No"
    Workstation_AD: str = "No"
    Server_AD: str = "No"
    ImmyBot: str = "No"
    Auvik: str = "No"
    Inactive_Computer: str = "No"