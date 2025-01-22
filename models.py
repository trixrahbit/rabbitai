from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Union, Any


class DataAggregationRequest(BaseModel):
    data: List[Dict[str, Any]] = Field(..., description="List of records to aggregate and generate PDF from")
    # Example of the expected structure:
    # [
    #     {"name": "Alice", "age": 30, "occupation": "Engineer"},
    #     {"name": "Bob", "age": 25, "occupation": "Designer"}
    # ]


class EmailRequest(BaseModel):
    email: str = Field(..., description="Email address to send the PDF report to")


class UserDefinedField(BaseModel):
    name: str
    value: Optional[str] = None


class TicketData(BaseModel):
    id: int
    title: str
    status: int  # Assuming status is represented by integers (e.g., 5 for closed, other values for open)
    priority: int
    description: Optional[str] = None
    createDate: str
    completedDate: Optional[str] = None
    userDefinedFields: Optional[List[UserDefinedField]] = None


class DeviceData(BaseModel):
    Name: str = "N/A"
    device_name: str = "N/A"
    LastLoggedOnUser: str = "N/A"
    IPv4Address: str = "N/A"
    OperatingSystem: str = "N/A"
    antivirusProduct: str = "N/A"
    antivirusStatus: str = "N/A"
    lastReboot: str = "N/A"
    lastSeen: str = "N/A"
    patchStatus: str = "N/A"
    rebootRequired: Optional[bool] = None
    warrantyDate: str = "N/A"

    # IDs
    datto_id: Optional[Union[int, str]] = None
    huntress_id: Optional[Union[int, str]] = None
    immy_id: Optional[str] = None
    auvik_id: Optional[str] = None
    cybercns_id: Optional[str] = None
    itglue_id: Optional[str] = None
    manufacturer_name: Optional[str] = None
    model_name: Optional[str] = None
    serial_number: Optional[str] = None

    # Integration flags
    Datto_RMM: bool = False
    Huntress: bool = False
    Workstation_AD: bool = False
    Server_AD: bool = False
    ImmyBot: bool = False
    Auvik: bool = False
    ITGlue: bool = False
    CyberCNS: bool = False
    Inactive_Computer: bool = False

    @validator("Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "CyberCNS", "ITGlue",
               "Inactive_Computer", pre=True)
    def parse_yes_no(cls, v):
        if isinstance(v, str):
            return v.lower() == "yes"
        return v

    @validator("rebootRequired", pre=True)
    def parse_reboot_required(cls, v):
        if v == "N/A":
            return None
        return bool(v) if isinstance(v, bool) else None

    class Config:
        populate_by_name = True  # Ensure compatibility with Pydantic v2
