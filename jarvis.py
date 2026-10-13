import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import asyncio
import inspect
import queue
import re
import threading
import time
import speech_recognition as sr
import pyttsx3
import edge_tts
import pygame
import ollama
from google import genai
from google.genai import types, errors

from rag import retrieve
from tools import TOOLS, ALERTS
from fast_commands import try_fast

# =============== SETTINGS ===============
BRAIN = "auto"                       # "auto" = Gemini first, Ollama as backup | "ollama" | "gemini"
MODELS = ["gemini-3.8-flash"]        # keep the Gemini names that work for you
OLLAMA_MODEL = "llama3.2"            # the chat model you pulled

USE_NATURAL_VOICE = True
NATURAL_VOICE = "en-GB-RyanNeural"   # also try en-IN-PrabhatNeural or en-IN-NeerjaNeural
VOICE_INDEX = 1                      # backup offline voice
SPEECH_RATE = 175

WAKE_WORDS = ["jarvis", "jervis", "jarvish", "garvis"]
EXIT_WORDS = ["goodbye", "shut down", "exit"]
SLEEP_WORDS = ["go to sleep", "that is all", "that's all", "thank you jarvis"]
ACTIVE_SECONDS = 15
MAX_HISTORY = 12

SYSTEM = (
    "You are Jarvis, a friendly voice assistant. "
    "Your replies are spoken aloud, so keep them to 1-3 short sentences. "
    "Never use markdown, bullet points, asterisks or emojis. "
    "Use your tools whenever the user asks for the time, the weather, to open "
    "something, to search, or to set a timer. "
    "If the user asks about their personal life and no notes were given, "
    "say you don't have that information. Never make up personal facts."
)

try:
    client = genai.Client()          # reads GEMINI_API_KEY
except Exception:
    client = None                    # no key: Gemini is skipped, Ollama still works
    print("(no Gemini key found, using Ollama only)")

recognizer = sr.Recognizer()
recognizer.pause_threshold = 0.7

history = []                         # [{"role": "user" or "assistant", "content": text}]
FUNCS = {f.__name__: f for f in TOOLS}
gemini_paused_until = 0              # after a quota error, skip Gemini for a while
ollama_tools_ok = True
announced_fallback = False


# =============== UI HOOKS ===============
def ui_state(state):      # "starting", "sleeping", "listening", "thinking", "speaking", "muted"
    pass

def ui_log(who, text):    # who = "You", "Jarvis" or "System"
    pass

STOP = threading.Event()      # set by the window to stop Jarvis
MUTED = threading.Event()     # set by the window's Mute button
TYPED = queue.Queue()         # commands typed in the window


# =============== MOUTH ===============
def speak_natural(text):
    path = "jarvis_speech.mp3"
    asyncio.run(edge_tts.Communicate(text, NATURAL_VOICE).save(path))
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()


def speak_offline(text):
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    idx = VOICE_INDEX if VOICE_INDEX < len(voices) else 0
    engine.setProperty("voice", voices[idx].id)
    engine.setProperty("rate", SPEECH_RATE)
    engine.say(text)
    engine.runAndWait()


def speak(text):
    print("Jarvis:", text)
    ui_log("Jarvis", text)
    ui_state("speaking")
    clean = text.replace("*", "").replace("#", "")
    if USE_NATURAL_VOICE:
        try:
            speak_natural(clean)
            return
        except Exception as e:
            print("(natural voice failed, using offline voice:", str(e)[:100], ")")
    speak_offline(clean)


# =============== EARS ===============
def listen(timeout=5, limit=12):
    with sr.Microphone() as mic:
        try:
            audio = recognizer.listen(mic, timeout=timeout, phrase_time_limit=limit)
        except sr.WaitTimeoutError:
            return None
    try:
        return recognizer.recognize_google(audio, language="en-IN")
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        print("(speech service unreachable, check internet)")
        return None


# =============== WAKE WORD ===============
def has_wake_word(text):
    return any(w in text for w in WAKE_WORDS)


def remove_wake_word(text):
    for w in WAKE_WORDS:
        text = text.replace(w, "")
    text = text.strip(" ,.!?")
    text = re.sub(r"^(hey|hi|hello|ok|okay)\b[ ,]*", "", text).strip(" ,.!?")
    return text


# =============== BRAIN: helpers ===============
def retry_seconds(error):
    m = re.search(r"retry in ([\d.]+)s", str(error))
    return float(m.group(1)) if m else 20


def trim_history():
    while len(history) > MAX_HISTORY:
        history.pop(0)
    while history and history[0]["role"] != "user":
        history.pop(0)


