import os
import json
from typing import List, Dict
import httpx
from config import logger, AZURE_API_KEY, AZURE_OPENAI_ENDPOINT, deployment_name


def generate_recommendations(analytics: Dict[str, dict]) -> Dict[str, List[Dict[str, str]]]:
    recommendations = {
        "device_recommendations": [],
        "general_recommendations": []
    }

    for issue_type, devices in analytics["issues"].items():
        if devices:
            # Ensure devices is a list of dictionaries with 'device_name' key
            if isinstance(devices, list) and all(isinstance(device, dict) and "device_name" in device for device in devices):
                recommendation = generate_ai_recommendation(issue_type, devices)
                recommendations["general_recommendations"].append(recommendation)
            else:
                logger.error(f"Unexpected data structure for devices in issue type {issue_type}: {devices}")
                recommendations["general_recommendations"].append({
                    "issue_type": issue_type,
                    "recommendation": "Error: Data structure issue; unable to generate recommendation."
                })

    return recommendations


def generate_ai_recommendation(issue_type: str, issue_details: List[Dict[str, str]]) -> Dict[str, str]:
    prompt = build_recommendation_prompt(issue_type, issue_details)

    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{deployment_name}/chat/completions?api-version=2023-05-15"

    try:
        # Construct the payload for the chat completion endpoint
        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.7,
            "n": 1
        }

        # Debugging: Log the payload being sent
        logger.debug(f"Sending payload to Azure OpenAI: {json.dumps(data)}")

        response = httpx.post(
            url,
            headers={
                "Content-Type": "application/json",
                "api-key": AZURE_API_KEY
            },
            json=data
        )

        # Raise for any HTTP error statuses
        response.raise_for_status()

        # Extract recommendation from the response
        recommendation_text = response.json()['choices'][0]['message']['content'].strip()
        return {
            "issue_type": issue_type,
            "recommendation": recommendation_text
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to retrieve recommendation text: {e} - Response: {response.text}")
        return {
            "issue_type": issue_type,
            "recommendation": "Error: Unable to generate recommendation due to API error."
        }
    except KeyError:
        logger.error(f"Unexpected response format: {response.json()}")
        return {
            "issue_type": issue_type,
            "recommendation": "Error: Unexpected response format from Azure OpenAI API."
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
