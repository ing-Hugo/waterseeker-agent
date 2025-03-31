# waterseeker-agent/app.py
import streamlit as st
from waterseeker import run_waterseeker_agent
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import io
import base64
import re
import requests
from geopy.geocoders import Nominatim
import time

st.set_page_config(page_title="WaterSeeker Agent", page_icon="💧")
st.title("💧 WaterSeeker Agent")
st.markdown("An AI-powered tool to find the best water reservoir sites with real-time insights!")

# Custom CSS for a futuristic appearance
st.markdown("""
    <style>
    /* Futuristic background with gradient and subtle animation */
    .stApp {
        background: linear-gradient(135deg, #0a0e2a, #1a1e3a, #2a2e4a);
        background-size: 400% 400%;
        animation: gradientShift 15s ease infinite;
        color: #e0e0ff;
        font-family: 'Orbitron', 'Arial', sans-serif;
    }
    @keyframes gradientShift {
        0% { background-position: 0% 0%; }
        50% { background-position: 100% 100%; }
        100% { background-position: 0% 0%; }
    }
    /* Sidebar styling */
    .stSidebar {
        background: #0a0e2a;
        color: #e0e0ff;
        padding: 20px;
        border-right: 2px solid #00ffcc;
    }
    /* Card-like containers for sections */
    .card {
        background: rgba(10, 14, 42, 0.9);
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        border: 1px solid #00ffcc;
        box-shadow: 0 0 15px rgba(0, 255, 204, 0.3);
    }
    /* Header styling */
    h1, h2, h3 {
        color: #00ffcc;
        text-shadow: 0 0 10px #00ffcc;
    }
    /* Button styling */
    .stButton>button {
        background-color: #00ffcc;
        color: #0a0e2a;
        border: none;
        padding: 10px 20px;
        border-radius: 5px;
        font-weight: bold;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #00cc99;
        transform: scale(1.05);
        box-shadow: 0 0 10px #00ffcc;
    }
    /* Text area and other elements */
    .stTextArea textarea {
        background: #1a1e3a;
        color: #e0e0ff;
        border: 1px solid #00ffcc;
    }
    .stExpander {
        background: #1a1e3a;
        border: 1px solid #00ffcc;
        border-radius: 5px;
    }
    .stExpander > div[data-testid="stExpanderHeader"] {
        color: #00ffcc;
    }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# Sidebar with usage explanation
with st.sidebar:
    st.markdown("<h2>How to Use WaterSeeker Agent</h2>", unsafe_allow_html=True)
    st.markdown("""
        <div class="card">
        <h3>Step-by-Step Guide</h3>
        <ul>
            <li><strong>Select Locations:</strong> Click on the map on the right to add up to 5 locations. A popup will display the latitude and longitude of each click. Selected locations are listed below the map.</li>
            <li><strong>Analyze Resources:</strong> Once you’ve selected at least 2 locations, click the '🔍 Analyze Water Resources' button. The app will use AI to analyze water resources and provide a recommendation.</li>
            <li><strong>Review Results:</strong> Explore the 'Agent's Process' log, 'Analysis' details, 'Recommendation', 'Results Map' (with the recommended location in green), and comparison plots for capacity and rainfall.</li>
            <li><strong>Provide Feedback:</strong> Rate the recommendation (1-5 stars) and add comments to help us improve. Submit your feedback and view the response.</li>
            <li><strong>Clear Points:</strong> Use the '🗑️ Clear Points' button to reset and start over.</li>
        </ul>
        </div>
    """, unsafe_allow_html=True)

# API Keys
OPENWEATHERMAP_API_KEY = st.secrets["OPENWEATHERMAP_API_KEY"]

# Initialize Nominatim geocoder with a user agent
geolocator = Nominatim(user_agent="WaterSeekerAgent")

# Function to get country and city using geopy with Nominatim
def get_location_details(lat, lon):
    try:
        # Respect Nominatim's rate limit (1 request per second)
        time.sleep(1)
        location = geolocator.reverse((lat, lon), language="en")
        if location and location.raw and "address" in location.raw:
            address = location.raw["address"]
            city = address.get("city", address.get("town", address.get("village", "Unknown")))
            country = address.get("country", "Unknown")
            return city, country
        return "Unknown", "Unknown"
    except Exception as e:
        st.warning(f"Error fetching location details: {str(e)}")
        return "Unknown", "Unknown"

# Function to get detailed weather data using OpenWeatherMap API
def get_weather_data(lat, lon):
    url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        weather_info = {
            "rain_1h": data.get("rain", {}).get("1h", 0),  # Rainfall in the last 1 hour (mm)
            "rain_3h": data.get("rain", {}).get("3h", 0),  # Rainfall in the last 3 hours (mm)
            "humidity": data.get("main", {}).get("humidity", 0),  # Humidity (%)
            "cloud_cover": data.get("clouds", {}).get("all", 0),  # Cloudiness (%)
            "temperature": data.get("main", {}).get("temp", 0),  # Temperature (°C)
            "wind_speed": data.get("wind", {}).get("speed", 0),  # Wind speed (m/s)
            "wind_direction": data.get("wind", {}).get("deg", 0),  # Wind direction (degrees)
            "pressure": data.get("main", {}).get("pressure", 0),  # Pressure (hPa)
            "weather_description": data.get("weather", [{}])[0].get("description", "N/A"),  # Weather description
        }
        return weather_info
    except Exception as e:
        st.warning(f"Error fetching weather data: {str(e)}")
        return {
            "rain_1h": 0,
            "rain_3h": 0,
            "humidity": 0,
            "cloud_cover": 0,
            "temperature": 0,
            "wind_speed": 0,
            "wind_direction": 0,
            "pressure": 0,
            "weather_description": "N/A",
        }

# Initialize session state variables
if "points" not in st.session_state:
    st.session_state.points = []
if "results" not in st.session_state:
    st.session_state.results = None
if "feedback_submitted" not in st.session_state:
    st.session_state.feedback_submitted = False
if "feedback_message" not in st.session_state:
    st.session_state.feedback_message = ""

default_center = [35.0, -78.0]
center = st.session_state.points[-1] if st.session_state.points else default_center
m = folium.Map(location=center, zoom_start=6)
folium.LatLngPopup().add_to(m)
for i, (lat, lon) in enumerate(st.session_state.points):
    folium.Marker(
        [lat, lon],
        popup=f"Location {i+1}",
        icon=folium.Icon(color="blue")
    ).add_to(m)

map_data = st_folium(m, width=700, height=400, key="input_map", returned_objects=["last_clicked"])
if map_data and "last_clicked" in map_data and map_data["last_clicked"]:
    click = map_data["last_clicked"]
    point = (click["lat"], click["lng"])
    if point not in st.session_state.points and len(st.session_state.points) < 5:
        st.session_state.points.append(point)
        st.rerun()
    elif len(st.session_state.points) >= 5:
        st.error("Max 5 locations allowed.")

st.subheader("📍 Selected Locations")
if st.session_state.points:
    for i, (lat, lon) in enumerate(st.session_state.points):
        city, country = get_location_details(lat, lon)
        st.write(f"Location {i+1}: (lat: {lat:.2f}, lon: {lon:.2f}) - {city}, {country}")
    if st.button("🗑️ Clear Points"):
        st.session_state.points = []
        st.session_state.results = None
        st.session_state.feedback_submitted = False
        st.session_state.feedback_message = ""
        st.rerun()
else:
    st.write("Click the map to add up to 5 locations.")

# Require at least 2 locations for a recommendation
min_locations_for_recommendation = 2
if st.button("🔍 Analyze Water Resources") and st.session_state.points:
    if len(st.session_state.points) < min_locations_for_recommendation:
        st.warning(f"Please select at least {min_locations_for_recommendation} locations to enable a recommendation. Currently, {len(st.session_state.points)} location(s) selected.")
        with st.spinner("Analyzing with watsonx.ai..."):
            try:
                analysis, recommendation, coords, agent_log, water_resources = run_waterseeker_agent(st.session_state.points)
                recommendation = "Recommendation not available: Please select more locations for comparison."
                st.session_state.results = (analysis, recommendation, coords, agent_log, water_resources)
            except Exception as e:
                st.error(f"Error: {str(e)}")
    else:
        with st.spinner("Analyzing locations and fetching water resource data..."):
            try:
                analysis, recommendation, coords, agent_log, water_resources = run_waterseeker_agent(st.session_state.points)
                if not recommendation:
                    recommendation = "- No recommendation: Failed to generate a valid recommendation."
                st.session_state.results = (analysis, recommendation, coords, agent_log, water_resources)
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Check if results exist before accessing
if st.session_state.results is not None:
    analysis, recommendation, coords, agent_log, water_resources = st.session_state.results
    
    # Display the agent's process in a textarea
    st.subheader("🤖 Agent's Process")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    filtered_log = "\n".join(line for line in agent_log.split("\n") if "missing ScriptRunContext" not in line)
    st.text_area("Agent Log", filtered_log, height=300)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Analysis with expandable sections
    st.subheader("📊 Analysis")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if "Error: Analysis includes" in analysis:
        st.warning("Analysis parsing failed. Displaying raw analysis data.")
        raw_analysis = []
        log_lines = agent_log.split("\n")
        in_analysis = False
        for line in log_lines:
            if "✅ Analysis complete:" in line:
                in_analysis = True
                continue
            if in_analysis and line.startswith("🔍"):
                break
            if in_analysis and line.strip():
                raw_analysis.append(line)
        if raw_analysis:
            st.markdown("\n".join(raw_analysis).replace("\n", "<br>"), unsafe_allow_html=True)
        else:
            st.error("No analysis data available.")
    else:
        analysis_lines = [line.strip() for line in analysis.split("\n") if line.strip()]
        formatted_analysis = [f"- {line[2:]}" if line.startswith("- ") else f"- {line}" for line in analysis_lines]
        for i, line in enumerate(formatted_analysis):
            with st.expander(f"Location {i+1} Details"):
                st.markdown(line.replace("\n", "<br>"), unsafe_allow_html=True)
                if i < len(water_resources):
                    st.write(f"**Water Resources**: {water_resources[i]}")
                else:
                    st.write("**Water Resources**: Data not available.")
                # Fetch detailed weather data
                lat, lon = coords[i] if i < len(coords) else (0, 0)
                weather_data = get_weather_data(lat, lon)
                st.write("**Current Weather Conditions**:")
                st.write(f"- Recent Rainfall (last 1 hour): {weather_data['rain_1h']} mm")
                st.write(f"- Recent Rainfall (last 3 hours): {weather_data['rain_3h']} mm")
                st.write(f"- Humidity: {weather_data['humidity']}%")
                st.write(f"- Cloud Cover: {weather_data['cloud_cover']}%")
                st.write(f"- Temperature: {weather_data['temperature']}°C")
                st.write(f"- Wind Speed: {weather_data['wind_speed']} m/s")
                st.write(f"- Wind Direction: {weather_data['wind_direction']}°")
                st.write(f"- Atmospheric Pressure: {weather_data['pressure']} hPa")
                st.write(f"- Weather Description: {weather_data['weather_description'].capitalize()}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display recommendation
    st.subheader("✅ Recommendation")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if recommendation.startswith("Error:"):
        st.error(recommendation)
    else:
        rec_lines = recommendation.split("\n")
        cleaned_rec_lines = []
        for line in rec_lines:
            if "Rainfall:" in line and "Capacity:" in line:
                line = re.sub(r": Rainfall: \d+mm/year, Capacity: \d+M liters", "", line)
            cleaned_rec_lines.append(line)
        cleaned_recommendation = "\n".join(cleaned_rec_lines)
        st.markdown(cleaned_recommendation.replace("\n", "<br>"), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Determine the recommended location index
    recommended_index = -1
    if not recommendation.startswith("Error:") and "Recommended: Location" in recommendation:
        rec_match = re.search(r"Recommended: Location (\d+)", recommendation)
        if rec_match:
            recommended_index = int(rec_match.group(1)) - 1

    # Results Map with tooltips
    map_center = coords[recommended_index] if recommended_index != -1 and recommended_index < len(coords) else coords[0] if coords else default_center
    result_map = folium.Map(location=map_center, zoom_start=6)
    capacities = []
    rainfalls = []
    analysis_lines = [line.strip() for line in analysis.split("\n") if line.strip() and line.startswith("- Location")]
    for i, line in enumerate(analysis_lines):
        try:
            rainfall_match = re.search(r"Rainfall: (\d+\.?\d*)mm/year", line)
            capacity_match = re.search(r"Capacity: (\d+\.?\d*)M liters", line)
            rainfall = float(rainfall_match.group(1)) if rainfall_match else 0
            capacity = float(capacity_match.group(1)) if capacity_match else 0
        except (IndexError, ValueError, AttributeError) as e:
            rainfall, capacity = 0, 0
        capacities.append(capacity)
        rainfalls.append(rainfall)
        lat, lon = coords[i] if i < len(coords) else (0, 0)
        city, country = get_location_details(lat, lon)
        water_info = water_resources[i] if i < len(water_resources) else "Data not available."
        weather_data = get_weather_data(lat, lon)
        popup_content = f"""
        <b>Location {i+1}</b><br>
        Lat: {lat:.2f}, Lon: {lon:.2f}<br>
        Country: {country}<br>
        City: {city}<br>
        Rainfall: {rainfall}mm/year<br>
        Recent Rainfall (last 1h): {weather_data['rain_1h']}mm<br>
        Recent Rainfall (last 3h): {weather_data['rain_3h']}mm<br>
        Humidity: {weather_data['humidity']}% <br>
        Cloud Cover: {weather_data['cloud_cover']}% <br>
        Temperature: {weather_data['temperature']}°C <br>
        Wind: {weather_data['wind_speed']} m/s, {weather_data['wind_direction']}° <br>
        Pressure: {weather_data['pressure']} hPa <br>
        Weather: {weather_data['weather_description'].capitalize()} <br>
        Capacity: {capacity}M liters<br>
        Water Resources: {water_info}<br>
        Country Info: Population ~{int(lat*1e6):,} (simulated)<br>
        Reservoir Status: Active (simulated)
        """
        color = "green" if i == recommended_index else "blue"
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_content, max_width=300),
            icon=folium.Icon(color=color),
            tooltip=f"Location {i+1}: {country}, {city}"
        ).add_to(result_map)
    st.subheader("📍 Results Map")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st_folium(result_map, width=700, height=400, key="result_map")
    st.markdown('</div>', unsafe_allow_html=True)

    # Plot Capacities
    st.subheader("📈 Reservoir Capacity Comparison")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    try:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=100)
        bars = ax.bar(
            [f"Loc {i+1}" for i in range(len(capacities))],
            capacities,
            color=["green" if i == recommended_index else "blue" for i in range(len(capacities))]
        )
        ax.set_xlabel("Location")
        ax.set_ylabel("Capacity (M liters)")
        ax.set_title("Reservoir Capacity by Location")
        ax.set_ylim(0, max(capacities) * 1.2 if capacities else 1)
        ax.grid(True, linestyle="--", alpha=0.7)
        for bar in bars:
            yval = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, yval + 0.3, f"{yval}M", ha="center", va="bottom", color="black")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode()
        st.image(f"data:image/png;base64,{img_str}")
        plt.close(fig)
    except Exception as e:
        st.error(f"Failed to generate capacity plot: {str(e)}")
    st.markdown('</div>', unsafe_allow_html=True)

    # Plot Rainfall
    st.subheader("🌧️ Rainfall Comparison")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    try:
        fig, ax = plt.subplots(figsize=(8, 6), dpi=100)
        bars = ax.bar(
            [f"Loc {i+1}" for i in range(len(rainfalls))],
            rainfalls,
            color=["green" if i == recommended_index else "blue" for i in range(len(rainfalls))]
        )
        ax.set_xlabel("Location")
        ax.set_ylabel("Rainfall (mm/year)")
        ax.set_title("Rainfall by Location")
        ax.set_ylim(0, max(rainfalls) * 1.2 if rainfalls else 1)
        ax.grid(True, linestyle="--", alpha=0.7)
        for bar in bars:
            yval = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, yval + 50, f"{int(yval)}mm", ha="center", va="bottom", color="black")
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode()
        st.image(f"data:image/png;base64,{img_str}")
        plt.close(fig)
    except Exception as e:
        st.error(f"Failed to generate rainfall plot: {str(e)}")
    st.markdown('</div>', unsafe_allow_html=True)

    # Feedback Section
    st.subheader("📝 Provide Feedback")
    st.markdown('<div class="card">', unsafe_allow_html=True)
    if not st.session_state.feedback_submitted:
        with st.form("feedback_form"):
            rating = st.slider("Rate the recommendation (1-5 stars)", 1, 5, 3)
            comments = st.text_area("Comments (optional)", placeholder="Let us know your thoughts!")
            submit_button = st.form_submit_button("Submit Feedback")
            if submit_button:
                st.session_state.feedback_submitted = True
                if rating >= 4:
                    message = f"Agent: Thank you for your feedback! We’re thrilled you rated the recommendation {rating}/5. Comments: {comments if comments else 'None'}. We’ll keep improving!"
                elif rating >= 2:
                    message = f"Agent: Thank you for your feedback! You rated the recommendation {rating}/5. Comments: {comments if comments else 'None'}. We’ll work on addressing your concerns."
                else:
                    message = f"Agent: Thank you for your feedback. We’re sorry you rated the recommendation {rating}/5. Comments: {comments if comments else 'None'}. We’ll strive to do better!"
                st.session_state.feedback_message = message
                st.rerun()
    else:
        st.write(st.session_state.feedback_message)
        if st.button("Submit New Feedback"):
            st.session_state.feedback_submitted = False
            st.session_state.feedback_message = ""
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
st.write("Built for IBM watsonx.ai Hackathon - Clean Water Challenge | Powered by Granite-3-8B")
st.write("Geolocation data provided by Nominatim, using OpenStreetMap data. © OpenStreetMap contributors.")
st.write("Weather data provided by OpenWeatherMap.")