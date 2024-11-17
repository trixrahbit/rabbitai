import logging
import os
import json
from typing import List, Dict
import httpx
from config import logger, AZURE_API_KEY, AZURE_OPENAI_ENDPOINT, deployment_name
# AI Processing
def generate_recommendations(analytics: Dict[str, dict]) -> Dict[str, List[Dict[str, str]]]:
    recommendations = {
        "device_recommendations": [],
        "strategic_plan": []
    }

    for issue_type, devices in analytics["issues"].items():
        if devices:
            # Ensure devices is a list of dictionaries with 'device_name' key
            if isinstance(devices, list) and all(isinstance(device, dict) and "device_name" in device for device in devices):
                recommendation = generate_ai_recommendation(issue_type, devices)
                recommendations["strategic_plan"].append(recommendation)
            else:
                logger.error(f"Unexpected data structure for devices in issue type {issue_type}: {devices}")
                recommendations["strategic_plan"].append({
                    "issue_type": issue_type,
                    "recommendation": "Error: Data structure issue; unable to generate recommendation."
                })

    return recommendations

def generate_ai_recommendation(issue_type: str, issue_details: List[Dict[str, str]]) -> Dict[str, str]:
    prompt = build_recommendation_prompt(issue_type, issue_details)

    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{deployment_name}/chat/completions?api-version=2023-05-15"

    try:
        data = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.7,
            "n": 1
        }

        logger.debug(f"Sending payload to Azure OpenAI: {json.dumps(data)}")

        response = httpx.post(
            url,
            headers={
                "Content-Type": "application/json",
                "api-key": AZURE_API_KEY
            },
            json=data
        )

        response.raise_for_status()

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
    # Tailored prompts for generating a strategic plan
    if issue_type == "not_seen_recently":
        return (
            f"As a vCIO for an MSP, develop a strategic plan to address inactive devices in the network. "
            f"Devices that have not been recently seen may indicate potential inactivity. "
            f"Here are the devices: {[device['device_name'] for device in issue_details]}. "
            f"Outline a step-by-step process to identify, assess, and manage these devices, considering "
            f"long-term monitoring and removal of outdated devices if necessary."
        )
    elif issue_type == "end_of_life_os":
        return (
            f"As a vCIO for an MSP, develop a strategic plan for upgrading devices running end-of-life operating systems. "
            f"Here are the devices affected: {[device['device_name'] for device in issue_details]}. "
            f"Provide actionable steps for migrating these systems to supported versions, including client communication, "
            f"budgeting considerations, and a timeline for phased upgrades."
        )
    elif issue_type == "end_of_support_os":
        return (
            f"As a vCIO for an MSP, create a strategic plan for managing devices with operating systems that are nearing "
            f"or at the end of support. Devices include: {[device['device_name'] for device in issue_details]}. "
            f"Recommend steps to transition these devices to supported systems, ensuring minimal disruption and client alignment. "
            f"Consider security risks, phased upgrade timelines, and budget allocation."
        )
    elif issue_type == "missing_defender_on_workstation":
        return (
            f"As a vCIO, develop a game plan to ensure all workstations have appropriate antivirus software installed and running. "
            f"Devices missing Defender: {[device['device_name'] for device in issue_details]}. "
            f"Outline a process for implementing and enforcing antivirus installation, including periodic compliance checks and automation options."
        )
    elif issue_type == "missing_sentinel_one_on_server":
        return (
            f"As a vCIO, outline a strategic approach to ensure all servers are protected with SentinelOne or equivalent. "
            f"Identify steps to assess, install, and enforce the antivirus protection policy on the affected servers: "
            f"{[device['device_name'] for device in issue_details]}."
        )
    elif issue_type == "reboot_required":
        return (
            f"As a vCIO, create a plan to address devices that require a reboot. For effective maintenance, ensure that these devices "
            f"are rebooted without disrupting operations. Devices requiring reboot: {[device['device_name'] for device in issue_details]}. "
            f"Develop a communication protocol with clients for scheduled reboots and automated reminders."
        )
    elif issue_type == "recently_inactive_devices":
        return (
            f"Provide a strategic plan to handle recently inactive devices as an MSP vCIO. "
            f"Inactive devices in the past month: {[device['device_name'] for device in issue_details]}. "
            f"Outline steps to verify device usage status, implement a monitoring policy, and set thresholds for device removal."
        )
    else:
        return (
            f"As a vCIO for an MSP, provide high-level strategic recommendations for overall network health and maintenance. "
            f"Generate a plan addressing device lifecycle management, compliance, and proactive monitoring."
        )

async def handle_sendtoai(data: str) -> dict:
    """
    Sends user input to Azure OpenAI for processing and returns the result.
    """
    if not data:
        return {"response": "No text provided for AI processing."}

    # Build the payload
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{deployment_name}/chat/completions?api-version=2023-05-15"
    payload = {
        "messages": [{"role": "user", "content": data}],
        "max_tokens": 4096,
        "temperature": 0.7,
        "n": 1,
    }

    try:
        # Send the request to Azure OpenAI
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "api-key": AZURE_API_KEY,
                },
                json=payload,
            )
            response.raise_for_status()

            # Parse the response
            ai_result = response.json()["choices"][0]["message"]["content"].strip()
            logging.info(f"Raw OpenAI response: {response.json()}")
            logging.info(f"AI Result: {ai_result}")
            ai_result = ai_result.replace("\n", " ").strip()
            return {"response": f"{ai_result}"}
    except httpx.HTTPStatusError as e:
        return {"response": f"Error communicating with OpenAI: {e.response.text}"}
    except KeyError:
        return {"response": "Error: Unexpected response format from OpenAI."}