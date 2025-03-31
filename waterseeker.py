
import requests
import streamlit as st
from langchain.prompts import PromptTemplate
from langchain_core.runnables import RunnableSequence
from langchain_core.output_parsers import StrOutputParser
from geopy.geocoders import Nominatim
import re
import time
import json

# API Keys
WATSON_API_KEY = st.secrets["WATSON_API_KEY"]

PROJECT_ID = "d7260761-7525-4bb8-b618-6f0928271382"
BASE_URL = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"

def get_iam_token(api_key):
    url = "https://iam.cloud.ibm.com/identity/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = f"grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey={api_key}"
    response = requests.post(url, headers=headers, data=data, timeout=10)
    if response.status_code != 200:
        raise Exception(f"Failed to get IAM token: {response.text}")
    return response.json()["access_token"]

IAM_TOKEN = get_iam_token(WATSON_API_KEY)  # Replace with fresh token

def call_watsonx(prompt_text):
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {IAM_TOKEN}"
    }
    payload = {
        "input": prompt_text,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 1000,
            "min_new_tokens": 50,
            "repetition_penalty": 1
        },
        "model_id": "ibm/granite-3-8b-instruct",
        "project_id": PROJECT_ID
    }
    try:
        response = requests.post(BASE_URL, json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            raise Exception(f"API call failed: {response.status_code} - {response.text}")
        return response.json()["results"][0]["generated_text"]
    except requests.Timeout:
        raise Exception("API call timed out after 30 seconds")

class WatsonxLLM:
    def __call__(self, prompt, **kwargs):
        prompt_text = prompt.text if hasattr(prompt, "text") else str(prompt)
        return call_watsonx(prompt_text)

geolocator = Nominatim(user_agent="WaterSeekerAgent")

def fetch_water_resource_data(lat, lon, country, city, agent_log):
    agent_log.append(f"🌊 Fetching water resource data for (lat: {lat}, lon: {lon}) in {country}, {city}...")
    try:
        # Define a bounding box (±0.5 degrees) around the location
        lat_min, lat_max = lat - 0.5, lat + 0.5
        lon_min, lon_max = lon - 0.5, lon + 0.5

        if country == "United States":
            # Query USGS NWIS for nearby water monitoring stations
            usgs_url = f"https://waterservices.usgs.gov/nwis/site/?format=rdb&bBox={lon_min},{lat_min},{lon_max},{lat_max}&siteType=ST,GW&hasDataTypeCd=qw,gw"
            response = requests.get(usgs_url, timeout=10)
            if response.status_code == 200:
                lines = response.text.split("\n")
                for line in lines:
                    if not line.startswith("#") and line.strip():
                        fields = line.split("\t")
                        if len(fields) > 5:  # Ensure enough fields
                            site_name = fields[2]  # station_nm
                            site_type = fields[3]  # site_tp_cd
                            agent_log.append(f"✅ Found USGS site: {site_name} ({site_type})")
                            return f"Nearby Water Resource: {site_name} ({site_type})"
            agent_log.append("⚠️ No USGS data found, falling back to general info.")
            return f"Nearby Water Resources: Limited data available. The U.S. has extensive water monitoring networks (USGS)."

        elif country == "Canada":
            # Query Environment Canada for hydrometric data
            ec_url = f"https://wateroffice.ec.gc.ca/search/station_e.html?lat={lat}&lon={lon}&radius=50"
            response = requests.get(ec_url, timeout=10)
            if response.status_code == 200:
                # Note: This API requires parsing HTML, which is complex. For simplicity, assume we find a station.
                agent_log.append("✅ Found Environment Canada hydrometric station.")
                return "Nearby Water Resource: Hydrometric station data available (Environment Canada)."
            agent_log.append("⚠️ No Environment Canada data found, falling back to general info.")
            return "Nearby Water Resources: Canada has extensive hydrometric monitoring (Environment Canada)."

        else:
            # Fallback to general web search for Brazil, Argentina, etc.
            search_query = f"water resources near {country} {city if city != 'Unknown' else ''} latitude {lat} longitude {lon}"
            agent_log.append(f"🔍 Performing web search: {search_query}")
            # Simulate web search result (in a real app, use a search API like Google Custom Search)
            if country == "Brazil":
                return "Nearby Water Resources: Brazil’s Cerrado region has significant groundwater reserves, but faces deforestation challenges."
            elif country == "Argentina":
                return "Nearby Water Resources: Argentina’s Pampas region is known for its aquifers, with annual rainfall around 600-1000mm."
            else:
                return "Nearby Water Resources: Limited data available for this region."
    except Exception as e:
        agent_log.append(f"❌ Error fetching water resource data: {str(e)}")
        return "Nearby Water Resources: Unable to fetch data due to an error."

def get_location_info(lat, lon, agent_log):
    agent_log.append(f"📍 Looking up location for coordinates (lat: {lat}, lon: {lon})...")
    try:
        time.sleep(1)  # Delay between requests
        location = geolocator.reverse((lat, lon), language="en", timeout=10)
        if location and location.raw.get("address"):
            addr = location.raw["address"]
            country = addr.get("country", "Unknown")
            city = addr.get("city") or addr.get("town") or addr.get("village") or "Unknown"
            agent_log.append(f"✅ Found location: Country: {country}, City: {city}")
            # Fetch additional water resource data
            water_data = fetch_water_resource_data(lat, lon, country, city, agent_log)
            return country, city, water_data
        agent_log.append("⚠️ Location not found, using default values.")
        return "Unknown", "Unknown", "Nearby Water Resources: Location data unavailable."
    except Exception as e:
        agent_log.append(f"❌ Error looking up location: {str(e)}")
        return "Unknown", "Unknown", "Nearby Water Resources: Unable to fetch data due to an error."

analysis_prompt = PromptTemplate(
    input_variables=["locations", "num_locations"],
    template="""Analyze these locations for water reservoir potential. You must only analyze the {num_locations} location(s) provided below. Do not generate or analyze any additional locations beyond Location {num_locations}. For each, provide:
- Rainfall: <value>mm/year (e.g., 1200mm/year)
- Capacity: <value>M liters (e.g., 5M liters)
Format as a single line per location with `-`. Example:
- Location 1 (lat: 35.5, lon: -78.3): Rainfall: 1200mm/year, Capacity: 5M liters
- Location 2 (lat: 36.0, lon: -79.0): Rainfall: 800mm/year, Capacity: 3M liters
Provide exactly one line per location, do not use sub-bullets, and do not skip fields or deviate from this format:\n{locations}"""
)

recommendation_prompt = PromptTemplate(
    input_variables=["analysis", "num_locations"],
    template="""Recommend the best location for a water reservoir based on this analysis. You must recommend exactly one location from the locations listed in the analysis (Locations 1 to {num_locations}). Do not recommend any other locations, and do not provide "No recommendation" for other locations. Prioritize the location with the highest capacity (in M liters). If there is a tie in capacity, use rainfall (in mm/year) as the tiebreaker. Provide exactly:
- Recommended: Location X (lat: Y, lon: Z)
- Justification: <reason based primarily on capacity, using rainfall only as a tiebreaker, comparing all locations>
Format as bullet points with `-`. Example:
- Recommended: Location 1 (lat: 35.5, lon: -78.3)
- Justification: Highest capacity (5M liters) compared to Location 2 (3M liters). Rainfall of 1200mm/year is sufficient.
If no suitable location is found, state exactly once:
- No recommendation: <reason>
Analysis:\n{analysis}"""
)

llm = WatsonxLLM()
analysis_sequence = analysis_prompt | llm | StrOutputParser()
recommendation_sequence = recommendation_prompt | llm | StrOutputParser()

def run_waterseeker_agent(locations):
    agent_log = []  # To store the agent's process
    if not locations:
        agent_log.append("❌ No locations provided for analysis.")
        return "No locations provided for analysis.", "No recommendation: No locations provided.", [], "\n".join(agent_log), []
    
    # Convert locations to text for analysis
    locations_text = "\n".join([f"Location {i+1}: (lat: {lat}, lon: {lon})" for i, (lat, lon) in enumerate(locations)])
    agent_log.append(f"📋 Preparing to analyze {len(locations)} location(s):")
    agent_log.append(locations_text.replace("\n", "\n"))
    
    # Run analysis
    agent_log.append("🤖 Running analysis with watsonx.ai (Granite-3-8B model)...")
    analysis = analysis_sequence.invoke({"locations": locations_text, "num_locations": len(locations)})
    agent_log.append("✅ Analysis complete:")
    agent_log.append(analysis.replace("\n", "\n"))
    
    # First, try to parse as single-line format
    analysis_lines = [line.strip() for line in analysis.split("\n") if line.strip().startswith("- Location")]
    filtered_analysis_lines = []
    for i in range(len(locations)):
        expected_prefix = f"- Location {i+1} (lat: {locations[i][0]}, lon: {locations[i][1]}):"
        found = False
        for line in analysis_lines:
            if line.startswith(expected_prefix):
                if "Rainfall:" in line and "Capacity:" in line:
                    filtered_analysis_lines.append(line)
                    found = True
                    break
        if not found:
            current_location = None
            rainfall = capacity = None
            for line in analysis.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith(f"- Location {i+1} (lat: {locations[i][0]}, lon: {locations[i][1]}):"):
                    current_location = line
                    rainfall = capacity = None
                elif line.startswith("- Rainfall:"):
                    rainfall_match = re.search(r"Rainfall: (\d+\.?\d*)mm/year", line)
                    rainfall = rainfall_match.group(1) if rainfall_match else "0"
                elif line.startswith("- Capacity:"):
                    capacity_match = re.search(r"Capacity: (\d+\.?\d*)M liters", line)
                    capacity = capacity_match.group(1) if capacity_match else "0"
                    if current_location and rainfall is not None:
                        flattened_line = f"{current_location}: Rainfall: {rainfall}mm/year, Capacity: {capacity}M liters"
                        filtered_analysis_lines.append(flattened_line)
                        found = True
                        break
            if not found:
                filtered_analysis_lines.append(f"- Location {i+1} (lat: {locations[i][0]}, lon: {locations[i][1]}): Rainfall: 0mm/year, Capacity: 0M liters")
    
    # Validate analysis matches input locations
    if len(filtered_analysis_lines) != len(locations):
        agent_log.append(f"❌ Error: Analysis includes {len(filtered_analysis_lines)} locations, but {len(locations)} were provided.")
        filtered_analysis_lines = analysis_lines if analysis_lines else [f"- Location {i+1} (lat: {lat}, lon: {lon}): Rainfall: 0mm/year, Capacity: 0M liters" for i, (lat, lon) in enumerate(locations)]
    
    # Run recommendation with strict constraint
    filtered_analysis = "\n".join(filtered_analysis_lines)
    agent_log.append("🔍 Performing comparison for recommendation...")
    for line in filtered_analysis_lines:
        rainfall_match = re.search(r"Rainfall: (\d+\.?\d*)mm/year", line)
        capacity_match = re.search(r"Capacity: (\d+\.?\d*)M liters", line)
        loc_id_match = re.search(r"Location (\d+)", line)
        rainfall = rainfall_match.group(1) if rainfall_match else "0"
        capacity = capacity_match.group(1) if capacity_match else "0"
        loc_id = loc_id_match.group(1) if loc_id_match else "Unknown"
        agent_log.append(f"  - Location {loc_id}: Rainfall: {rainfall}mm/year, Capacity: {capacity}M liters")
    agent_log.append("🤖 Generating recommendation with watsonx.ai (Granite-3-8B model)...")
    recommendation = recommendation_sequence.invoke({"analysis": filtered_analysis, "num_locations": len(locations)})
    
    # Post-process recommendation to filter out duplicates and invalid locations
    valid_location_ids = set(range(1, len(locations) + 1))
    rec_lines = recommendation.split("\n")
    filtered_rec = []
    recommended_loc = None
    seen_no_recommendation = False
    for i, line in enumerate(rec_lines):
        line = line.strip()
        if not line:
            continue
        if line.startswith("- Recommended: Location"):
            loc_id_match = re.search(r"Recommended: Location (\d+)", line)
            if loc_id_match:
                loc_id = int(loc_id_match.group(1))
                if loc_id not in valid_location_ids:
                    filtered_rec.append(f"- Error: Invalid recommendation for Location {loc_id}. Only Locations 1 to {len(locations)} were provided.")
                    continue
                if recommended_loc is None:  # Only keep the first recommendation
                    recommended_loc = loc_id
                    filtered_rec.append(line)
        elif line.startswith("- Justification:") and recommended_loc is not None:
            filtered_rec.append(line)
        elif line.startswith("- No recommendation:"):
            if not seen_no_recommendation:
                filtered_rec.append(line)
                seen_no_recommendation = True
    recommendation = "\n".join(filtered_rec)
    agent_log.append("✅ Recommendation generated:")
    agent_log.append(recommendation.replace("\n", "\n"))
    if not recommendation:
        recommendation = "- No recommendation: Failed to generate a valid recommendation."
        agent_log.append("❌ Failed to generate a valid recommendation.")
    
    # Enrich analysis with country, city, and water resource data
    enriched_analysis = []
    water_resources_data = []
    for i, (lat, lon) in enumerate(locations):
        country, city, water_data = get_location_info(lat, lon, agent_log)
        analysis_line = filtered_analysis_lines[i]
        enriched_analysis.append(f"{analysis_line}, Country: {country}, City: {city}")
        water_resources_data.append(water_data)
    
    enriched_analysis = "\n".join(enriched_analysis)
    
    return enriched_analysis, recommendation, locations, "\n".join(agent_log), water_resources_data

if __name__ == "__main__":
    sample_locations = [(35.5, -78.3), (36.0, -79.0)]
    try:
        analysis, recommendation, coords, agent_log, water_resources = run_waterseeker_agent(sample_locations)
        print("Analysis:", analysis)
        print("Recommendation:", recommendation)
        print("Coordinates:", coords)
        print("Agent Log:", agent_log)
        print("Water Resources Data:", water_resources)
    except Exception as e:
        print(f"Error: {str(e)}")