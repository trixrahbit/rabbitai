from typing import List, Dict
from datetime import datetime

from config import AZURE_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT
from models import DeviceData, TicketData
import logging
import requests

from services.data_processing import generate_analytics

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)



def count_open_tickets(tickets: List[TicketData]) -> int:
    open_tickets = [ticket for ticket in tickets if ticket.status != 5]
    return len(open_tickets)

def generate_recommendations(analytics: Dict[str, dict]) -> Dict[str, List[Dict[str, str]]]:
    recommendations = {
        "device_recommendations": [],
        "general_recommendations": []
    }

    # Analyze each issue in the analytics data
    if analytics["issues"]["no_antivirus_installed"]:
        antivirus_recommendation = generate_ai_recommendation(
            "no_antivirus_installed",
            analytics["issues"]["no_antivirus_installed"]
        )
        recommendations["general_recommendations"].append(antivirus_recommendation)

    if analytics["issues"]["expired_warranty"]:
        warranty_recommendation = generate_ai_recommendation(
            "expired_warranty",
            analytics["issues"]["expired_warranty"]
        )
        recommendations["general_recommendations"].append(warranty_recommendation)

    if analytics["issues"]["not_seen_recently"]:
        inactive_devices_recommendation = generate_ai_recommendation(
            "not_seen_recently",
            analytics["issues"]["not_seen_recently"]
        )
        recommendations["general_recommendations"].append(inactive_devices_recommendation)

    if analytics["os_metrics"]["end_of_life"]:
        eol_os_recommendation = generate_ai_recommendation(
            "end_of_life_os",
            analytics["os_metrics"]["end_of_life"]
        )
        recommendations["general_recommendations"].append(eol_os_recommendation)

    if analytics["os_metrics"]["end_of_support"]:
        eos_os_recommendation = generate_ai_recommendation(
            "end_of_support_os",
            analytics["os_metrics"]["end_of_support"]
        )
        recommendations["general_recommendations"].append(eos_os_recommendation)

    return recommendations


def generate_ai_recommendation(issue_type: str, issue_details: List[Dict[str, str]]) -> Dict[str, str]:
    # Generate a descriptive prompt based on the issue type and details
    prompt = build_recommendation_prompt(issue_type, issue_details)

    # Azure OpenAI API call
    headers = {
        "Content-Type": "application/json",
        "api-key": AZURE_API_KEY
    }
    data = {
        "prompt": prompt,
        "max_tokens": 150,
        "temperature": 1.0,
        "n": 1
    }

    response = requests.post(
        f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/completions?api-version=2023-05-15",
        headers=headers,
        json=data
    )

    # Check for errors in the response
    if response.status_code != 200:
        logger.error(f"API call failed with status code {response.status_code}: {response.text}")
        return {
            "issue_type": issue_type,
            "recommendation": f"Error: Unable to generate recommendation due to API error: {response.status_code}"
        }

    try:
        # Ensure 'choices' is in the response
        recommendation_text = response.json()["choices"][0]["text"].strip()
        return {
            "issue_type": issue_type,
            "recommendation": recommendation_text
        }
    except (KeyError, IndexError) as e:
        logger.error(f"Failed to retrieve recommendation text from response: {response.json()}")
        return {
            "issue_type": issue_type,
            "recommendation": "Error: Unable to generate recommendation due to unexpected API response format."
        }

def build_recommendation_prompt(issue_type: str, issue_details: List[Dict[str, str]]) -> str:
    # Generate a descriptive prompt based on the issue type and details
    if issue_type == "no_antivirus_installed":
        return (
            f"Some devices are missing antivirus protection. Here are the devices: "
            f"{[device['device_name'] for device in issue_details]}. "
            f"Generate recommendations on how to address this issue, including actions to install and enforce antivirus protection."
        )
    elif issue_type == "expired_warranty":
        return (
            f"Some devices have expired warranties. Here are the devices: "
            f"{[device['device_name'] for device in issue_details]}. "
            f"Suggest steps to manage devices with expired warranties and ensure device health."
        )
    elif issue_type == "not_seen_recently":
        return (
            f"Some devices have not been seen recently, indicating potential inactivity. Here are the devices: "
            f"{[device['device_name'] for device in issue_details]}. "
            f"Suggest recommendations to assess and manage inactive devices in a network."
        )
    elif issue_type == "end_of_life_os":
        return (
            f"Some devices are running end-of-life operating systems. Here are the devices: "
            f"{[device['device_name'] for device in issue_details]}. "
            f"Generate a plan for upgrading these systems and maintaining supported OS versions."
        )
    elif issue_type == "end_of_support_os":
        return (
            f"Some devices are running operating systems that are nearing or at end of support. Here are the devices: "
            f"{[device['device_name'] for device in issue_details]}. "
            f"Provide recommendations for upgrading these devices to supported OS versions to enhance security and performance."
        )
    else:
        return "Generate general recommendations for improving device and network health."

def generate_analytics_with_recommendations(device_data: List[DeviceData]) -> Dict[str, dict]:
    analytics = generate_analytics(device_data)
    recommendations = generate_recommendations(analytics)
    return {
        "analytics": analytics,
        "recommendations": recommendations
    }
