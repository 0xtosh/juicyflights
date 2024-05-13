import requests
import time
import json
import subprocess
from datetime import datetime
import requests
from bs4 import BeautifulSoup
api_key = 'f24api_key'

#####################################################################################################
# FlightRadar anomaly finder to find juicy flights >:)  -- Tom Van de Wiele
#
# Checks every 15 seconds:
# 1. Is a flight in the air that we can detect locally with dump1090-fa, but is NOT on Flightradar24 or FlightAware (administratively "hidden" flights)
# 2. Do we see fast acceleration or acceleration beyond the capabilities of a commercial airliner or light aircraft
# 3. Do we see fast climbing/descending beyond the capabilities of a commercial airliner or light aircraft
#
# If we get a change of 50 knots or 1000 feet difference within 30 seconds we run the ./alert command. Replace with your IRC/other bots
#
# If you do not want to use the paying FlightRadar24 API, comment out 4 lines at line 107
#
# Note: If you are receiving ADSB at an airport you will have to add error checking to not get alerted when planes take off/land
#####################################################################################################
#
# Flight Characteristics Background (MIGHT NEED TWEAKING)
# 
# 1. Commercial Jet Airliners
# - Acceleration/Deceleration: At a typical rate of 1 to 3 knots per second in 15 seconds slow down by approximately 15 to 45 knots
# - Climb Rate: The average initial climb rate for a commercial jet is between 2,000 to 3,000 feet per minute (varies depending on the aircraft load and weather conditions)
# - Descent Rate: Normal descent rates are around 1,500 to 2,000 feet per minute, can be faster if needed for e.g. CDA (Continuous Descent Approaches)
# 
# 2. Light Aircraft (e.g. Piper, Cessna)
# - Acceleration/Deceleration: Takeoff speeds are around 100-160 kph (60-100 mph) and can stop within shorter distances often less than 800 feet
# - Climb Rate: Climb rates ranging from 500 to 1,200 feet per minute. High-performance models e.g. Cessna 182 can climb a bit faster
# - Descent Rate: Typically at 500 to 1,000 feet per minute
# 
# 3. Combat Planes
# - Acceleration/Deceleration: e.g F-16 can reach speeds over Mach 2 and rapid deceleration is possible
# - Climb Rate: e.g. F-15 Eagle can climb at over 50,000 feet per minute in a zoom climb
# - Descent Rate: Can descend very quickly, exceeding those of commercial and light aircraft
# 

def check_flight24_in_air(flight_number, api_key):
    url = f"https://api.flightradar24.com/common/v1/flight/list.json?query={flight_number.strip()}&fetchBy=flight&page=1&limit=1&token={api_key}"
    response = requests.get(url)
    flight_data = response.json()
    if flight_data['result']['response']['flight']:
        print(f"Flight {flight_number.strip()} is recognized by Flightradar24 and in the air.")
        return flight_data['result']['response']['flight'][0]['status']['live']
    print(f"Flight {flight_number.strip()} not recognized or not in the air by Flightradar24.")
    return False

def check_flightaware_in_air(flight_number):
    
    url = f"https://www.flightaware.com/live/flight/{flight_number}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    meta_tag = soup.find('meta', attrs={'property': 'og:title'})
    
    if meta_tag and 'Unknown Flight' not in meta_tag['content']:
        print(f"There is a record of flight {flight_number} on flightaware.com")
        return True
    else:
        print("No record of this flight.")
        return False


def alert_me(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subprocess.run(["./alert", message, timestamp], check=True)
    #subprocess.run(["./prowl_alert", message, timestamp], check=True)
    #subprocess.run(["./irc_alert", message, timestamp], check=True)
    print(f"Alert triggered: {message} at {timestamp}")

def calculate_rates(prev_data, current_data):
    time_diff = current_data['seen'] - prev_data['seen']
    if time_diff == 0:
        print("No time difference detected; skipping rate calculations.")
        return 0, 0  # Avoid division by zero
    speed_change = (current_data['gs'] - prev_data['gs']) / time_diff
    altitude_change = (current_data['alt_baro'] - prev_data['alt_baro']) / time_diff
    print(f"Calculated speed change: {speed_change} knots/s, altitude change: {altitude_change} ft/s for aircraft.")
    return speed_change, altitude_change


aircraft_history = {}
print()
print("      \    /     ");
print("  _____-/\-_____     ");
print("      \_\/_/     ");
print()
print("Waiting for juicy flights...")
print()

while True:
    try:
        with open('/run/dump1090-fa/aircraft.json', 'r') as file:
            data = json.load(file)
            for aircraft in data['aircraft']:
                if 'flight' in aircraft and aircraft['flight'].strip():
                    flight_number = aircraft['flight']

                    # Comment out the following 4 lines if you don't want FlightRadar24 checks
                    print(f"Checking flight status for {flight_number.strip()} with Flightradar24.")
                    if not check_flight24_in_air(flight_number, api_key):
                        alert_me("Hidden flight detected: " + flight_number.strip())
                        print("Hidden flight detected: " + flight_number.strip())

                    # Comment out the following 4 lines if you don't want FlightAware checks
                    print(f"Checking flight status for {flight_number.strip()} with FlightAware.")
                    if not check_flightaware_in_air(flight_number):
                        alert_me("Hidden flight detected: " + flight_number.strip())
                        print("Hidden flight detected: " + flight_number.strip())

                    hex_code = aircraft['hex']
                    current_data = {
                        'seen': aircraft['seen'],
                        'gs': aircraft.get('gs', 0),
                        'alt_baro': aircraft.get('alt_baro', 0)
                    }
                    if hex_code in aircraft_history:
                        speed_change, altitude_change = calculate_rates(aircraft_history[hex_code], current_data)
                        # Define thresholds for combat aircraft-like behavior, if we get a change of 50 knots or 1000 feet difference within 30 seconds we alert
                        if abs(speed_change) > 50 or abs(altitude_change) > 1000: 
                            alert_me("Possible anomaly detected: " + flight_number.strip())
                            print("Possible anomaly detected: " + flight_number.strip())
                    else:
                        print(f"New aircraft tracked: {hex_code}. Initializing data.")
                    aircraft_history[hex_code] = current_data
    except Exception as e:
        print(f"Error occurred: {e}")
    
    print(f"Going to sleep for 15 seconds...")
    time.sleep(15)
