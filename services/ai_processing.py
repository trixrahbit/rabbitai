import os
import json
from typing import List, Dict

from config import client, logger

# Initialize the Azure OpenAI client with Azure-specific endpoint, key, and API version


deployment_name = os.getenv("rabbit_smart")  # Set your deployment name here


def generate_recommendations(analytics: Dict[str, dict]) -> Dict[str, List[Dict[str, str]]]:
    recommendations = {
        "device_recommendations": [],
        "general_recommendations": []
    }

    # Mapping each issue type to a descriptive prompt
    issue_prompts = {
        "no_antivirus_installed": "Some devices are missing antivirus protection. Here are the devices: {}. Generate recommendations on how to address this issue, including actions to install and enforce antivirus protection.",
        "missing_defender_on_workstation": "Some workstations are missing Windows Defender. Here are the devices: {}. Provide recommendations for ensuring antivirus coverage on all workstations.",
        "missing_sentinel_one_on_server": "Some servers are missing SentinelOne antivirus. Here are the servers: {}. Suggest actions to ensure servers have appropriate antivirus software installed.",
        "not_seen_recently": "Some devices have not been seen recently, indicating potential inactivity. Here are the devices: {}. Provide recommendations on how to manage inactive devices.",
        "reboot_required": "Some devices require a reboot. Here are the devices: {}. Suggest a strategy for maintaining regular device reboots to keep systems up-to-date.",
        "expired_warranty": "Some devices have expired warranties. Here are the devices: {}. Recommend strategies for handling devices with expired warranties.",
        "end_of_life": "Some devices are running end-of-life operating systems. Here are the devices: {}. Provide a plan for upgrading these devices to supported OS versions.",
        "end_of_support": "Some devices are running operating systems that are nearing or at end of support. Here are the devices: {}. Suggest strategies for upgrading these devices to supported OS versions."
    }

    # Generate recommendations for each issue type
    for issue_type, devices in analytics["issues"].items():
        if devices:  # Only generate recommendation if there are devices with this issue
            device_names = [device["device_name"] for device in devices]
            prompt = issue_prompts.get(issue_type, "").format(device_names)

            if prompt:
                # Call AI function to get recommendation based on prompt
                recommendation = generate_ai_recommendation(issue_type, prompt)
                recommendations["general_recommendations"].append(recommendation)

    return recommendations


def generate_ai_recommendation(issue_type: str, issue_details: List[Dict[str, str]]) -> Dict[str, str]:
    # Generate a descriptive prompt based on the issue type and details
    prompt = build_recommendation_prompt(issue_type, issue_details)

    # Define the messages and the initial prompt message for the model
    messages = [
        {"role": "user", "content": prompt}
    ]

    try:
        # Call the Azure OpenAI chat completions API
        response = client.chat.completions.create(
            model=deployment_name,
            messages=messages
        )

        # Extract recommendation from the response
        recommendation_text = response.choices[0].message['content'].strip()
        return {
            "issue_type": issue_type,
            "recommendation": recommendation_text
        }
    except Exception as e:
        # Log and return a default error message in case of failure
        logger.error(f"Failed to retrieve recommendation text: {e}")
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