def needs_notes(text):
    """Only personal questions need a search of your notes."""
    t = " " + text.lower() + " "
    return any(w in t for w in (" my ", " me ", " mine ", " i ", " i'm ", " our "))


def to_ollama_tool(fn):
    """Describe one of our Python functions to Ollama (name, purpose, inputs)."""
    props, required = {}, []
    for name, p in inspect.signature(fn).parameters.items():
        kind = {float: "number", int: "integer", bool: "boolean"}.get(p.annotation, "string")
        props[name] = {"type": kind, "description": name}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "function",
            "function": {"name": fn.__name__,
                         "description": inspect.getdoc(fn) or fn.__name__,
                         "parameters": {"type": "object", "properties": props,
                                        "required": required}}}


def run_tool(name, args):
    """Run the tool the model asked for. Small models sometimes send numbers as text."""
    fn = FUNCS.get(name)
    if not fn:
        return "Unknown tool"
    params = inspect.signature(fn).parameters
    clean = {}
    for k, v in (args or {}).items():
        if k not in params:
            continue
        ann = params[k].annotation
        try:
            if ann is float:
                v = float(v)
            elif ann is int:
                v = int(float(v))
            elif ann is str:
                v = str(v)
        except (TypeError, ValueError):
            pass
        clean[k] = v
    try:
        return fn(**clean)
    except Exception as e:
        return f"Tool error: {e}"


# =============== BRAIN 1: Gemini (cloud) ===============
def ask_gemini(prompt):
    """Returns (answer, None) on success, or (None, reason) on failure."""
    global gemini_paused_until
    if client is None:
        return None, "nokey"
    if time.time() < gemini_paused_until:
        return None, "paused"

    contents = [types.Content(role="user" if m["role"] == "user" else "model",
                              parts=[types.Part(text=m["content"])])
                for m in history[:-1]]
    contents.append(types.Content(role="user", parts=[types.Part(text=prompt)]))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=TOOLS,
        max_output_tokens=150,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=2),
    )

    problem = "busy"
    for model in MODELS:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model, contents=contents, config=config)
                return ((response.text or "").strip() or "Sorry, I have no answer for that."), None
            except errors.ServerError:
                problem = "busy"
                time.sleep(2)
            except errors.ClientError as e:
                msg = str(e)
                if e.code == 429:
                    if "PerDay" in msg:
                        problem = "daily"
                        print(f"(Gemini daily free limit reached for {model})")
                    else:
                        problem = "minute"
                        wait = retry_seconds(e)
                        print(f"(Gemini per-minute limit, Google says wait {wait:.0f}s)")
                        if wait <= 8 and attempt < 1:
                            time.sleep(wait + 1)
                            continue
                else:
                    problem = "error"
                    print("Gemini error:", msg[:200])
                break

    if problem == "daily":
        gemini_paused_until = time.time() + 1800     # skip Gemini for 30 minutes
    elif problem == "minute":
        gemini_paused_until = time.time() + 70       # skip Gemini for 70 seconds
    return None, problem


# =============== BRAIN 2: Ollama (local) ===============
def ask_ollama(prompt):
    """Returns (answer, None) on success, or (None, reason) on failure."""
    global ollama_tools_ok
    messages = ([{"role": "system", "content": SYSTEM}]
                + history[:-1]
                + [{"role": "user", "content": prompt}])
    try:
        for _ in range(3):                         # at most 3 rounds, no endless loops
            kwargs = dict(model=OLLAMA_MODEL, messages=messages, keep_alive="30m",
                          options={"num_predict": 150})
            if ollama_tools_ok:
                kwargs["tools"] = [to_ollama_tool(f) for f in TOOLS]
            try:
                reply = ollama.chat(**kwargs)
            except ollama.ResponseError as e:
                if ollama_tools_ok and "tool" in str(e).lower():
                    ollama_tools_ok = False
                    print("(this Ollama model has no tool support, tools turned off)")
                    continue
                raise
            msg = reply.message
            if not msg.tool_calls:                 # final answer
                return ((msg.content or "").strip() or "Sorry, I have no answer for that."), None
            messages.append(msg)                   # the model asked for tools: run them
            for call in msg.tool_calls:
                result = run_tool(call.function.name, call.function.arguments)
                messages.append({"role": "tool", "tool_name": call.function.name,
                                 "content": str(result)})
        return "Sorry, I could not finish that request.", None
    except Exception as e:
        print("Ollama error:", str(e)[:200])
        return None, "ollama"


def warm_up_ollama():
    """Load the local model into memory in the background so the first answer is faster."""
    try:
        ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": "hi"}],
                    keep_alive="30m", options={"num_predict": 1})
        print("(Ollama model ready)")
    except Exception as e:
        print("(Ollama is not reachable:", str(e)[:100], ")")


