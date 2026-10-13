import pyttsx3

engine = pyttsx3.init()

# Show all voices installed on your PC
voices = engine.getProperty("voices")
for i, v in enumerate(voices):
    print(i, v.name)

# Settings
engine.setProperty("rate", 175)      # speed: lower = slower
engine.setProperty("volume", 1.0)    # 0.0 to 1.0
engine.setProperty("voice", voices[1].id)   # try 0, 1, 2... to change voice

engine.say("Hello, I am Jarvis. Your voice assistant is now online.")
engine.runAndWait()