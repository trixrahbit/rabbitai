from typing import Optional
from datetime import date
from pydantic import BaseModel


class KPI(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    category: str  # Values: 'Service Desk', 'Field Team', 'Professional Services', 'Security', 'Procurement'
    type: str  # Values: 'Team', 'Individual'


class KPIValue(BaseModel):
    id: int
    kpi_id: int
    resource_id: Optional[int] = None  # Null for team-level KPIs
    team_name: Optional[str] = None  # Null for individual KPIs
    value: float
    date_recorded: date = date.today()


class EndpointMetric(BaseModel):
    id: int
    kpi_id: int
    endpoint_id: str
    value: float
    date_recorded: date = date.today()


class TicketMetric(BaseModel):
    id: int
    kpi_id: int
    ticket_id: str
    resource_id: Optional[int] = None  # Only for individual KPIs
    team_name: Optional[str] = None  # Only for team KPIs
    value: float
    date_recorded: date = date.today()


class CallMetric(BaseModel):
    id: int
    kpi_id: int
    resource_id: Optional[int] = None  # Null for team-level call KPIs
    total_calls: int
    avg_duration: Optional[float] = None
    date_recorded: date = date.today()


class Resource(BaseModel):
    resource_id: int
    email: str
    first_name: str
    last_name: str
