import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
import os.path

# Scopes define the permissions the script requests from Google.
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file' # Added to manage files created by the app, potentially needed for folder_id
]
CREDENTIALS_FILE = 'credentials.json' # Downloaded from Google Cloud Console
TOKEN_FILE = 'token.json' # Stores user's access and refresh tokens

def get_authenticated_service():
    """Authenticates with Google Sheets API using OAuth 2.0 for a desktop app.
    Manages token refresh and user authorization flow.
    """
    creds = None
    # The TOKEN_FILE stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists(TOKEN_FILE):
        try:
            creds = UserCredentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"Error loading token file: {e}. Will attempt to re-authenticate.")
            creds = None # Force re-authentication

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Credentials expired, attempting to refresh...")
                creds.refresh(Request())
                print("Credentials refreshed successfully.")
            except RefreshError as e:
                print(f"Error refreshing access token: {e}")
                print("Please re-authenticate by deleting token.json and running the script again.")
                # Fall through to re-authorize if refresh fails
                creds = None 
            except Exception as e: # Catch any other unexpected error during refresh
                print(f"Unexpected error during token refresh: {e}")
                creds = None
        
        if not creds or not creds.valid: # Re-check creds validity after potential refresh
            if os.path.exists(CREDENTIALS_FILE):
                # Load client secrets from credentials.json
                # This uses 'google.oauth2.credentials.Credentials.from_authorized_user_info' 
                # implicitly by gspread.oauth() if token.json is not found or invalid.
                # For a desktop app, gspread.oauth() will initiate the flow.
                print("No valid token found, initiating new OAuth2 flow...")
                try:
                    # gspread.oauth() handles the desktop app flow,
                    # including prompting the user to authorize in their browser
                    # and saving the new token to TOKEN_FILE (default location).
                    gc = gspread.oauth(
                        credentials_filename=CREDENTIALS_FILE,
                        authorized_user_filename=TOKEN_FILE,
                        scopes=SCOPES
                    )
                    print(f"Authentication successful. Token saved to {TOKEN_FILE}")
                    return gc
                except Exception as e:
                    print(f"Error during OAuth flow: {e}")
                    print(f"Please ensure '{CREDENTIALS_FILE}' is correctly configured and in the project root.")
                    return None
            else:
                print(f"Error: '{CREDENTIALS_FILE}' not found. Please download it from Google Cloud Console.")
                return None
        
    # If we got here, creds should be valid (either loaded or refreshed)
    # We need to return a gspread Client object authorized with these UserCredentials
    try:
        gc = gspread.Client(auth=creds)
        # Test the connection by listing spreadsheets to ensure creds are working with gspread.Client
        gc.list_spreadsheet_files() 
        print("Successfully authenticated with existing token.")
        return gc
    except Exception as e:
        print(f"Error creating gspread client with existing credentials: {e}")
        print("Attempting to re-authenticate.")
        # If gspread.Client fails with existing creds, try the full oauth flow again
        # by removing the potentially problematic token file.
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        return get_authenticated_service() # Recursive call to re-initiate flow


def create_spreadsheet(gc, title, folder_id=None):
    """Creates a new spreadsheet with the given title.
    Optionally creates it within the specified folder_id.
    Returns the spreadsheet object or None if creation fails.
    """
    if not gc:
        print("Authentication failed, cannot create spreadsheet.")
        return None
    try:
        # Check if spreadsheet already exists (gspread.open does not use folder_id for lookup)
        # If it exists anywhere, it will be opened. If you need to ensure it's in the specific folder
        # and create a new one otherwise, the logic would be more complex (list folder contents, then check).
        # For now, we assume if it exists with this name, we use it.
        try:
            spreadsheet = gc.open(title)
            print(f"Spreadsheet '{title}' already exists (opened). URL: {spreadsheet.url}")
            # Note: If it already exists, this doesn't move it to the folder_id.
            # If you want to ensure it's in the folder, or move it, that's an additional step.
            return spreadsheet
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"Spreadsheet '{title}' not found. Creating new one...")
            try:
                spreadsheet = gc.create(title, folder_id=folder_id) # Use folder_id here
                print(f"Spreadsheet '{title}' created successfully in folder_id: '{folder_id if folder_id else 'root'}'.")
                print(f"You can view it at: {spreadsheet.url}")
            except Exception as e:
                print(f"Error creating spreadsheet with folder_id '{folder_id}': {e}")
                if folder_id: # Only attempt fallback if a folder_id was actually provided
                    print("Attempting to create spreadsheet in root directory instead (fallback).")
                    try:
                        spreadsheet = gc.create(title) # Fallback to root
                        print(f"Spreadsheet '{title}' created successfully in root (fallback).")
                        print(f"You can view it at: {spreadsheet.url}")
                    except Exception as e2:
                        print(f"Fallback creation in root also failed: {e2}")
                        return None
                else: # No folder_id was specified, and initial creation failed.
                    return None
            
            # Removed problematic sharing logic here as the creator is the owner.
            return spreadsheet # Return the successfully created spreadsheet

    except Exception as e:
        print(f"An error occurred while creating or opening the spreadsheet: {e}")
        return None

if __name__ == '__main__':
    # This part is for testing the module directly
    print("Testing sheets_manager.py...")
    google_client = get_authenticated_service()
    if google_client:
        spreadsheet_title = "Zion/Grand Canyon Trip Planning Test" # Test with a different name
        # To test folder creation here, uncomment and set a valid test_folder_id:
        # test_folder_id = "YOUR_VALID_TEST_FOLDER_ID"
        # new_sheet = create_spreadsheet(google_client, spreadsheet_title, folder_id=test_folder_id)
        new_sheet = create_spreadsheet(google_client, spreadsheet_title) # Default test to root
        if new_sheet:
            print(f"Successfully accessed/created spreadsheet for testing: {new_sheet.title}")
            # Clean up by deleting the test sheet if you want
            # try:
            #     google_client.del_spreadsheet(new_sheet.id)
            #     print(f"Test spreadsheet '{new_sheet.title}' deleted.")
            # except Exception as e:
            #     print(f"Error deleting test spreadsheet: {e}")
        else:
            print("Failed to create or access spreadsheet for testing.")
    else:
        print("Failed to authenticate with Google Sheets for testing.") 