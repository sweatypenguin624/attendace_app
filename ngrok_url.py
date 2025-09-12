import requests
import json

NGROK_API = "http://127.0.0.1:4040/api/tunnels"
OUTPUT_FILE = "static/ngrok_url.json"  # frontend can fetch this

# Ports for backend and frontend
BACKEND_PORT = "5008"
FRONTEND_PORT = "5000"

def get_tunnel_url(port):
    """Return the public ngrok URL for a given local port."""
    try:
        resp = requests.get(NGROK_API)
        data = resp.json()
        tunnels = data.get("tunnels", [])
        for t in tunnels:
            if port in t.get("config", {}).get("addr", ""):
                return t.get("public_url")
        return None
    except Exception as e:
        print(f"Error fetching ngrok tunnels for port {port}:", e)
        return None

def write_url_file(backend_url, frontend_url):
    data = {
        "backend_url": backend_url,
        "frontend_url": frontend_url
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f)
    print(f"Written backend and frontend URLs to {OUTPUT_FILE}:\nBackend: {backend_url}\nFrontend: {frontend_url}")

if __name__ == "__main__":
    backend_url = get_tunnel_url(BACKEND_PORT)
    frontend_url = get_tunnel_url(FRONTEND_PORT)

    if backend_url or frontend_url:
        write_url_file(backend_url, frontend_url)
    else:
        print("No active ngrok tunnels found for backend or frontend ports")
