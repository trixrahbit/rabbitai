from pydantic import BaseModel, Field
from typing import List, Dict

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