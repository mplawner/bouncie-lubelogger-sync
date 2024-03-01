import requests
from datetime import datetime
import pytz
import csv
import argparse
import configparser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import os
import logging

# Set up argument parsing
parser = argparse.ArgumentParser(description='Run the Bouncie Odometer Logger script.')
parser.add_argument('--config', type=str, default='./config.ini', help='Path to the configuration file. Defaults to ./config.ini')
args = parser.parse_args()

# Load the configuration file
config = configparser.ConfigParser()
config.read(args.config)  # Use the path provided via the command line

# Start Logging
logging.basicConfig(filename=config['Logging']['log_file'],
                    level=config['Logging']['log_level'].upper(),
                    format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("Application started")

# Read the Bouncie API credentials
CLIENT_ID = config['BouncieAPI']['client_id']
CLIENT_SECRET = config['BouncieAPI']['client_secret']
REDIRECT_URI = config['BouncieAPI']['redirect_uri']
AUTH_URL = config['BouncieAPI']['auth_url']
BOUNCIE_API_ENDPOINT = config['BouncieAPI']['endpoint_url']
TOKEN_URL = config['BouncieAPI']['token_url']
AUTH_FILE = config['BouncieAPI']['auth_file']

# Read the LocationIQ API credentials
LOCATIONIQ_API_ENDPOINT = config['LocationIQ']['endpoint_url']
LOCATIONIQ_API_KEY = config['LocationIQ']['api_key'] 

# Read the local server address
SERVER_ADDRESS = (config['Server']['host'], int(config['Server']['port']))

# LubeLogger API
LUBELOGGER_SERVER_ADDRESS = f"http://{config['LubeLoggerAPI']['host']}:{int(config['LubeLoggerAPI']['port'])}"

TARGET_DIR = config['Application']['target_dir']
TIMEZONE = config['Application']['timezone']

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

        if 'code' in query_components:
            self.server.auth_code = query_components['code'][0]
            self.wfile.write(b"Authentication successful. You can close this window.")
        else:
            self.wfile.write(b"Failed to authenticate.")

def get_auth_code():
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': 'basic'  # Update the scope as per Bouncie's documentation
    }
    auth_url = f"{AUTH_URL}?{requests.compat.urlencode(params)}"
    print("Please navigate to the following URL to authorize:")
    print(auth_url)

    # Start the HTTP server to listen for the redirect
    httpd = HTTPServer(SERVER_ADDRESS, RequestHandler)
    print(f"Server started at {SERVER_ADDRESS}. Waiting for authorization...")
    httpd.handle_request()  # Handles a single request then returns

    auth_code = getattr(httpd, 'auth_code', None)
    if auth_code:
        with open(AUTH_FILE, 'w') as file:
            file.write(auth_code)
    return auth_code

def get_tokens(auth_code):
    headers = {'Content-Type': 'application/json'}
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': auth_code,
        'redirect_uri': REDIRECT_URI
    }

    response = requests.post(TOKEN_URL, headers=headers, json=data)
    if response.status_code == 200:
        tokens = response.json()
        return tokens
    else:
        logging.error(f"Failed to exchange authorization code for tokens: {response.status_code}")
        return None

def fetch_vehicles(access_token):
    vehicles_endpoint = f"{BOUNCIE_API_ENDPOINT}/vehicles"
    headers = {'Authorization': f'{access_token}'}
    response = requests.get(vehicles_endpoint, headers=headers)
    if response.status_code == 200:
        return response.json() 
    else:
        logging.error(f"Failed to fetch vehicles: {response.status_code}")
        logging.error(f"Endpoint URL: {vehicles_endpoint}")
        logging.error(f"Response headers: {response.headers}")
        logging.error(f"Response body: {response.text}")
        return []

