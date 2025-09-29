import streamlit as st
import ee
import json
import base64
import folium
from streamlit_folium import st_folium



import tempfile

# --- 1. Load credentials ---
SERVICE_ACCOUNT = st.secrets["gee"]["service_account"]
PRIVATE_KEY_B64 = st.secrets["gee"]["private_key"]

# Decode Base64 into JSON string
decoded = base64.b64decode(PRIVATE_KEY_B64).decode("utf-8")

# --- 2. Write to temporary file ---
with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as f:
    f.write(decoded)
    temp_path = f.name

# --- 3. Initialize Earth Engine ---
try:
    credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, temp_path)
    ee.Initialize(credentials)
    st.success(f"✅ Earth Engine initialized for: {SERVICE_ACCOUNT}")
except Exception as e:
    st.error(f"❌ Failed to initialize Earth Engine: {e}")
    st.stop()


st.set_page_config(page_title="Streamlit + Earth Engine", layout="wide")

st.title("🌍 Earth Engine Streamlit App")


# --- 3. Example: List available Sentinel-2 images ---
try:
    region = ee.Geometry.Point([12.4924, 41.8902])  # Rome
    dataset = ee.ImageCollection("COPERNICUS/S2") \
        .filterBounds(region) \
        .filterDate("2024-01-01", "2024-02-01") \
        .limit(5)

    count = dataset.size().getInfo()
    st.write(f"🛰️ Found {count} Sentinel-2 images near Rome (Jan 2024).")

    # Display some image IDs
    images = dataset.aggregate_array("system:id").getInfo()
    st.write(images)

except Exception as e:
    st.error(f"Error querying Earth Engine: {e}")

# --- 4. Example: Display a simple map ---
try:
    # Pick one image to visualize
    image = ee.Image("COPERNICUS/S2/20240101T101031_20240101T101029_T32TNR") \
        .select(["B4", "B3", "B2"])  # RGB

    vis_params = {"min": 0, "max": 3000, "gamma": 1.4}
    map_center = [41.9, 12.5]

    m = folium.Map(location=map_center, zoom_start=8)
    m.add_ee_layer(image, vis_params, "Sentinel-2 RGB")

    st_folium(m, width=800, height=500)

except Exception as e:
    st.error(f"Error displaying map: {e}")

# --- 5. Helper to support Earth Engine layers in folium ---
def add_ee_layer(self, ee_object, vis_params, name):
    try:
        map_id_dict = ee.Image(ee_object).getMapId(vis_params)
        folium.raster_layers.TileLayer(
            tiles=map_id_dict["tile_fetcher"].url_format,
            attr="Map Data © Google Earth Engine",
            name=name,
            overlay=True,
            control=True
        ).add_to(self)
    except Exception as e:
        st.error(f"Error adding EE layer: {e}")

folium.Map.add_ee_layer = add_ee_layer