import re
import tools

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "linkedin": "https://www.linkedin.com",
    "instagram": "https://www.instagram.com",
    "maps": "https://maps.google.com",
}

NUMBER_WORDS = {"half": 0.5, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30}


def try_fast(text):
    """Handle simple commands with no AI at all.
    Returns the sentence to speak, or None if the AI should handle it."""
    t = text.lower().strip(" .?!,")
    t = re.sub(r"^(can you|could you|please)\s+", "", t)

    # ---- time and date ----
    if re.search(r"what('s| is) the (time|date)|what time is it|current time|time now|today's date", t):
        return "It is " + tools.get_time_and_date() + "."

    # ---- timer ----
    if "timer" in t:
        m = re.search(r"(\d+(?:\.\d+)?|[a-z]+)\s*(seconds?|minutes?|mins?|hours?)", t)
        if m:
            num = m.group(1)
            try:
                amount = float(num)
            except ValueError:
                amount = NUMBER_WORDS.get(num)
            if amount:
                unit = m.group(2)
                minutes = amount / 60 if unit.startswith("sec") else \
                          amount * 60 if unit.startswith("hour") else amount
                tools.set_timer(minutes, "timer")
                return f"Timer set for {num} {unit}."

    # ---- search ----
    m = re.match(r"(?:search|google)(?:\s+google)?(?:\s+for)?\s+(.+)", t)
    if m:
        tools.search_google(m.group(1))
        return f"Searching for {m.group(1)}."

    # ---- open a website or an approved app ----
    m = re.search(r"\b(?:open|launch)\s+(.+)", t)
    if m:
        target = re.sub(r"\b(for me|please|app|application|website|site|the)\b", "", m.group(1))
        target = " ".join(target.split())
        if target in SITES:
            tools.open_website(SITES[target])
            return f"Opening {target}."
        if target in tools.APPS:
            tools.open_app(target)
            return f"Opening {target}."
        if "." in target and " " not in target:          # something like youtube.com
            tools.open_website(target)
            return f"Opening {target}."
        return f"I am not allowed to open {target}."

    return None          # not a simple command, so the AI decides