def fetch_lubelogger_vehicles():
    vehicles_endpoint = f"{LUBELOGGER_SERVER_ADDRESS}/api/vehicles"
    # headers = {'Authorization': f'{access_token}'}
    #response = requests.get(vehicles_endpoint, headers=headers)
    response = requests.get(vehicles_endpoint)
    if response.status_code == 200:
        return response.json() 
    else:
        logging.error(f"Failed to fetch vehicles: {response.status_code}")
        logging.error(f"Endpoint URL: {vehicles_endpoint}")
        logging.error(f"Response headers: {response.headers}")
        logging.error(f"Response body: {response.text}")
        return []

def match_vehicle(vin, lube_logger_vehicles):
    for vehicle in lube_logger_vehicles:
        if vin in vehicle['tags']:
            return vehicle['id']
    return None

def lubelogger_max_odo_reading(vehicle_id):
    endpoint = f"{LUBELOGGER_SERVER_ADDRESS}/api/vehicle/odometerrecords"
    #headers = {'Authorization': f'Bearer {lube_logger_auth}'}
    params = {'vehicleId': vehicle_id}
    #response = requests.get(endpoint, headers=headers, params=params)
    logging.info(f"Fetching odometer records for vehicle ID {vehicle_id} from {endpoint}")

    response = requests.get(endpoint, params=params)

    if response.status_code == 200:
        logging.info(f"Successfully fetched data for vehicle ID {vehicle_id}")
        try:
            odometer_records = response.json()
            if odometer_records and all('odometer' in record for record in odometer_records):
                # Convert odometer reading to float if necessary
                for record in odometer_records:
                    record['odometer'] = float(record['odometer'])
                highest_record = max(odometer_records, key=lambda x: x['odometer'])
                logging.info(f"Highest odometer reading for vehicle ID {vehicle_id}: {highest_record['odometer']}")
                return highest_record['odometer']
            else:
                logging.warning("No valid odometer records found or missing 'odometer' key.")
                return 0.0
        except ValueError as e:
            logging.error(f"Error processing odometer records: {e}")
            return 0.0
    else:
        logging.error(f"Failed to fetch odometer records: {response.status_code}")
        return 0.0

def fetch_trips_and_generate_csvs(access_token, vehicles, lubelogger_vehicles):
    for vehicle in vehicles:
        imei = vehicle['imei'] 
        vin = vehicle['vin']  

        # Get the max recorded odometer reading for this car from lubelogger
        lubelogger_max_odo = 0
        lubelogger_vehicle_id = match_vehicle(vin, lubelogger_vehicles)
        if lubelogger_vehicle_id:
            lubelogger_max_odo = lubelogger_max_odo_reading(lubelogger_vehicle_id)
            logging.info(f"Max odometer reading recorded for {vin} in LubeLogger is {lubelogger_max_odo}")
        else:
            logging.info(f"No vehicle found in Lubelogger for vin {vin}")
        
        trips_endpoint = f"{BOUNCIE_API_ENDPOINT}/trips"
        params = {
            'imei': imei,
            'gps-format': 'geojson'  # Either polyline or geojson,  depending on your requirement
        }
        headers = {'Authorization': f'{access_token}'}
        response = requests.get(trips_endpoint, headers=headers, params=params)
        logging.debug(f"Headers: {headers}")
        logging.debug(f"Parameters: {params}")
        logging.debug(f"Response: {response}")
        if response.status_code == 200:
            trips = response.json() 
            with open(f'{TARGET_DIR}/{vin}_trips.csv', mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['Date', 'Odometer', 'Notes'])
                for trip in trips:
                    date = trip['endTime']
                    target_timezone = pytz.timezone(TIMEZONE)
                    date_with_timezone = datetime.strptime(date, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=pytz.utc).astimezone(target_timezone)
                    odometer = trip['endOdometer']
                    notes = f"Distance: {trip['distance']} miles"
                    gps = trip['gps']
                    if int(odometer) > int(lubelogger_max_odo):
                        trip_notes = trip_description(gps)
                        notes = f"{trip_notes}\n{notes}"
                        update_lube_logger_odometer(lubelogger_vehicle_id, date_with_timezone, odometer, notes)
                        notes = notes.replace("\n", "\\n")
                        writer.writerow([date_with_timezone, odometer, notes])
            logging.info(f"Trips for vehicle {vin} saved successfully.")
        else:
            logging.error(f"Failed to fetch trips for vehicle {vin}: {response.status_code}")

