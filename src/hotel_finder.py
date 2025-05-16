# src/hotel_finder.py
import time

# Placeholder for actual hotel searching logic

def find_hotels(trip_period, search_locations, preferred_brands, fallback_options):
    """Placeholder function to find hotels.

    Args:
        trip_period (dict): Contains start_date_str, end_date_str.
        search_locations (list): List of dicts, each with 'type' ('airport' or 'park_area') 
                                 and 'location_name' (airport code or area like 'Tusayan, AZ').
        preferred_brands (list): List of preferred hotel brands (e.g., ['Hyatt']).
        fallback_options (str): Fallback search if preferred not found (e.g., "Any").

    Returns:
        list: A list of dummy hotel option dictionaries.
    """
    print(f"  [HotelFinder] Searching hotels for dates: {trip_period['start_date_str']} to {trip_period['end_date_str']}")
    print(f"                Preferred brands: {preferred_brands}, Fallback: {fallback_options}")
    print(f"                Search locations: {search_locations}")

    # Simulate API call or scraping delay
    # time.sleep(0.1)

    hotels_found = []
    # Simulate finding one Hyatt for the first search location
    if search_locations and preferred_brands:
        hotels_found.append({
            "search_location_type": search_locations[0]['type'],
            "searched_at": search_locations[0]['location_name'],
            "hotel_name": f"Dummy {preferred_brands[0]} {search_locations[0]['location_name']}",
            "brand": preferred_brands[0],
            "check_in_date": trip_period['start_date_str'],
            "check_out_date": trip_period['end_date_str'],
            "price_total": "$400 - $700",
            "price_per_night": "$200 - $350",
            "booking_link": "https://hotels.example.com/dummy_link"
        })
        print(f"    -> Found dummy {preferred_brands[0]} hotel at {search_locations[0]['location_name']}")
    else:
        print("    -> Not enough info to search for dummy hotels (need location and brand).")
        
    return hotels_found

if __name__ == '__main__':
    print("Testing hotel_finder.py...")
    sample_trip_period = {
        'start_date_str': '2025-07-04',
        'end_date_str': '2025-07-06'
    }
    sample_locations = [
        {'type': 'airport', 'location_name': 'LAS'},
        {'type': 'park_area', 'location_name': 'Springdale, UT'}
    ]
    pref_brands = ['Hyatt']
    fallback = "Any"

    hotels = find_hotels(sample_trip_period, sample_locations, pref_brands, fallback)
    if hotels:
        print(f"Dummy hotel options: {hotels}") 