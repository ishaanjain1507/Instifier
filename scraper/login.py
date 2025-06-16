from dotenv import load_dotenv
import os

load_dotenv()
login_credentials = {"username": os.getenv("IG_USERNAME"), "password": os.getenv("IG_PASSWORD")}

def get_login_credentials():
    """
    Returns the Instagram login credentials from environment variables.
    
    Returns:
        dict: A dictionary containing the Instagram username and password.
    """
    if not login_credentials["username"] or not login_credentials["password"]:
        raise ValueError("Instagram username and password must be set in environment variables.")
    
    return login_credentials

def login():
    """
    Logs into Instagram using the credentials stored in environment variables.

    Returns:
        str: A message indicating successful login.
    """
    credentials = get_login_credentials()
    # Here you would implement the actual login logic, e.g., using requests or selenium.
    # For now, we just return a success message.
    
    return f"Logged in as {credentials['username']}"