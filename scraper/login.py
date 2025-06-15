import instaloader
import getpass

def login_and_save_session():
    print("🔐 Instagram Login to Save Session")

    username = input("Enter Instagram username: ")
    password = getpass.getpass("Enter Instagram password (input hidden): ")

    loader = instaloader.Instaloader()

    try:
        loader.login(username, password)
        loader.save_session_to_file()
        print("✅ Login successful. Session saved for reuse.")
    except instaloader.exceptions.BadCredentialsException:
        print("❌ Login failed: Incorrect username or password.")
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        print("⚠️ 2FA required. This script does not handle 2FA currently.")
    except instaloader.exceptions.ConnectionException as e:
        print(f"🚫 Connection error: {e}")
    except instaloader.exceptions.LoginRequiredException as e:
        print(f"⚠️ Login required: {e}")
    except Exception as e:
        print(f"❌ Unknown error: {e}")

if __name__ == "__main__":
    login_and_save_session()
