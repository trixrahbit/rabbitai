from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Union


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


from typing import Optional, Union, List
from pydantic import BaseModel, Field, validator

class DeviceData(BaseModel):
    device_name: str = "N/A"
    Datto_RMM: str = "No"
    Huntress: str = "No"
    Workstation_AD: str = "No"
    Server_AD: str = "No"
    ImmyBot: str = "No"
    Auvik: str = "No"
    ITGlue: str = "No"
    Inactive_Computer: str = "No"
    LastLoggedInUser: Optional[str] = "N/A"
    IPv4Address: Union[str, List[str]] = "N/A"  # Adjust for list format if needed
    OperatingSystem: Optional[str] = "N/A"
    antivirusProduct: Optional[str] = "N/A"
    antivirusStatus: Optional[str] = "N/A"
    lastReboot: Optional[str] = "N/A"
    lastSeen: Optional[str] = "N/A"
    patchStatus: Optional[str] = "N/A"
    rebootRequired: Optional[bool] = None
    warrantyDate: Optional[str] = "N/A"
    datto_id: Union[int, str] = "N/A"
    huntress_id: Union[int, str] = "N/A"
    immy_id: Optional[str] = "N/A"
    auvik_id: Optional[str] = "N/A"
    itglue_id: Optional[str] = "N/A"
    manufacturer_name: Optional[str] = "N/A"
    model_name: Optional[str] = "N/A"
    serial_number: Optional[str] = "N/A"
    locationName: Optional[str] = "N/A"

    @validator("Datto_RMM", "Huntress", "Workstation_AD", "Server_AD", "ImmyBot", "Auvik", "ITGlue", "Inactive_Computer", pre=True)
    def parse_yes_no(cls, v):
        if isinstance(v, str):
            return v == "Yes"
        return v

    @validator("rebootRequired", pre=True)
    def parse_reboot_required(cls, v):
        return v if v not in ["N/A", None] else False