# =============== BRAIN: the decision ===============
def think(user_text):
    global announced_fallback

    # 0. FAST PATH: simple commands run instantly with no AI at all
    quick = try_fast(user_text)
    if quick:
        return quick

    ui_state("thinking")

    # 1. RAG: only for personal questions
    notes = []
    if needs_notes(user_text):
        try:
            notes = retrieve(user_text)
        except Exception as e:
            print("(notes lookup failed:", str(e)[:100], ")")

    if notes:
        context = "\n".join(f"- {chunk}" for chunk, score in notes)
        print("(used notes:", [(c, round(s, 2)) for c, s in notes], ")")
        prompt = (f"Notes about the user:\n{context}\n\n"
                  f"Use the notes only if they help answer. Question: {user_text}")
    else:
        prompt = user_text

    history.append({"role": "user", "content": user_text})

    # 2. Pick the brain(s) to try, in order
    order = {"gemini": ["gemini"], "ollama": ["ollama"],
             "auto": ["gemini", "ollama"]}.get(BRAIN, ["gemini", "ollama"])

    problem = "error"
    for brain in order:
        answer, problem = ask_gemini(prompt) if brain == "gemini" else ask_ollama(prompt)
        if answer:
            print(f"(brain: {brain})")
            if brain == "ollama" and "gemini" in order and not announced_fallback:
                announced_fallback = True
                ui_log("System", "Gemini is unavailable, using the local Ollama brain.")
            elif brain == "gemini":
                announced_fallback = False
            history.append({"role": "assistant", "content": answer})
            trim_history()
            return answer

    history.pop()
    if BRAIN == "auto":
        return "Both of my brains are unavailable. Please check that Ollama is running."
    if problem == "ollama":
        return "My local brain is not responding. Please check that Ollama is running."
    return {"daily": "My free daily Gemini limit is finished.",
            "minute": "I am going too fast for the free limit. Please try again in a minute.",
            "busy": "The AI service is busy right now. Please try again in a moment.",
            "paused": "Gemini is resting after a limit. Please try again shortly.",
            "nokey": "No Gemini key was found.",
            }.get(problem, "Something went wrong. Check the terminal for details.")


# =============== MAIN LOOP ===============
def run():
    try:                                   # offline voice needs COM started in this thread
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass

    if BRAIN in ("ollama", "auto"):
        threading.Thread(target=warm_up_ollama, daemon=True).start()

    ui_state("starting")
    ui_log("System", "Calibrating microphone... stay quiet for 2 seconds")
    print("Calibrating microphone... stay quiet for 2 seconds")
    with sr.Microphone() as mic:
        recognizer.adjust_for_ambient_noise(mic, duration=2)
    recognizer.dynamic_energy_threshold = True

    speak("Jarvis is ready. Say my name when you need me.")

    active = False
    last_active = 0

    try:
        while not STOP.is_set():
            while not ALERTS.empty():              # finished timers
                speak(ALERTS.get())

            # ---- commands typed in the window (no wake word needed) ----
            try:
                typed = TYPED.get_nowait()
            except queue.Empty:
                typed = None
            if typed:
                ui_log("You", typed)
                lower = typed.lower().strip()
                if any(w in lower for w in EXIT_WORDS):
                    speak("Goodbye! Shutting down.")
                    break
                speak(think(lower))
                active = True
                last_active = time.time()
                continue

            # ---- microphone muted from the window ----
            if MUTED.is_set():
                ui_state("muted")
                time.sleep(0.3)
                continue

            ui_state("listening" if active else "sleeping")
            print("\n" + ("Listening (awake)..." if active else "Sleeping... say 'Jarvis'"))
            text = listen()

            if not text:
                if active and time.time() - last_active > ACTIVE_SECONDS:
                    active = False
                    print("(going back to sleep)")
                continue

            print("Heard:", text)
            lower = text.lower()

            if not active:
                if not has_wake_word(lower):
                    continue
                active = True
                ui_log("You", text)
                lower = remove_wake_word(lower)
                if not lower:
                    speak("Yes?")
                    last_active = time.time()
                    continue
            else:
                ui_log("You", text)

            if any(w in lower for w in EXIT_WORDS):
                speak("Goodbye! Shutting down.")
                break
            if any(w in lower for w in SLEEP_WORDS):
                speak("Okay, going to sleep.")
                active = False
                continue

            speak(think(lower))
            last_active = time.time()
    except KeyboardInterrupt:
        print("\nStopped by user.")


if __name__ == "__main__":
    run()