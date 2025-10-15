import streamlit as st
import ee
import geemap.foliumap as geemap
import base64
import json
import tempfile
import os
import datetime
import pandas as pd  # Added for data manipulation and plotting
import altair as alt  # Added for custom chart coloring

# --- Configuration ---
st.set_page_config(layout="wide")
st.title("🇪🇺 European Capitals Satellite Viewer")

# Define a list of major European capitals and their coordinates (Lon, Lat)
EUROPEAN_CAPITALS = {
    "Rome, Italy": (12.4964, 41.9028),
    "Stockholm, Sweden": (18.0656, 59.3327),
    "Paris, France": (2.3522, 48.8566),
    "Berlin, Germany": (13.4050, 52.5200),
    "London, UK": (-0.1278, 51.5074),
    "Madrid, Spain": (-3.7038, 40.4168),
    "Vienna, Austria": (16.3738, 48.2082),
    "Athens, Greece": (23.7275, 37.9838),
    "Warsaw, Poland": (21.0118, 52.2297),
    "Amsterdam, Netherlands": (4.8952, 52.3702),
    "Oslo, Norway": (10.7522, 59.9139),
    "Lisbon, Portugal": (-9.1393, 38.7223),
}

# --- Initialize EE (using the temporary file method) ---


@st.cache_resource
def initialize_ee_session():
    """Initializes the Earth Engine session and caches the result."""
    try:
        # Ensure secrets are available
        SERVICE_ACCOUNT = st.secrets["gee"]["service_account"]
        PRIVATE_KEY_B64 = st.secrets["gee"]["private_key"]

        # Decode the private key and write it to a temporary file for ee.Initialize
        decoded = base64.b64decode(PRIVATE_KEY_B64).decode("utf-8")
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as f:
            f.write(decoded)
            temp_path = f.name

        credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, temp_path)
        ee.Initialize(credentials)
        os.remove(temp_path)

        return True
    except Exception as e:
        st.error(f"❌ Error initializing Earth Engine. Check your Streamlit secrets configuration. Error: {e}")
        return False


# Run the initialization only once
if initialize_ee_session():
    st.success(f"✅ Earth Engine initialized successfully (Cached).")
else:
    st.stop()


# --- User Inputs ---
st.sidebar.image("image/logo.png")

st.sidebar.header("Controls")

selected_city = st.sidebar.selectbox(
    "1. Select a European Capital:",
    options=list(EUROPEAN_CAPITALS.keys())
)

col1, col2 = st.sidebar.columns(2)
with col1:
    # Fixed: Use datetime.date for Streamlit compatibility
    start_date = st.date_input("2. Start Date:", value=datetime.date(2023, 9, 1))
with col2:
    # Fixed: Use datetime.date for Streamlit compatibility
    end_date = st.date_input("3. End Date:", value=datetime.date(2024, 3, 1))

cloud_filter = st.sidebar.slider(
    "4. Max Cloud Filter (%):",
    min_value=1,
    max_value=100,
    value=15
)

# --- Processing Logic ---

# Get selected city coordinates
lon, lat = EUROPEAN_CAPITALS[selected_city]
# Define a buffer around the city point (e.g., 25km radius)
city_point = ee.Geometry.Point([lon, lat])
aoi = city_point.buffer(25000)

# 1. Collection filtered ONLY by date and bounds (used for comprehensive plotting)
s2_unfiltered_collection = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
    .filterDate(start_date.isoformat(), end_date.isoformat()) \
    .filterBounds(aoi)

# 2. Collection filtered by date, bounds, AND cloud percentage (used for composite)
# This ensures only images under the cloud_filter threshold are used for the median composite.
s2_composite_collection = s2_unfiltered_collection \
    .filterMetadata('CLOUDY_PIXEL_PERCENTAGE', 'less_than', cloud_filter)

# Calculate the size of the *composite* collection (blocking call)
collection_size = s2_composite_collection.size().getInfo()
unfiltered_collection_size = s2_unfiltered_collection.size().getInfo()

