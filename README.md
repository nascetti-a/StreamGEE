# **Building a Dynamic Geospatial App with Streamlit and Google Earth Engine**

**Title: From Satellite to Streamlit: Analyzing Cloudiness Over Europe's Capitals**

Have you ever wanted to build a dynamic web application that analyzes satellite data in real-time? This tutorial walks through creating a Python app using Streamlit and the powerful Google Earth Engine (GEE) platform, allowing users to select a European capital, filter Sentinel-2 imagery by cloud cover, and visualize the resulting cloud-free composite and the cloudiness history.

Here is the complete, runnable Python code, followed by a step-by-step breakdown of how it works.

*(Note: The full code is available in the Canvas app.py file)*

## **Step 1: Setting up Authentication (The Secret Sauce)**

The most critical and often confusing step when using GEE in a production environment like a web app is authentication. We must securely handle the GEE service account key.

### **A. Obtain the Service Account Key (key.json)**

To allow your Streamlit app to access Earth Engine, you need a service account JSON key from your Google Cloud Project:

1. **Create a Service Account:** Navigate to the **IAM & Admin** section of your Google Cloud Console, select **Service accounts**, and create a new account.  
2. **Assign Roles:** Ensure the service account is granted the necessary roles to access your Earth Engine project (at minimum, it needs the **Earth Engine Resource User** role).  
3. **Generate the Key:** Under the service account details, go to the **Keys** tab and select **Add Key \> Create new key**. Choose the **JSON** type and download the file. This file, typically named something like your-project-id-randomhash.json, is your key.json.

### **B. Base64 Encode the Key (For Security)**

**Importance of Secrets:** The JSON key contains your private credentials, granting access to your GEE resources. It is **critical** that this file's contents are never committed to a public GitHub repository. By converting the key to a Base64 string, we can store it safely within Streamlit's secrets management, which is often excluded from version control.

Use your terminal to convert the contents of your downloaded JSON file into a single, encoded string:

```commandline
cat /path/to/your/key.json | base64
```

Copy the long output string that this command generates.

### **C. Configure Streamlit Secrets (.streamlit/secrets.toml)**

Your Streamlit secrets file will use the service account email and the long Base64 string you just generated:

```python
[gee]  
service_account = "your-gee-service-account-id@project.iam.gserviceaccount.com"  
private_key = "PASTE_THE_LONG_BASE64_STRING_HERE"
```


### **D. Decoding and Initializing Earth Engine (Python)**

The Python code retrieves the Base64-encoded key from the Streamlit secrets, decodes it, writes it temporarily to a file (as required by the GEE library), initializes the connection, and then deletes the temporary file for security.

```python
# --- Initialize EE (using the temporary file method) ---
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

    st.success(f"✅ Earth Engine initialized successfully.")
except Exception as e:
    st.error(f"❌ Error initializing Earth Engine. Check your Streamlit secrets configuration. Error: {e}")
    st.stop()
```

## **Step 2: Defining the User Interface**

We use Streamlit's sidebar for all user inputs, keeping the main screen clean for the map and analysis.

1. **Capital Selection:** We define a dictionary of European capitals and their coordinates, feeding the keys to a st.selectbox. 

```python
   EUROPEAN_CAPITALS = {  
       "Paris, France": (2.3522, 48.8566),  
       # ... other capitals  
   }  
   selected_city = st.sidebar.selectbox("1. Select a European Capital:", options=list(EUROPEAN_CAPITALS.keys()))
```


2. **Date and Cloud Filters:** We use datetime.date objects for compatibility with Streamlit's st.date_input and a slider for cloud percentage control.  

```python
   start_date = st.date_input("2. Start Date:", value=datetime.date(2023, 9, 1))  
   end_date = st.date_input("3. End Date:", value=datetime.date(2024, 3, 1))  
   cloud_filter = st.sidebar.slider("4. Max Cloud Filter (%):", value=15)
```
## **Step 3: Filtering Geospatial Data with Earth Engine**

This is where we connect the user inputs to the GEE platform.

1. **Define Area of Interest (AOI):** We take the selected capital's coordinates and create an ee.Geometry.Point, then use .buffer(25000) to create a 25 km radius area around the city.  
2. **Filter the Image Collection:** We query the Sentinel-2 (S2) collection using the user-defined parameters:  
   * `.filterDate()`: Uses the selected start and end dates.  
   * `.filterBounds()`: Filters images to only include those overlapping the 25km AOI.  
   * `.filterMetadata()`: This filters out images where the CLOUDY_PIXEL_PERCENTAGE property exceeds the user's maximum cloud filter.

```python
city\_point \= ee.Geometry.Point(\[lon, lat\])  
aoi \= city\_point.buffer(25000)

s2\_collection \= ee.ImageCollection("COPERNICUS/S2\_HARMONIZED") \\  
    .filterDate(start\_date.isoformat(), end\_date.isoformat()) \\  
    .filterBounds(aoi) \\  
    .filterMetadata('CLOUDY\_PIXEL\_PERCENTAGE', 'less\_than', cloud\_filter)
```
3. **Generate Composite and Metrics:** We generate the final cloud-free composite by taking the pixel-wise **median** of the filtered collection. We also calculate the mean cloudiness for analysis.  

```python
    s2_composite = s2_collection.median()  
    mean_cloud_percentage = s2_collection.aggregate_mean('CLOUDY\_PIXEL\_PERCENTAGE').getInfo()
```

## **Step 4: Visualizing Cloudiness Over Time**

To plot the cloudiness for *each* individual image used in the composite, we need to extract the metadata from GEE and transfer it to a Pandas DataFrame.

1. **Extract Metadata:** We use `s2_collection.toList(collection_size).getInfo()` to pull a list of image properties (blocking call).  
2. **Process with Pandas:** We loop through the list, extract the acquisition date (timestamp in milliseconds) and the cloudiness percentage, convert the timestamp to a proper datetime object, and create a DataFrame.  
  
```python
    # ... inside else: block  
   feature_list = s2_collection.toList(collection_size).getInfo()  
   # ... data\_for\_df population

   df = pd.DataFrame(data_for_df)  
   # Convert Earth Engine Unix timestamp (milliseconds) to datetime  
   df['Acquisition Date'] = pd.to_datetime(df['Acquisition Date'], unit='ms')  
   df = df.set_index('Acquisition Date').sort_index()
``` 

3. **Plotting:** We use Streamlit's simple and efficient bar chart function to show the data.  

```python
   st.subheader("Cloudiness Over Time")  
   st.bar_chart(df['Cloudiness (%)']) 
```
## **Step 5: Displaying the Map**

Finally, we use the geemap library (a wrapper around folium) to display the results.

1. **Initialize Map:** `Map = geemap.Map(center=[lat, lon], zoom=11)` centers the map on the selected city.  
2. **Add Composite Layer:** `Map.addLayer(s2_composite, vis_params, ...)` adds the final median composite image using Natural Color RGB visualization parameters.  
3. **Add Context:** We add a marker for the city center and a red boundary for the 25km AOI.  
4. **Render:** `Map.to_streamlit()` embeds the interactive map into the application layout.

This framework provides a robust and secure way to build complex geospatial analysis applications, leveraging the power of Google Earth Engine with the interactive capabilities of Streamlit.

Would you like to explore adding another visualization, like a chart showing the average NDVI (Normalized Difference Vegetation Index) over time?