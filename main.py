import yaml # For loading YAML configuration
from datetime import datetime, timedelta # For date calculations
from src.sheets_manager import get_authenticated_service, create_spreadsheet
from src.flight_finder import find_flights
from src.car_rental_finder import find_car_rentals
from src.hotel_finder import find_hotels

CONFIG_FILE = "trip_config.yaml"
# FOLDER_ID for Google Drive can remain a constant here, or be moved to config if preferred
FOLDER_ID = "1hDvTg-y2Nl3DPNvFaPzfdhVhxeSaoga6"

def load_config():
    """Loads trip configuration from the YAML file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
            print(f"Successfully loaded configuration from {CONFIG_FILE}")
            return config
    except FileNotFoundError:
        print(f"Error: Configuration file '{CONFIG_FILE}' not found. Please create it from the example.")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration file '{CONFIG_FILE}': {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading config: {e}")
        return None

def main():
    print("Starting Trip Planner...")

    config = load_config()
    if not config:
        print("Exiting due to configuration loading error.")
        return

    # For now, print the loaded config to verify
    # print("\nLoaded Configuration:")
    # import json
    # print(json.dumps(config, indent=2))
    # print("\n")

    spreadsheet_title = config.get('output_sheet_name', "Default Trip Planning Sheet")
    
    # Authenticate and get Google Sheets service client
    gs_client = get_authenticated_service()
    
    if not gs_client:
        print("Exiting: Could not authenticate with Google Sheets.")
        return

    print("Successfully authenticated with Google Sheets.")

    # Create or open the spreadsheet in the specified folder
    spreadsheet = create_spreadsheet(gs_client, spreadsheet_title, folder_id=FOLDER_ID)

    if not spreadsheet:
        print(f"Exiting: Could not create or open spreadsheet: {spreadsheet_title}")
        return

    print(f"Successfully accessed spreadsheet: {spreadsheet.title} ({spreadsheet.url})")
    print("\n--- Starting Trip Option Calculations ---")

    # Process trip dates
    parsed_weekend_dates = []
    for date_str in config.get('weekend_dates', []):
        try:
            # Assuming date_str is YYYY-MM-DD and represents a Saturday
            parsed_weekend_dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
        except ValueError:
            print(f"Warning: Invalid date format '{date_str}' in config. Skipping.")
            continue

    trip_length_options = config.get('trip_length_options', [])
    all_trip_periods = []

    for sat_date in parsed_weekend_dates:
        for length_option in trip_length_options:
            start_date = None
            end_date = None
            description = ""

            if length_option == "none": # Fri-Sun
                start_date = sat_date - timedelta(days=1)
                end_date = sat_date + timedelta(days=1)
                description = f"Weekend (Fri-Sun): {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            elif length_option == "friday_off": # Thu-Sun
                start_date = sat_date - timedelta(days=2)
                end_date = sat_date + timedelta(days=1)
                description = f"Friday Off (Thu-Sun): {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            elif length_option == "monday_off": # Fri-Mon
                start_date = sat_date - timedelta(days=1)
                end_date = sat_date + timedelta(days=2)
                description = f"Monday Off (Fri-Mon): {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            else:
                print(f"Warning: Unknown trip length option '{length_option}'. Skipping.")
                continue
            
            if start_date and end_date:
                trip_info = {
                    "description": description,
                    "start_date_str": start_date.strftime("%Y-%m-%d"),
                    "end_date_str": end_date.strftime("%Y-%m-%d"),
                    "start_date_obj": start_date,
                    "end_date_obj": end_date,
                    "original_saturday": sat_date.strftime("%Y-%m-%d")
                }
                all_trip_periods.append(trip_info)
                print(f"Generated trip option: {description}")

    if not all_trip_periods:
        print("No valid trip periods generated. Check config for weekend_dates and trip_length_options.")
        return

    print(f"\nTotal trip options generated: {len(all_trip_periods)}")
    print("--- Starting to fetch details for each trip option ---")

    all_trip_data_for_sheet = [] # Will hold data for all options

    for i, trip_period in enumerate(all_trip_periods):
        print(f"\nProcessing Trip Option {i+1}/{len(all_trip_periods)}: {trip_period['description']}")

        current_option_flights = []
        for traveler in config.get('travelers', []):
            flights = find_flights(trip_period, traveler, config.get('destination_airport_options', []))
            if flights:
                current_option_flights.extend(flights)
            # else: # Handle no flights found for a traveler if needed
            #     print(f"    No flights found for {traveler['name']}")
        
        # For car rentals, we'd typically search at each potential destination airport
        # and then the user would choose one that aligns with their chosen flights.
        # For now, let's assume we search at all destination_airport_options.
        car_rentals = find_car_rentals(trip_period, config.get('destination_airport_options', []))

        # Prepare hotel search locations
        hotel_search_locations = []
        # 1. Add destination airports
        for airport_code in config.get('destination_airport_options', []):
            hotel_search_locations.append({'type': 'airport', 'location_name': airport_code})
        
        # 2. Add park-specific search areas if defined in config
        for park_info in config.get('destination_parks', []):
            search_area = park_info.get('hotel_search_area')
            if search_area: # Only add if hotel_search_area is provided and not empty
                hotel_search_locations.append({'type': 'park_area', 'location_name': search_area, 'park_name': park_info.get('name')})

        hotels = find_hotels(
            trip_period,
            hotel_search_locations,
            config.get('preferred_hotel_brands', []),
            config.get('fallback_hotel_options', "Any")
        )

        # For now, just print the collected dummy data for this trip option
        print(f"  Collected for {trip_period['description']}:")
        if current_option_flights:
            print(f"    Flights: {current_option_flights}")
        if car_rentals:
            print(f"    Car Rentals: {car_rentals}")
        if hotels:
            print(f"    Hotels: {hotels}")
        
        # We would store this collected data for later writing to the sheet
        trip_data_summary = {
            "trip_description": trip_period['description'],
            "start_date": trip_period['start_date_str'],
            "end_date": trip_period['end_date_str'],
            "flights_info": current_option_flights,
            "car_rentals_info": car_rentals,
            "hotels_info": hotels
        }
        all_trip_data_for_sheet.append(trip_data_summary)

    print("\n--- All trip options processed (with dummy data) ---")
    # print(f"Total data collected for sheet: {json.dumps(all_trip_data_for_sheet, indent=2)}") 
    print("Next step: Implement actual data fetching in finder modules and write to Google Sheet.")

if __name__ == "__main__":
    main() 