import numpy as np
from math import radians, cos, sin, asin, sqrt, degrees, atan2
from shapely.geometry import Point, Polygon, MultiPolygon
from shapely.ops import unary_union
import folium
from folium.features import DivIcon
import smtplib
from email.message import EmailMessage
import os
from branca.element import Template, MacroElement
from dotenv import load_dotenv
load_dotenv()

GMAIL_ADDRESS = os.environ.get('GMAIL_ADDRESS')
GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD')

def glide_range(altitude, arrival_altitude, glide_ratio, safety_margin, Vg, wind_speed, wind_direction, heading):
    """
    Calculate the glide range of an aircraft in the presence of wind.

    Parameters:
    altitude (float): The initial altitude from which the aircraft starts to glide in feet.
    arrival_altitude (float): The arrival altitude at the center location in feet.
    glide_ratio (float): The glide ratio of the aircraft.
    Vg (float): The glide speed of the aircraft in still air in knots.
    wind_speed (float): The speed of the wind in knots.
    wind_direction (float): The direction from which the wind is coming, in degrees.
    heading (float): The heading of the aircraft, in degrees.

    Returns:
    float: The glide range of the aircraft in nautical miles from the initial altitude
      from which the aircraft starts to glide to the arrival altitude.
    """
    initial_altitude = altitude - arrival_altitude

    # Convert speeds from knots to feet/s
    Vg = Vg * 1.68781
    wind_speed = wind_speed * 1.68781

    # Reverse wind direction
    wind_direction = (wind_direction + 180) % 360

    # Calculate the difference between the wind direction and the heading
    angle_diff = np.radians(wind_direction - heading)

    # Calculate the effective wind speed
    Vw = wind_speed * np.cos(angle_diff)

    safety_margin = 1 - safety_margin

    # Set a minimum safety margin to avoid multiplying by zero
    MIN_SAFETY_MARGIN = 0.01
    safety_margin = max(safety_margin, MIN_SAFETY_MARGIN)

    # Calculate the glide ratio in the presence of wind
    glide_ratio_wind = ((Vg - Vw) / Vg) * glide_ratio * safety_margin

    # Calculate the glide range in feet
    glide_range_wind_ft = initial_altitude * glide_ratio_wind

    # Convert the glide range to nautical miles
    glide_range_wind_nm = glide_range_wind_ft / 6076.12

    return glide_range_wind_nm

def haversine(lon1, lat1, d, brng):
    """
    Calculate the new coordinates given a starting point, distance and bearing
    """
    R = 3440.069 #Radius of the Earth in nautical miles
    brng = radians(brng) #convert bearing to radians

    lat1 = radians(lat1) #Current lat point converted to radians
    lon1 = radians(lon1) #Current long point converted to radians

    lat2 = asin( sin(lat1)*cos(d/R) + cos(lat1)*sin(d/R)*cos(brng) )

    lon2 = lon1 + atan2(sin(brng)*sin(d/R)*cos(lat1), cos(d/R)-sin(lat1)*sin(lat2))

    lat2 = degrees(lat2)
    lon2 = degrees(lon2)

    return [lat2, lon2]