def update_lube_logger_odometer(vehicle_id, date, odometer, notes):
    endpoint = f"{LUBELOGGER_SERVER_ADDRESS}/api/vehicle/odometerrecords/add?vehicleId={vehicle_id}"
    print (date)
    #date_obj = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
    date_obj = datetime.strptime(str(date), "%Y-%m-%d %H:%M:%S%z")

    date_formatted = date_obj.strftime("%m/%d/%Y")

    odometer = int(odometer)

    print(f"VehicleID: {vehicle_id} Date: {date_formatted} Odo: {odometer} Notes: {notes}")
    data = {
        'date': date_formatted,  
        'odometer': odometer, 
        'notes': notes 
    }

    response = requests.post(endpoint, data=data)
    if response.status_code == 200:
        logging.info(f"Successfully updated odometer for vehicle ID {vehicle_id}")
    else:
        logging.error(f"Failed to update odometer for vehicle ID {vehicle_id}: {response.status_code}")

def get_address(lat, lon):
    params = {
        "key": LOCATIONIQ_API_KEY,
        "lat": lat,
        "lon": lon,
        "format": "json"
    }
    response = requests.get(LOCATIONIQ_API_ENDPOINT, params=params)
    # if response.status_code == 200:
    #     data = response.json()
    #     address = data.get("display_name", "Unknown location")
    #     logging.debug(f"Got Address {address}")
    #     return address
    if response.status_code == 200:
        data = response.json()
        address_components = data.get("address", {})
        # Extracting specific components for formatting
        house_number = address_components.get("house_number", "")
        road = address_components.get("road", "")
        city = address_components.get("city", "")
        state = address_components.get("state", "")
        formatted_address = f"{house_number} {road}, {city}, {state}".strip(", ")
        logging.debug(f"Got Address {formatted_address}")
        return formatted_address
    else:
        logging.error(f"Error retrieving address for lat {lat} and lon {lon}")
        return "Unknown location"

def trip_description(geojson_line_string):
    coordinates = geojson_line_string.get('coordinates', [])
    if len(coordinates) >= 2:
        start_coord = coordinates[0]
        end_coord = coordinates[-1]

        start_address = get_address(start_coord[1], start_coord[0])
        end_address = get_address(end_coord[1], end_coord[0])

        return f"Start: {start_address}\nEnd: {end_address}"
    else:
        # Handle the case where there are not enough coordinates for a trip
        return "Insufficient data for trip description."

def main():
    # Authenticate
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r') as file:
            auth_code = file.read().strip()
            tokens = get_tokens(auth_code)
            if tokens:  
                access_token = tokens.get('access_token')
                logging.info("Found authentication file, generated new token")
            else:
                logging.error("Failed to exchange authorization code for tokens.")
                return
    else:
        auth_code = get_auth_code()
        if auth_code:
            tokens = get_tokens(auth_code)
            if tokens:  
                access_token = tokens.get('access_token')
                logging.info("New authentication file created, and token generated")
            else:
                logging.error("Failed to exchange authorization code for tokens.")
                return
        else:
            logging.error("Failed to obtain authorization code.")
            return

    vehicles = fetch_vehicles(access_token)
    lubelogger_vehicles = fetch_lubelogger_vehicles()

    if vehicles and lubelogger_vehicles:
        fetch_trips_and_generate_csvs(access_token, vehicles, lubelogger_vehicles)
    else:
        logging.error("No vehicles found or failed to fetch vehicles.")

    logging.info("Application completed")

if __name__ == "__main__":
    main()