try:
    if collection_size == 0:
        st.warning(
            f"⚠️ No Sentinel-2 images found for **{selected_city}** that meet the **{cloud_filter}%** max cloudiness filter. Try expanding the date range or increasing the cloud filter.")
        # Create a map centered on the city even if no image is found
        Map = geemap.Map(center=[lat, lon], zoom=11, plugin_Draw=False)
        Map.to_streamlit(width=800, height=500)
        st.stop()
    else:
        # Calculate the median composite image
        s2_composite = s2_composite_collection.median()

        # --- Data Extraction for Plotting (Using UNFILTERED Collection) ---
        # Get list of properties for each image in the UNFILTERED collection
        feature_list = s2_unfiltered_collection.toList(unfiltered_collection_size).getInfo()
        data_for_df = []
        for feature in feature_list:
            props = feature['properties']
            data_for_df.append({
                'Acquisition Date': props['system:time_start'],
                'Cloudiness (%)': props['CLOUDY_PIXEL_PERCENTAGE']
            })

        # Convert to Pandas DataFrame and format the date
        df = pd.DataFrame(data_for_df)
        # Convert Earth Engine Unix timestamp (milliseconds) to datetime objects
        df['Acquisition Date'] = pd.to_datetime(df['Acquisition Date'], unit='ms')
        df = df.set_index('Acquisition Date').sort_index()

        # Add color column based on the user's filter threshold (Blue <= threshold, Red > threshold)
        df['Color'] = df['Cloudiness (%)'].apply(
            lambda x: 'blue' if x <= cloud_filter else 'red'
        )

        # Calculate the average cloudiness of the source images (from the UNFILTERED set for proper reporting)
        mean_cloud_percentage = s2_unfiltered_collection.aggregate_mean('CLOUDY_PIXEL_PERCENTAGE').getInfo()

        # Display analysis results
        st.subheader(f"Data Analysis for {selected_city}")
        st.info(f"📸 Total available images (date/bounds filtered): **{unfiltered_collection_size}**")
        st.info(f"✅ Images used for composite (under {cloud_filter}% cloudiness): **{collection_size}**")
        st.info(f"☁️ Average Cloudiness of all available images: **{mean_cloud_percentage:.2f}%**")

        # --- PLOT CLOUDINESS OVER TIME with Conditional Colors using Altair ---
        st.subheader("Cloudiness Over Time vs. Filter Threshold")
        st.markdown(
            f"Bars are colored **blue** if cloudiness is below the **{cloud_filter}%** threshold (used for composite) and **red** if above.")

        # Define custom color scale to ensure blue and red are used
        color_scale = alt.Scale(domain=['blue', 'red'], range=['blue', 'red'])

        # Create the Altair chart
        chart = alt.Chart(df.reset_index()).mark_bar().encode(
            x=alt.X('Acquisition Date', title='Acquisition Date'),
            y=alt.Y('Cloudiness (%)', title='Cloudiness (%)'),
            color=alt.Color('Color', scale=color_scale),  # Use the pre-calculated color column
            tooltip=['Acquisition Date', 'Cloudiness (%)']
        ).properties(
            height=300
        ).interactive()  # Make the chart zoomable/pannable

        # Add a horizontal line to represent the user's cloud filter threshold
        rule = alt.Chart(pd.DataFrame({'y': [cloud_filter]})).mark_rule(color='green', strokeDash=[5, 5]).encode(
            y='y'
        )

        st.altair_chart(chart + rule, use_container_width=True)
        # --- END PLOT ---

        # Visualization parameters (Natural Color RGB)
        vis_params = {
            "bands": ["B4", "B3", "B2"],
            "min": 0,
            "max": 3000,
            "gamma": 1.4
        }

        # Create a map centered on the selected city
        Map = geemap.Map(center=[lat, lon], zoom=10)

        # Add the composite layer to the map
        Map.addLayer(s2_composite, vis_params, f"Sentinel-2 Composite: {selected_city}")

        # Add a marker for the capital city center
        Map.add_marker([lat, lon], tooltip=selected_city)
        #Map.add_ee_layer(aoi.bounds(), {'color': 'red'}, 'Area of Interest')

        # Display the map in Streamlit
        st.subheader("Satellite Composite Visualization")
        Map.to_streamlit(width=900, height=600)

except Exception as e:
    st.error(f"An Earth Engine error occurred during processing: {e}")

st.markdown("""
---
*Data Source: ESA Copernicus Sentinel-2 Level 2A data via Google Earth Engine.*
""")
