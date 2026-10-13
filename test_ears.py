import speech_recognition as sr

recognizer = sr.Recognizer()

with sr.Microphone() as mic:
    print("Adjusting for background noise... stay quiet for 1 second")
    recognizer.adjust_for_ambient_noise(mic, duration=1)
    print("Speak now!")
    try:
        audio = recognizer.listen(mic, timeout=5, phrase_time_limit=10)
    except sr.WaitTimeoutError:
        print("I heard nothing. Check your microphone.")
        raise SystemExit

print("Understanding...")
try:
    text = recognizer.recognize_google(audio, language="en-IN")
    print("You said:", text)
except sr.UnknownValueError:
    print("Sorry, I could not understand the audio.")
except sr.RequestError:
    print("Could not reach the speech service. Check your internet.")