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
    device_name: str = Field(alias="device_name")
    LastLoggedOnUser: Optional[str] = "N/A"
    IPv4Address: Optional[str] = "N/A"
    OperatingSystem: Optional[str] = "N/A"
    antivirusProduct: Optional[str] = "N/A"
    antivirusStatus: Optional[str] = "N/A"
    lastReboot: Optional[str] = "N/A"  # Consider using datetime if dates are required
    lastSeen: Optional[str] = "N/A"    # Same as above
    patchStatus: Optional[str] = "N/A"
    rebootRequired: Optional[bool] = False  # Use bool for consistent handling
    warrantyDate: Optional[str] = "N/A"     # Same as above if date needed
    datto_id: Optional[str] = "N/A"
    huntress_id: Optional[str] = "N/A"
    immy_id: Optional[str] = "N/A"
    auvik_id: Optional[str] = "N/A"
    Datto_RMM: bool = False
    Huntress: bool = False
    Workstation_AD: bool = False
    Server_AD: bool = False
    ImmyBot: bool = False
    Auvik: bool = False
    Inactive_Computer: bool = False