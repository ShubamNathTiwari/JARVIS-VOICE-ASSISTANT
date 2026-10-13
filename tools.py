import datetime
import os
import queue
import subprocess
import threading
import urllib.parse
import urllib.request
import webbrowser

ALERTS = queue.Queue()     # timers drop their messages here; jarvis.py speaks them


# NOTE: Gemini reads each function's NAME, TYPE HINTS and DOCSTRING to decide
# when to use it. Clear docstrings = smarter tool choices.

def get_time_and_date() -> str:
    """Get the current local time and today's date."""
    print("(tool: get_time_and_date)")
    return datetime.datetime.now().strftime("%I:%M %p on %A, %d %B %Y")


def open_website(url: str) -> str:
    """Open a website in the browser. Give a full address such as https://www.youtube.com"""
    print(f"(tool: open_website {url})")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Opened {url}"


def search_google(query: str) -> str:
    """Search Google for the given text and show the results in the browser."""
    print(f"(tool: search_google {query})")
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote_plus(query))
    return f"Showing Google results for {query}"


# Safety: Jarvis may open ONLY apps from this approved list
APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "file explorer": "explorer",
    "chrome": "start chrome",
    "vs code": "code",
}

def open_app(app_name: str) -> str:
    """Open a desktop app. Allowed names: notepad, calculator, paint, file explorer, chrome, vs code."""
    print(f"(tool: open_app {app_name})")
    command = APPS.get(app_name.lower().strip())
    if not command:
        return f"I am not allowed to open {app_name}. Allowed apps: {', '.join(APPS)}"
    subprocess.Popen(command, shell=True)
    return f"Opened {app_name}"


def get_weather(city: str) -> str:
    """Get the current weather for a city. Ask the user for the city if they did not say one."""
    print(f"(tool: get_weather {city})")
    try:
        url = "https://wttr.in/" + urllib.parse.quote(city) + "?format=3"
        req = urllib.request.Request(url, headers={"User-Agent": "curl"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return "I could not get the weather right now."


def set_timer(minutes: float, label: str = "timer") -> str:
    """Set a countdown timer or reminder. 'minutes' can be a decimal, for example 0.5 for 30 seconds."""
    print(f"(tool: set_timer {minutes} min, {label})")

    def ring():
        ALERTS.put(f"Your {label} is done.")
        try:
            import winsound
            winsound.Beep(1000, 600)
        except Exception:
            pass

    t = threading.Timer(minutes * 60, ring)
    t.daemon = True
    t.start()
    return f"Timer set for {minutes} minutes."


TOOLS = [get_time_and_date, open_website, search_google, open_app, get_weather, set_timer]