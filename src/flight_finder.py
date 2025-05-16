# src/flight_finder.py
import time
import json
import math # Added for rounding
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

# --- Constants ---
GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights"

# --- Selenium WebDriver Setup ---
def get_webdriver(headless=True):
    """Initializes and returns a Selenium Chrome WebDriver.

    Args:
        headless (bool): If True, runs Chrome in headless mode. 
                         Set to False for debugging to see browser actions.

    Returns:
        selenium.webdriver.chrome.webdriver.WebDriver or None: 
            The initialized WebDriver instance, or None if initialization fails.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox") # Important for running in some environments
    options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
    options.add_experimental_option('excludeSwitches', ['enable-logging']) # Suppress DevTools logging
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        print(f"Error initializing WebDriver: {e}")
        print("Please ensure Google Chrome is installed.")
        print("If issues persist, you might need to check ChromeDriver compatibility or network access for webdriver-manager.")
        return None

# --- Helper function to set a slider thumb ---
def _set_slider_thumb_value(driver, wait, thumb_xpath, input_xpath, slider_track_xpath, target_value, slider_label):
    """Helper function to set a single slider thumb to a target value."""
    print(f"      Attempting to set {slider_label} to {target_value}...")
    try:
        # Locate the hidden input to get its properties
        slider_input_element = wait.until(EC.presence_of_element_located((By.XPATH, input_xpath)))
        min_val = int(slider_input_element.get_attribute('min'))
        max_val = int(slider_input_element.get_attribute('max'))
        step_size = int(slider_input_element.get_attribute('step'))
        current_value = int(slider_input_element.get_attribute('value'))

        # Locate the visible slider track
        slider_track = driver.find_element(By.XPATH, slider_track_xpath)
        slider_track_width = slider_track.size['width']
        
        # Locate the draggable thumb element
        thumb_element = driver.find_element(By.XPATH, thumb_xpath)
        
        print(f"        {slider_label} Slider: min={min_val}, max={max_val}, step={step_size}, current_value={current_value}, target_value={target_value}")
        print(f"        {slider_label} Slider track width: {slider_track_width}px")

        # Clamp target_value to min/max of the specific thumb
        clamped_target_value = max(min_val, min(max_val, target_value))
        if clamped_target_value != target_value:
            target_value = clamped_target_value
        
        if target_value == current_value:
            return True

        if step_size <= 0: step_size = 1 # Avoid division by zero or non-positive step
        
        # Ensure total_steps_in_slider is not zero before division
        if max_val == min_val: # slider has no range
             total_steps_in_slider = 0
        else:
            total_steps_in_slider = (max_val - min_val) / step_size
        
        pixels_per_step = 0
        if total_steps_in_slider != 0 and slider_track_width > 0 :
            pixels_per_step = slider_track_width / total_steps_in_slider
        else:
            print(f"        WARNING: Cannot accurately calculate pixels_per_step for {slider_label} (total_steps: {total_steps_in_slider}, track_width: {slider_track_width}). Drag might be inaccurate.")

        steps_to_move = (target_value - current_value) / step_size
        x_drag_offset = int(math.ceil(steps_to_move * pixels_per_step)) # Use math.ceil to ensure movement if pixels_per_step is small

        if x_drag_offset != 0:
            actions = ActionChains(driver)
            actions.drag_and_drop_by_offset(thumb_element, x_drag_offset, 0).perform()
            time.sleep(2.0) # Pause for UI to update after drag
        else:
            pass # No action needed if offset is 0

        # Verify the value after trying to set by drag
        try:
            # Re-fetch input element to get updated value
            slider_input_element_after_drag = driver.find_element(By.XPATH, input_xpath) 
            updated_value_attr = slider_input_element_after_drag.get_attribute('value')
            # Check if the new value is close to the target (within one step, due to rounding/pixel precision)
            if abs(int(updated_value_attr) - target_value) >= step_size and step_size > 0 : # Check if off by at least one full step
                print(f"        WARNING: {slider_label} value {updated_value_attr} is not close to target {target_value} after drag.")
        except Exception as e_val_check:
            print(f"        Could not check {slider_label} value after drag: {e_val_check}")

        return True

    except TimeoutException as e_timeout:
        print(f"      Timeout while trying to set {slider_label}: {e_timeout}")
        return False
    except Exception as e_general:
        print(f"      Error setting {slider_label}: {e_general}")
        return False

# --- Main flight finding function using Selenium ---
def find_flights_selenium(trip_period, traveler_info, destination_airports, run_headless=True):
    """Finds flights using Selenium to automate Google Flights.
    Initial version focuses on performing the search and reaching results page.
    """
    print(f"  [FlightFinder Selenium] Starting search for {traveler_info['name']}")
    print(f"                 Dates: {trip_period['start_date_str']} to {trip_period['end_date_str']}")
    traveler_budget = traveler_info.get('budget') # Get budget, default to None if not present
    if traveler_budget:
        print(f"                 Budget: ${traveler_budget}")
    
    origin_ap = traveler_info['origin_airport_options'][0] if traveler_info['origin_airport_options'] else None
    dest_ap = destination_airports[0] if destination_airports else None

    if not origin_ap or not dest_ap:
        print("    -> Missing origin or destination airport for search.")
        return [{ "status": "ERROR_MISSING_INPUTS", "message": "Origin or destination airport missing."}]

    print(f"                 From {origin_ap} to {dest_ap}")

    driver = get_webdriver(headless=run_headless)
    if not driver:
        return [{ "status": "ERROR_WEBDRIVER_INIT", "message": "Failed to initialize WebDriver."}]

    search_success_status = "ERROR_UNKNOWN_SELENIUM_ISSUE"
    search_message = "An unknown error occurred during Selenium automation."
    flight_results_summary = []

    try:
        driver.get(GOOGLE_FLIGHTS_URL)
        print(f"    Navigated to {GOOGLE_FLIGHTS_URL}")
        wait = WebDriverWait(driver, 20) # Increased wait time

        # --- Consent form / "Before you continue" dialog (if it appears) ---
        try:
            # Google sometimes shows a consent form. Common button text is "Accept all" or "Reject all"
            # Using a more general XPath that looks for buttons with specific text patterns.
            consent_button_xpath = "//button[.//span[contains(text(),'Accept all') or contains(text(),'Reject all') or contains(text(),'I agree')]]"
            consent_button = wait.until(EC.element_to_be_clickable((By.XPATH, consent_button_xpath)))
            print("    Consent form detected. Clicking a consent button (e.g., 'Reject all' or 'Accept all')...")
            # To be less intrusive / faster, often "Reject all" is preferred if available and functional.
            # Prioritize "Reject all" then "Accept all"
            try:
                reject_all_button_xpath = "//button[.//span[contains(text(),'Reject all')]]"
                reject_button = driver.find_element(By.XPATH, reject_all_button_xpath)
                reject_button.click()
                print("    Clicked 'Reject all'.")
            except NoSuchElementException:
                print("    'Reject all' not found, trying 'Accept all' or similar.")
                consent_button.click() # Fallback to the first found button
                print("    Clicked a consent button.")
            print("    Consent form handled.")
            time.sleep(2) # Wait for dialog to disappear
        except TimeoutException:
            print("    No consent form detected or already handled.")
        except Exception as e_consent:
            print(f"    Error handling consent form: {e_consent}")

        # --- Locate and fill origin --- 
        print("    Locating origin input...")
        origin_input_xpath = "//input[@aria-label='Where from?']"
        origin_input_field = wait.until(EC.presence_of_element_located((By.XPATH, origin_input_xpath)))
        
        # Click to ensure it's focused, then clear and send keys
        # Some inputs on Google Flights are divs that swap to inputs, direct interaction is key
        origin_input_field.click() 
        time.sleep(0.3) # Brief pause for any JS focusing or swapping
        origin_input_field.send_keys(Keys.CONTROL + "a" + Keys.DELETE) # Clear field
        time.sleep(0.2)
        origin_input_field.send_keys(origin_ap)
        print(f"    Typed origin: {origin_ap}")
        time.sleep(0.5) # Adjust this timing if needed for suggestions to populate
        
        # Updated suggestion selection logic
        # Wait for the listbox itself to appear first
        listbox_xpath = "//ul[@role='listbox']"
        wait.until(EC.presence_of_element_located((By.XPATH, listbox_xpath)))
        print("    Suggestion listbox appeared.")
        
        # Now find the specific suggestion. This XPath tries to find an item that contains the airport code 
        # and is often followed by the city or airport name. Adjust if necessary.
        # It looks for a list item that has a div containing a span with the airport code.
        # Or a div directly containing the airport code and the word airport in its text or a child span.
        specific_suggestion_xpath = f"//li[@role='option' and @data-code='{origin_ap}' and @data-type='1']"
        # Fallback if the above is too complex or specific (e.g., if 'airport' text isn't always present):
        # specific_suggestion_xpath = f"//ul[@role='listbox']/li[@role='option'][.//div[contains(., '{origin_ap}')]][1]"
        print(f"    Trying to click suggestion with XPath: {specific_suggestion_xpath}")
        suggestion_to_click = wait.until(EC.element_to_be_clickable((By.XPATH, specific_suggestion_xpath)))
        suggestion_to_click.click()
        print(f"    Clicked origin suggestion for {origin_ap}")
        time.sleep(0.5) # Short pause for origin dropdown/UI to settle

        # --- Locate and fill destination ---
        print("    Locating destination input ('Where to? ')...")
        # Target the input field that seems to be reactivated for destination input.
        # Using the aria-label with a trailing space as observed in user-provided HTML.
        dest_input_xpath = "//input[@aria-label='Where to? ']" 
        dest_input_field = wait.until(EC.element_to_be_clickable((By.XPATH, dest_input_xpath)))
        
        # dest_input_field.click() # Removed click as field might be autofocused
        time.sleep(0.5) # Increased pause to allow autofocus to settle before sending keys
        dest_input_field.send_keys(Keys.CONTROL + "a" + Keys.DELETE)
        time.sleep(0.2)
        dest_input_field.send_keys(dest_ap)
        print(f"    Typed destination: {dest_ap}")
        time.sleep(0.5) # Adjust this timing if needed for suggestions to populate
        
        # Reuse suggestion logic for destination
        # Wait for the listbox itself to appear first (it might be the same listbox as origin or a new one)
        listbox_xpath = "//ul[@role='listbox']" # Assuming same listbox XPath, adjust if different for dest
        wait.until(EC.presence_of_element_located((By.XPATH, listbox_xpath)))
        print("    Destination suggestion listbox appeared.")
        
        specific_suggestion_xpath_dest = f"//li[@role='option' and @data-code='{dest_ap}']" # Simplified XPath, relying on data-code
        print(f"    Trying to click destination suggestion with XPath: {specific_suggestion_xpath_dest}")
        suggestion_to_click_dest = wait.until(EC.element_to_be_clickable((By.XPATH, specific_suggestion_xpath_dest)))
        suggestion_to_click_dest.click()
        print(f"    Clicked destination suggestion for {dest_ap}")

        # --- Enter Dates (This is often the trickiest part) ---
        print("    Locating date inputs...")
        try:
            departure_date_xpath = "//input[@aria-label='Departure' and @placeholder='Departure']"
            departure_date_field = wait.until(EC.element_to_be_clickable((By.XPATH, departure_date_xpath)))
            print(f"    Found departure date field. Clicking and sending keys: {trip_period['start_date_str']}")
            departure_date_field.click()
            time.sleep(0.3) # Brief pause for calendar to open or field to be fully active
            departure_date_field.send_keys(Keys.CONTROL + "a" + Keys.DELETE) # Clear field first
            time.sleep(0.2)
            departure_date_field.send_keys(trip_period['start_date_str'])
            time.sleep(0.3) # Pause after sending keys
            print("    Sent departure date. Attempting to close calendar with ENTER key.")
            departure_date_field.send_keys(Keys.ENTER)
            time.sleep(0.5) # Wait for calendar to close

            return_date_xpath = "//input[@aria-label='Return' and @placeholder='Return']"
            return_date_field = wait.until(EC.presence_of_element_located((By.XPATH, return_date_xpath))) # Wait for presence, not clickability initially
            print(f"    Found return date field. Sending keys: {trip_period['end_date_str']}")
            # return_date_field.click() # Removed click, assuming field is auto-focused or ready
            time.sleep(0.3) # Brief pause before sending keys
            return_date_field.send_keys(Keys.CONTROL + "a" + Keys.DELETE) # Clear field
            time.sleep(0.2)
            return_date_field.send_keys(trip_period['end_date_str'])
            time.sleep(0.3)
            print("    Sent return date. Attempting to close calendar with ENTER key.")
            return_date_field.send_keys(Keys.ENTER) # Also try to close calendar for return date
            time.sleep(0.5) # Wait for calendar to close

            # Click "Done" button for dates
            done_button_xpath = "//button[@aria-label='Done. ']"
            print("    Attempting to click 'Done' button for dates...")
            date_done_button = wait.until(EC.element_to_be_clickable((By.XPATH, done_button_xpath)))
            date_done_button.click()
            print("    Clicked 'Done' for dates.")

            # print("DEBUG: Pausing for 60s AFTER date 'Done' button. Check if results load or what search button to click.") # Remove this pause
            # time.sleep(60)

        except TimeoutException as e_date:
            print(f"    Timeout while trying to input dates or click Done: {e_date}")
            print("    Could not find or interact with date fields or Done button as expected.")
        except Exception as e_date_general:
            print(f"    An error occurred during date input: {e_date_general}")

        # --- Click Search/Done button --- # Re-enabling with specific XPath
        print("    Looking for final 'Search' button (for flight listings)...")
        try:
            search_button_xpath = "//button[@aria-label='Search' and @jsname='vLv7Lb']" # Specific XPath for the correct Search button
            search_button = wait.until(EC.element_to_be_clickable((By.XPATH, search_button_xpath)))
            search_button.click()
            print("    Clicked main 'Search' button.")

            # print("DEBUG: Pausing for 60s AFTER main 'Search' button click. Inspect results page for indicator XPath.") # Removing debug pause
            # time.sleep(60) # PAUSE FOR DEBUGGING RESULTS PAGE INDICATOR

        except TimeoutException:
            print("    Could not find or click the specific 'Search' button for flight listings.")
            # If this fails, it's a critical error for this flow.
            raise # Re-raise the exception to stop the script if search button isn't found/clicked

        # --- Wait for results to load (very basic check for now) --- # Re-enabling
        print("    Waiting for flight results to appear (indicative check)...")
        results_indicator_xpath = "//div[@class='JMc5Xc']" # Updated XPath to look for a flight item
        wait.until(EC.presence_of_element_located((By.XPATH, results_indicator_xpath)))
        print("    Flight results page seems to have loaded (found a flight item).")
        
        # --- VALIDATION STEP 1: After initial search, before filters ---
        if not run_headless:
            print("    [VALIDATION 1] Initial search results loaded. Pausing for 30s to verify (before filters)...")
            time.sleep(30)
        
        # --- Apply Filters: Stops ---
        print("    Attempting to apply 'Stops: Nonstop' filter...")
        try:
            # Using a more robust XPath that checks for child span text and aria-label prefix
            stops_filter_button_xpath = "//button[.//span[text()='Stops'] and starts-with(@aria-label, 'Stops')]"
            print(f"      Locating 'Stops' filter button with XPath: {stops_filter_button_xpath}")
            stops_button = wait.until(EC.element_to_be_clickable((By.XPATH, stops_filter_button_xpath)))
            stops_button.click()
            print("      Clicked 'Stops' filter button.")
            time.sleep(1) # Brief pause for the dropdown to open

            # Refined XPath to click the surrounding div of the radio button, which is often the actual clickable element.
            nonstop_option_xpath = "//div[contains(@class, 'VfPpkd-GCYh9b') and .//input[@aria-label='Nonstop only' and @type='radio']]"
            print(f"      Locating 'Nonstop only' option with XPath: {nonstop_option_xpath}")
            nonstop_clickable_element = wait.until(EC.element_to_be_clickable((By.XPATH, nonstop_option_xpath)))
            
            # Check if the radio button within this element is already selected
            # To do this, we find the input element relative to the clickable div
            nonstop_radio_button = nonstop_clickable_element.find_element(By.XPATH, ".//input[@aria-label='Nonstop only']")

            if not nonstop_radio_button.is_selected():
                nonstop_clickable_element.click()
                print("      Selected 'Nonstop only'.")
            else:
                print("      'Nonstop only' was already selected.")
            
            print("      Waiting for Nonstop filter to apply and UI to refresh...")
            time.sleep(3) # Increased pause significantly after selection for UI to potentially reload/settle

            # Attempt to close the Stops filter dialog by sending the ESCAPE key
            print("      Attempting to close 'Stops' dialog by sending ESCAPE key...")
            try:
                # Find the body element to send keys to, or any major stable element
                body_element = driver.find_element(By.XPATH, "//body")
                body_element.send_keys(Keys.ESCAPE)
                print("      Sent ESCAPE key to close 'Stops' dialog.")
            except Exception as e_escape:
                print(f"      Error sending ESCAPE key: {e_escape}")
                # If escape fails, we might be stuck, but will proceed to next pause for now

            print("    Successfully applied 'Stops: Nonstop' filter and closed dialog.")

            # --- Apply Filters: Price ---
            print("    Attempting to open 'Price' filter...")
            try:
                price_filter_button_xpath = "//button[.//span[text()='Price'] and starts-with(@aria-label, 'Price')]"
                print(f"      Locating 'Price' filter button with XPath: {price_filter_button_xpath}")
                price_button = wait.until(EC.element_to_be_clickable((By.XPATH, price_filter_button_xpath)))
                price_button.click()
                print("      Clicked 'Price' filter button.")
                # Status update for the next step/pause
                search_success_status = "INFO_PRICE_FILTER_OPENED_PAUSED_FOR_INPUT_INSPECTION"
                search_message = "Opened Price filter. Paused for Price input elements inspection."
            except TimeoutException as e_filter_price_open:
                print(f"    Timeout while trying to open 'Price' filter: {e_filter_price_open}")
                search_success_status = "ERROR_FILTER_PRICE_OPEN_TIMEOUT"
                search_message = f"Timeout opening 'Price' filter: {e_filter_price_open}"
            except Exception as e_filter_price_open_general:
                print(f"    Error opening 'Price' filter: {e_filter_price_open_general}")
                search_success_status = "ERROR_FILTER_PRICE_OPEN_GENERAL"
                search_message = f"General error opening 'Price' filter: {e_filter_price_open_general}"

            # --- Set Price Value ---
            if traveler_budget is not None:
                print(f"    Attempting to set price filter to max ${traveler_budget} by dragging slider thumb...")
                try:
                    # Locate the hidden input to get its properties (min, max, step, current value)
                    price_input_xpath = "//input[@type='range' and @aria-label='Maximum price']"
                    price_input = wait.until(EC.presence_of_element_located((By.XPATH, price_input_xpath)))
                    min_price = int(price_input.get_attribute('min'))
                    max_price = int(price_input.get_attribute('max'))
                    step_size = int(price_input.get_attribute('step'))
                    current_value = int(price_input.get_attribute('value'))

                    # Locate the visible slider track to get its width for pixel calculations
                    slider_track_xpath = "//div[contains(@class, 'VfPpkd-SxecR') and @jscontroller='tbQzUe' and @jsname='SxecR']"
                    slider_track = driver.find_element(By.XPATH, slider_track_xpath)
                    slider_track_width = slider_track.size['width']

                    # Locate the draggable thumb element
                    thumb_xpath = "//div[@jsname='PFprWc' and .//input[@aria-label='Maximum price']]"
                    thumb_element = driver.find_element(By.XPATH, thumb_xpath)
                    
                    print(f"      Slider details: min=${min_price}, max=${max_price}, step=${step_size}, current_value=${current_value}, target_budget=${traveler_budget}")
                    print(f"      Slider track width: {slider_track_width}px")

                    target_value_for_slider = max(min_price, min(max_price, traveler_budget)) # Clamp budget to min/max

                    if target_value_for_slider == current_value:
                        print(f"      Target price ${target_value_for_slider} is already set. Skipping slider drag.")
                    else:
                        if step_size == 0: step_size = 1 # Avoid division by zero if step is 0 (should not happen for range input)
                        total_steps_in_slider = (max_price - min_price) / step_size
                        if total_steps_in_slider == 0: # Avoid division by zero if min=max
                             pixels_per_step = 0
                        else:
                            pixels_per_step = slider_track_width / total_steps_in_slider
                        
                        steps_to_move = (target_value_for_slider - current_value) / step_size
                        x_drag_offset = int(steps_to_move * pixels_per_step)

                        print(f"      Target value for slider: ${target_value_for_slider}")
                        print(f"      Pixels per step: {pixels_per_step:.2f}, Steps to move: {steps_to_move}, Calculated X drag offset: {x_drag_offset}px")

                        if x_drag_offset != 0:
                            actions = ActionChains(driver)
                            actions.drag_and_drop_by_offset(thumb_element, x_drag_offset, 0).perform()
                            time.sleep(2.0) # Adjusted pause for UI to update after drag
                        else:
                            print("      Calculated drag offset is 0, no drag action performed.")

                    # Verify the aria-valuetext after trying to set by drag
                    try:
                        price_input_after_drag = driver.find_element(By.XPATH, price_input_xpath) # Re-fetch
                        updated_aria_value = price_input_after_drag.get_attribute('aria-valuetext')
                        current_slider_val_attr = price_input_after_drag.get_attribute('value')
                        print(f"      Slider aria-valuetext after drag: {updated_aria_value}, value attribute: {current_slider_val_attr}")
                        # Check if the new value is close to the target (within one step, due to rounding/pixel precision)
                        if abs(int(current_slider_val_attr) - target_value_for_slider) > step_size:
                            print(f"      WARNING: Slider value ${current_slider_val_attr} is not close to target ${target_value_for_slider} after drag.")
                    except Exception as e_aria_check:
                        print(f"      Could not check slider values after drag: {e_aria_check}")

                    # Close Price dialog using ESCAPE key
                    print("      Attempting to close 'Price' dialog by sending ESCAPE key...")
                    body_element = driver.find_element(By.XPATH, "//body")
                    body_element.send_keys(Keys.ESCAPE)
                    print("      Sent ESCAPE key to close 'Price' dialog.")
                    time.sleep(2) # Pause for results to refresh after price change

                    search_success_status = "INFO_PRICE_FILTER_APPLIED_PAUSED_FOR_TIMES_INSPECTION"
                    search_message = f"Applied Price filter (max ${traveler_budget}). Paused for Times filter inspection."
                    print(f"    Successfully applied Price filter (max ${traveler_budget}).")

                except TimeoutException as e_price_set:
                    print(f"    Timeout while trying to set price: {e_price_set}")
                    search_success_status = "ERROR_FILTER_PRICE_SET_TIMEOUT"
                    search_message = f"Timeout setting price filter: {e_price_set}"
                except Exception as e_price_set_general:
                    print(f"    Error setting price filter: {e_price_set_general}")
                    search_success_status = "ERROR_FILTER_PRICE_SET_GENERAL"
                    search_message = f"General error setting price filter: {e_price_set_general}"
            else:
                print("    No budget specified for traveler, skipping Price filter.")
                # Update status if price filter is skipped
                search_success_status = "INFO_PRICE_FILTER_SKIPPED_PAUSED_FOR_TIMES_INSPECTION"
                search_message = "Price filter skipped (no budget). Paused for Times filter inspection."

            # --- Apply Filters: Times (Open Dialog) ---
            print("    Attempting to open 'Times' filter...")
            try:
                times_filter_button_xpath = "//button[.//span[text()='Times'] and starts-with(@aria-label, 'Times')]"
                print(f"      Locating 'Times' filter button with XPath: {times_filter_button_xpath}")
                times_button = wait.until(EC.element_to_be_clickable((By.XPATH, times_filter_button_xpath)))
                times_button.click()
                print("      Clicked 'Times' filter button.")
                search_success_status = "INFO_TIMES_FILTER_OPENED_PAUSED_FOR_INPUT_INSPECTION"
                search_message = "Opened Times filter. Paused for Outbound Times input elements inspection."
            except TimeoutException as e_filter_times_open:
                print(f"    Timeout while trying to open 'Times' filter: {e_filter_times_open}")
                search_success_status = "ERROR_FILTER_TIMES_OPEN_TIMEOUT"
                search_message = f"Timeout opening 'Times' filter: {e_filter_times_open}"
            except Exception as e_filter_times_open_general:
                print(f"    Error opening 'Times' filter: {e_filter_times_open_general}")
                search_success_status = "ERROR_FILTER_TIMES_OPEN_GENERAL"
                search_message = f"General error opening 'Times' filter: {e_filter_times_open_general}"

            # This debug pause is now for inspecting the TIMES filter UI elements (outbound departure/arrival)
            print("DEBUG: Pausing for 120s to inspect OUTBOUND TIMES filter UI elements (after 'Times' filter button click)...")
            # time.sleep(120) # PAUSE FOR INSPECTING TIMES FILTER UI ELEMENTS

            # --- Apply Times Filters (Outbound Departure & Arrival) ---
            print("    Applying 'Times' filter settings...")
            preferred_times = traveler_info.get('preferred_times', {})
            out_dep_earliest = preferred_times.get('outbound_departure_earliest')
            out_dep_latest = preferred_times.get('outbound_departure_latest')
            out_arr_earliest = preferred_times.get('outbound_arrival_earliest')
            out_arr_latest = preferred_times.get('outbound_arrival_latest')

            times_dialog_xpath_base = "//div[@aria-modal='true' and @role='dialog' and .//h2[text()='Times']]"
            
            # Wait for the dialog to be stable.
            # A specific element within the dialog, e.g., the first input for earliest departure.
            try:
                wait.until(EC.presence_of_element_located((By.XPATH, times_dialog_xpath_base + "//input[@aria-label='Earliest departure']")))
                time.sleep(0.5) # Small pause for elements to be fully rendered

                # Define XPaths for slider components within the active "Outbound" tab
                # The "Outbound" tab should be active by default.
                # These XPaths assume the structure within the "Times" dialog.

                departure_slider_track_xpath = times_dialog_xpath_base + "//div[.//span[text()='Departure'] and descendant::input[@aria-label='Earliest departure']]//div[@jscontroller='tbQzUe' and contains(@class, 'VfPpkd-SxecR')][1]"
                arrival_slider_track_xpath = times_dialog_xpath_base + "//div[.//span[text()='Arrival'] and descendant::input[@aria-label='Earliest arrival']]//div[@jscontroller='tbQzUe' and contains(@class, 'VfPpkd-SxecR')][1]"

                # Outbound Departure Times
                if out_dep_earliest is not None:
                    _set_slider_thumb_value(driver, wait,
                        thumb_xpath=times_dialog_xpath_base + "//div[@jsname='PFprWc' and .//input[@aria-label='Earliest departure']]",
                        input_xpath=times_dialog_xpath_base + "//input[@aria-label='Earliest departure']",
                        slider_track_xpath=departure_slider_track_xpath,
                        target_value=out_dep_earliest,
                        slider_label="Outbound Earliest Departure")
                
                if out_dep_latest is not None:
                    _set_slider_thumb_value(driver, wait,
                        thumb_xpath=times_dialog_xpath_base + "//div[@jsname='PFprWc' and .//input[@aria-label='Latest departure']]",
                        input_xpath=times_dialog_xpath_base + "//input[@aria-label='Latest departure']",
                        slider_track_xpath=departure_slider_track_xpath, 
                        target_value=out_dep_latest,
                        slider_label="Outbound Latest Departure")

                # Outbound Arrival Times
                if out_arr_earliest is not None:
                    _set_slider_thumb_value(driver, wait,
                        thumb_xpath=times_dialog_xpath_base + "//div[@jsname='PFprWc' and .//input[@aria-label='Earliest arrival']]",
                        input_xpath=times_dialog_xpath_base + "//input[@aria-label='Earliest arrival']",
                        slider_track_xpath=arrival_slider_track_xpath,
                        target_value=out_arr_earliest,
                        slider_label="Outbound Earliest Arrival")

                if out_arr_latest is not None:
                    _set_slider_thumb_value(driver, wait,
                        thumb_xpath=times_dialog_xpath_base + "//div[@jsname='PFprWc' and .//input[@aria-label='Latest arrival']]",
                        input_xpath=times_dialog_xpath_base + "//input[@aria-label='Latest arrival']",
                        slider_track_xpath=arrival_slider_track_xpath,
                        target_value=out_arr_latest,
                        slider_label="Outbound Latest Arrival")
                
                # Close Times dialog using ESCAPE key
                print("      Attempting to close 'Times' dialog by sending ESCAPE key...")
                # Ensure focus is on an element that can receive key presses, like the body
                body_element = driver.find_element(By.XPATH, "//body")
                body_element.send_keys(Keys.ESCAPE)
                print("      Sent ESCAPE key to close 'Times' dialog.")
                time.sleep(2) # Pause for results to refresh

                search_success_status = "INFO_ALL_FILTERS_APPLIED" 
                search_message = "Successfully applied Stops, Price, and Times filters."
                print("    Successfully applied 'Times' filter and closed dialog.")

            except Exception as e_times_set:
                print(f"    Error applying Times filter values or closing dialog: {e_times_set}")
                search_success_status = "ERROR_FILTER_TIMES_SETTING"
                search_message = f"Error setting Times filter values: {e_times_set}"
        
        except TimeoutException as e_filter_stops:
            print(f"    Timeout while trying to apply 'Stops' filter: {e_filter_stops}")
            search_success_status = "ERROR_FILTER_STOPS_TIMEOUT"
            search_message = f"Timeout applying 'Stops: Nonstop' filter: {e_filter_stops}"
        except Exception as e_filter_stops_general:
            print(f"    Error applying 'Stops' filter: {e_filter_stops_general}")
            search_success_status = "ERROR_FILTER_STOPS_GENERAL"
            search_message = f"General error applying 'Stops: Nonstop' filter: {e_filter_stops_general}"

        # The search_success_status and search_message are updated by the filter block above
        # or retain their default error values if an earlier critical error occurred.
        flight_results_summary.append({"status": search_success_status, "message": search_message})
        
        # --- VALIDATION STEP 2: After all filters, before data extraction (if any) ---
        if not run_headless:
            print("    [VALIDATION 2] All filters applied. Pausing for 30 seconds to verify final filtered results...")
            time.sleep(30) # Pause to observe final results when not headless

        return flight_results_summary

        # print(f"    Page source length: {len(html_content)}")
        # time.sleep(30) # Keep browser open for a bit longer to see the result if not headless # Old pause, replaced

    except TimeoutException as e:
        search_success_status = "ERROR_TIMEOUT"
        search_message = f"A timeout occurred: {e}"
        print(f"    Timeout: {e}")
        print("DEBUG: Pausing for 60 seconds due to TIMEOUT to allow inspection...")
        time.sleep(60) # PAUSE FOR DEBUGGING TIMEOUTS
    except NoSuchElementException as e:
        search_success_status = "ERROR_NO_SUCH_ELEMENT"
        search_message = f"Could not find a critical element: {e}"
        print(f"    NoSuchElement: {e}")
        # driver.save_screenshot("no_such_element_error.png")
        print("DEBUG: Pausing for 60 seconds to allow inspection of the browser before quit...")
        time.sleep(60) # PAUSE FOR DEBUGGING
    except Exception as e:
        search_success_status = "ERROR_SELENIUM_GENERAL"
        search_message = f"An unexpected error occurred during Selenium automation: {e}"
        print(f"    Selenium Error: {e}")
        # driver.save_screenshot("general_selenium_error.png")
    finally:
        if driver:
            driver.quit()
            print("    WebDriver closed.")
    
    # flight_results_summary.append({"status": search_success_status, "message": search_message})
    # return flight_results_summary
    # The actual return is now handled within the try block after data extraction attempt

# --- Main function to be called by main.py (adapter) ---
def find_flights(trip_period, traveler_info, destination_airports, run_headless=True):
    # This is the function main.py will call. It now uses Selenium.
    return find_flights_selenium(trip_period, traveler_info, destination_airports, run_headless=run_headless)

if __name__ == '__main__':
    print("Testing flight_finder.py with Selenium (REAL BROWSER AUTOMATION)...")
    # For direct testing, run with headless=False to see the browser actions.
    # Set run_headless_test = False to see the browser.
    run_headless_test = False # <<< CHANGE TO True for background execution

    sample_trip = {
        'start_date_str': '2025-06-06', 
        'end_date_str': '2025-06-08',   
        'description': 'Sample Weekend SFO-LAS'
    }
    sawim = {
        'name': 'Sawim',
        'origin_airport_options': ['SFO'],
        'origin_city': 'San Francisco', 
        'budget': 300,  
        'preferred_times': {
            'outbound_departure_earliest': 8,  # 8 AM (value for 0-23 range)
            'outbound_departure_latest': 22, # 10 PM (value for 1-24 range, so 22 is 10 PM)
            'outbound_arrival_earliest': 9,    # 9 AM (value for 0-23 range)
            'outbound_arrival_latest': 17     # 5 PM (value for 1-24 range, so 17 is 5 PM)
        }
    }
    destination_aps = ['LAS']
    # dom_info = {
    #     'name': 'Dom',
    #     'origin_airport_options': ['JFK'],
    #     'origin_city': 'New York',
    #     'budget': 500
    # }

    print(f"\nAttempting search for: {sawim['name']} to {destination_aps[0]} for {sample_trip['description']}")
    flights = find_flights(sample_trip, sawim, destination_aps, run_headless=run_headless_test)
    
    print("\n--- Selenium Flight Search Result ---")
    if flights:
        print(json.dumps(flights, indent=2))
    else:
        print("No flight information returned or an error occurred.")

    # Example for Dom (could add if needed for more testing)
    # dom_info = {\n    #     'name': 'Dom',\n    #     'origin_airport_options': ['JFK']\n    # }\n    # print(f\"\\nAttempting search for: {dom_info['name']} to {dest_airports[0]} for {sample_trip_period['description']}\")\n    # dom_flights = find_flights(sample_trip_period, dom_info, dest_airports)\n    # if dom_flights:\n    #     print(\"Dom's flight options:\")\n    #     print(json.dumps(dom_flights, indent=2))\n 