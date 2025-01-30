from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Union, Any
from datetime import datetime

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    CLIENT_ID: str
    TENANT_ID: str
    CLIENT_SECRET: str
    BOT_CLIENT_ID: str
    BOT_CLIENT_SECRET: str
    API_KEY: str  # For API key-based security
    APP_ID: str
    APP_SECRET: str
    AZURE_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    DEPLOYMENT_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_SECONDARY_USER: str
    DB_SECONDARY_PASSWORD: str
    DB_SERVER: str
    DB_NAME: str
    DB_SECONDARY_NAME: str
    class Config:
        env_file = ".env"

class UserDefinedField(BaseModel):
    name: str
    value: Optional[str] = None

class TicketData(BaseModel):
    id: int
    ticketNumber: str
    title: str
    description: Optional[str] = None
    companyID: int
    contactID: Optional[int] = None
    contractID: Optional[int] = None
    assignedResourceID: Optional[int] = None
    queueID: Optional[int] = None
    status: int
    priority: int
    ticketCategory: int
    ticketType: int
    issueType: int
    subIssueType: Optional[int] = None
    source: Optional[int] = None
    serviceLevelAgreementHasBeenMet: Optional[bool] = None
    createDate: Optional[datetime] = None
    dueDateTime: Optional[datetime] = None
    firstResponseDateTime: Optional[datetime] = None
    firstResponseDueDateTime: Optional[datetime] = None
    resolutionPlanDateTime: Optional[datetime] = None
    resolutionPlanDueDateTime: Optional[datetime] = None
    resolvedDateTime: Optional[datetime] = None
    resolvedDueDateTime: Optional[datetime] = None
    completedDate: Optional[datetime] = None
    lastActivityDate: Optional[datetime] = None
    userDefinedFields: Optional[List[dict]] = None
    @validator(
        "createDate",
        "dueDateTime",
        "firstResponseDateTime",
        "firstResponseDueDateTime",
        "resolutionPlanDateTime",
        "resolutionPlanDueDateTime",
        "resolvedDateTime",
        "resolvedDueDateTime",
        "completedDate",
        "lastActivityDate",
        pre=True
    )
    def parse_datetime(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", ""))
        return value
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
    cybercns_id: Optional[Union[str, int]] = "N/A"
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

# class ContractUnit(BaseModel):
#     contractID: Optional[int] = None
#     id: Optional[int] = None
#     serviceID: Optional[int] = None
#     startDate: Optional[str] = None
#     endDate: Optional[str] = None
#     unitCost: Optional[float] = None
#     unitPrice: Optional[float] = None
#     internalCurrencyPrice: Optional[float] = None
#     organizationalLevelAssociationID: Optional[int] = None
#     invoiceDescription: Optional[str] = None
#     approveAndPostDate: Optional[str] = None
#     units: Optional[float] = None

class ProcessedContractUnit(BaseModel):
    contractID: Optional[int] = None
    id: Optional[int] = None
    serviceID: Optional[int] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    unitCost: Optional[float] = None
    unitPrice: Optional[float] = None
    internalCurrencyPrice: Optional[float] = None
    organizationalLevelAssociationID: Optional[int] = None
    invoiceDescription: Optional[str] = None
    approveAndPostDate: Optional[str] = None
    units: Optional[float] = None

class Contract(BaseModel):
    id: int
    status: int
    endDate: str
    setupFee: Optional[float] = None
    companyID: int
    contactID: Optional[int] = None
    startDate: str
    contactName: Optional[str] = None
    description: Optional[str] = None
    isCompliant: bool
    contractName: str
    contractType: int
    estimatedCost: Optional[float] = None
    opportunityID: Optional[int] = None
    contractNumber: Optional[str] = None
    estimatedHours: Optional[float] = None
    billToCompanyID: Optional[int] = None
    contractCategory: int
    estimatedRevenue: Optional[float] = None
    billingPreference: int
    isDefaultContract: bool
    renewedContractID: Optional[int] = None
    userDefinedFields: Optional[List[UserDefinedField]] = None
    contractPeriodType: int
    overageBillingRate: Optional[float] = None
    exclusionContractID: Optional[int] = None
    purchaseOrderNumber: Optional[str] = None
    lastModifiedDateTime: str
    setupFeeBillingCodeID: Optional[int] = None
    billToCompanyContactID: Optional[int] = None
    contractExclusionSetID: Optional[int] = None
    serviceLevelAgreementID: Optional[int] = None
    internalCurrencySetupFee: Optional[float] = None
    organizationalLevelAssociationID: Optional[int] = None
    internalCurrencyOverageBillingRate: Optional[float] = None
    timeReportingRequiresStartAndStopTimes: int

    @validator("startDate", "endDate", "lastModifiedDateTime", pre=True)
    def parse_dates(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", ""))
        return v

class TimeEntries(BaseModel):
    id: int
    contractID: int
    contractServiceBundleID: Optional[int] = None
    contractServiceID: Optional[int] = None
    createDateTime: Optional[datetime] = None
    creatorUserID: int
    dateWorked: Optional[datetime] = None
    endDateTime: Optional[datetime] = None
    hoursToBill: float
    hoursWorked: float
    internalNotes: Optional[str] = None
    isNonBillable: bool
    lastModifiedDateTime: Optional[datetime] = None
    resourceID: int
    roleID: int
    startDateTime: Optional[datetime] = None
    summaryNotes: Optional[str] = None
    taskID: Optional[int] = None
    ticketID: Optional[int] = None
    timeEntryType: int
    userDefinedFields: Optional[List]

    @validator("createDateTime", "dateWorked", "endDateTime", "lastModifiedDateTime", "startDateTime", pre=True)
    def parse_datetime(cls, value):
        """Converts string timestamps into datetime objects"""
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")  # Handles fractional seconds
            except ValueError:
                try:
                    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")  # Handles 'Z' format without milliseconds
                except ValueError:
                    return None  # Return None if parsing fails
        return value

class ResourceResponseResolution(BaseModel):
    id: Optional[int] = None
    resourceID: int
    emailAddress: Optional[str] = None
    assignedResource: str
    weekStartDate: str
    weekEndDate: str
    totalResponseTime: float
    totalResolutionTime: float
    avgResponseTime: float
    avgResolutionTime: float
    ticketCount: int