def plot_map(lat1, lon1, glide_ratio, safety_margin, Vg, center_locations, polygon_altitudes,  \
    arrival_altitude_agl, selected_glider,wind_speed,wind_direction):
    """
    Plots a map using Folium library with markers and polygons based on the input parameters.

    Args:
    lat1 (float): Latitude of the center of the map.
    lon1 (float): Longitude of the center of the map.
    glide_ratio (float): The glide ratio of the aircraft.
    safety_margin (float): The safety margin to be added to the glide range.
    Vg (float): The ground speed of the aircraft.
    center_locations (list): A list of tuples containing the location information of the center points.
    polygon_altitudes (list): A list of altitudes for which polygons need to be drawn.
    arrival_altitude_agl (float): The arrival altitude above ground level.

    Returns:
    str: The HTML code for the rendered map.
    """
    m = folium.Map(location=[lat1, lon1], tiles=None, zoom_start=10)
    folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite', overlay=False, control=True).add_to(m)
    folium.TileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Topographic', overlay=False, control=True).add_to(m)
    folium.TileLayer('https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/VFR_Sectional/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='VFR Sectional', overlay=False, control=True).add_to(m)
    folium.LayerControl().add_to(m)

    for altitude in polygon_altitudes:
        polygons_points = []

        for lat, lon, polygon_altitude, wind_speed, wind_direction, arrival_altitude_msl, name, type, description in center_locations:
            folium.Marker(
                location=[lat, lon],
                popup=f"{name}\nType: {type}\nArrival Alt: {arrival_altitude_msl}ft\nLocation Alt: {arrival_altitude_msl-arrival_altitude_agl}ft\nDescription: {description}",
                icon=folium.Icon(icon="plane-arrival", prefix='fa')
            ).add_to(m)
            # Only calculate the polygon rings for altitudes above arrival altitude and the location type is not a turnpoint
            if altitude >= arrival_altitude_msl and type != "T":
                polygon_points = []
                for heading in range(0, 360, 10):
                    range_nm = glide_range(altitude, arrival_altitude_msl, glide_ratio, safety_margin, Vg, wind_speed, wind_direction, heading)
                    new_point = haversine(lon, lat, range_nm, heading)
                    polygon_points.append(new_point)

                polygons_points.append(polygon_points)

        # Merge the polygons using a union operation
        merged_polygon = unary_union([Polygon(polygon_points) for polygon_points in polygons_points])

        # Handle both Polygon and MultiPolygon cases
        merged_polygons = list(merged_polygon.geoms) if isinstance(merged_polygon, MultiPolygon) else [merged_polygon]

        for merged_polygon in merged_polygons:
            # Only proceed if the geometry is a Polygon
            if isinstance(merged_polygon, Polygon):
                # Convert the merged polygon back to a list of points
                merged_polygon_points = [list(point) for point in merged_polygon.exterior.coords]
                # Draw the merged polygon on the map
                folium.Polygon(locations=merged_polygon_points, color='blue', fill=False).add_to(m)

                label_locs = [1, 10, 19, 28] # bearing of the label locations
                for loc in label_locs:
                    # Add a label with the altitude at the label locations
                    folium.Marker(
                      location=merged_polygon_points[loc],
                      icon=DivIcon(
                          icon_size=(150,36),
                          icon_anchor=(0,0),
                          html='<div style="font-size: 12pt; color: yellow; text-shadow: -1px 0 black, 0 1px black, 1px 0 black, 0 -1px black;">%s ft</div>' % (altitude),
                      )
                    ).add_to(m)

    #Display input values on map
    template = get_input_parms_display(selected_glider, glide_ratio, Vg, safety_margin * 100, \
                                       wind_speed,wind_direction, arrival_altitude_agl)
    macro = MacroElement()
    macro._template = Template(template)
    m.get_root().add_child(macro)


    return m.get_root().render()

def send_email(to_email, subject, content):
    """Send email using SMTP."""
    msg = EmailMessage()
    msg.set_content(content)
    msg['Subject'] = subject
    msg['From'] = GMAIL_ADDRESS
    msg['To'] = to_email

    # Connect to Gmail's SMTP server
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        server.send_message(msg)

## Original source from https://nbviewer.org/gist/talbertc-usgs/18f8901fc98f109f2b71156cf3ac81cd
# and modified as needed
def get_input_parms_display(selected_glider, glide_ratio, vg, safety_margin, wind_speed,wind_direction, arrival_altitude_agl):
    template = f"""
        {{% macro html(this, kwargs) %}}
        
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>jQuery UI Draggable - Default functionality</title>
          <link rel="stylesheet" href="//code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">
        
          <script src="https://code.jquery.com/jquery-1.12.4.js"></script>
          <script src="https://code.jquery.com/ui/1.12.1/jquery-ui.js"></script>
          
          <script>
          $( function() {{
            $( '#parameterslegend' ).draggable({{
                            start: function (event, ui) {{
                                $(this).css({{
                                    right: 'auto',
                                    top: 'auto',
                                    bottom: 'auto'
                                }});
                            }}
                        }});
        }});
        
          </script>
        </head>
        <body>
        
         
        <div id='parameterslegend' class='parameterslegend' 
            style='position: absolute; z-index:9999; border:2px solid grey; background-color:rgba(255, 255, 255, 0.8);
             border-radius:6px; padding: 10px; font-size:14px; right: 20px; bottom: 20px;'; >
             
        <div class='parameters-title'>Input Values</div>
        <div class='parameters-scale'>
          <ul class='parameters-labels'>
          <p>{selected_glider}<br>
          Max L/D: {glide_ratio} at: {vg} kts<br>
          Safety Margin over best L/D: {safety_margin}%<br>
          Wind spd: {wind_speed}kts at: {wind_direction}degs<br>
          Arrival alt: {arrival_altitude_agl}ft AGL
          </p>
          </ul>
        </div>
        </div>
         
        </body>
        </html>
        
        <style type='text/css'>
          .parameterslegend .parameters-title {{
            text-align: left;
            margin-bottom: 5px;
            font-weight: bold;
            font-size: 90%;
            }}
          .parameterslegend .parameters-scale ul {{
            margin: 0;
            margin-bottom: 5px;
            padding: 0;
            float: left;
            list-style: none;
            }}
          .parameterslegend .parameters-scale ul li {{
            font-size: 80%;
            list-style: none;
            margin-left: 0;
            line-height: 18px;
            margin-bottom: 2px;
            }}
          .parameterslegend ul.parameters-labels li span {{
            display: block;
            float: left;
            height: 16px;
            width: 30px;
            margin-right: 5px;
            margin-left: 0;
            border: 1px solid #999;
            }}
          .parameterslegend .parameters-source {{
            font-size: 80%;
            color: #777;
            clear: both;
            }}
          .parameterslegend a {{
            color: #777;
            }}
        </style>
        {{% endmacro %}}"""
    return template