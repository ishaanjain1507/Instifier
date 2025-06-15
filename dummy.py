import requests

username = "instagram"  # Replace with the desired Instagram username
url = f"https://www.instagram.com/{username}/?__a=1&__d=dis"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    print(response.json())
else:
    print(f"Failed to fetch data: {response.status_code}. {response.text}, {response.reason}, {response.headers}, {response.content}")