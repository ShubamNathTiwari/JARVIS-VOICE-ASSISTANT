# 🤖 JARVIS: Voice AI Assistant

A voice-controlled AI assistant for Windows, inspired by Alexa and Iron Man's JARVIS.
Say "Jarvis", ask a question or give a command, and it answers out loud.
It uses an LLM brain, RAG over personal notes, and an agent that can run tools.

![Jarvis demo](screenshots/demo.gif)

## 📸 Screenshots

| Main window | Mini mode |
|---|---|
| ![Main window](screenshots/ui-main.png) | ![Mini mode](screenshots/ui-mini.png) |

## ✨ Features

- 🎙️ **Wake word** ("Jarvis") and hands-free voice conversation
- 🧠 **Two brains:** Google Gemini (cloud) with automatic fallback to Ollama (local, free, no limits)
- 📚 **RAG:** answers questions from your own notes using embeddings and vector search
- 🛠️ **Agentic tools:** time, weather, web search, open websites, approved apps, timers
- ⚡ **Fast path:** simple commands run instantly with zero AI calls
- 🗣️ **Natural voice** (edge-tts) with an offline backup voice (pyttsx3)
- 🖥️ **Animated desktop UI** built with Tkinter: glowing orb, themes, chat bubbles, mini mode

## 🏗️ How it works
Microphone → Wake word → Speech-to-Text
↓
Fast commands? ── yes → run tool instantly
↓ no
RAG (search your notes) → LLM (Gemini or Ollama) ⇄ Tools
↓
Text-to-Speech → Speaker


| Part | Technology |
|---|---|
| Speech-to-Text | SpeechRecognition (Google Web Speech) |
| LLM | Google Gemini API, Ollama (llama3.2) |
| RAG | Embeddings (Ollama `nomic-embed-text`) + NumPy cosine similarity |
| Agent tools | Python functions with LLM function calling |
| Text-to-Speech | edge-tts, pyttsx3 |
| UI | Tkinter (Python only) |

## 🚀 Setup (Windows 10/11)

1. **Install Python 3.12** from python.org (tick "Add to PATH" and "tcl/tk").
2. **Clone and create an environment**
```bat
   git clone https://github.com/[your-username]/jarvis-voice-assistant.git
   cd jarvis-voice-assistant
   python -m venv jarvis_env
   jarvis_env\Scripts\activate.bat
   pip install -r requirements.txt
```
3. **Get a free Gemini API key** at https://aistudio.google.com and set it:
```bat
   setx GEMINI_API_KEY "your-key-here"
```
   Close and reopen the terminal afterwards.
4. **Install Ollama** from https://ollama.com, then:
```bat
   ollama pull llama3.2
   ollama pull nomic-embed-text
```
5. **Add your notes:** copy `knowledge/my_notes.example.txt` to `knowledge/my_notes.txt`, edit it, then build the index:
```bat
   python rag.py
```
6. **Run**
```bat
   python jarvis_ui.py
```

Use `python jarvis_ui.py demo` to preview the UI without using any API quota.

## 💬 Example commands

- "Jarvis, what time is it?"
- "Open YouTube" / "Open notepad"
- "Search Google for Python projects"
- "Set a timer for 5 minutes"
- "What's the weather in Mumbai?"
- "When does my exam start?" (answered from your notes)
- "Explain machine learning in simple words"

## 📁 Project structure

├── jarvis.py # voice loop, wake word, brains (Gemini + Ollama)
├── jarvis_ui.py # Tkinter window with animated orb
├── rag.py # embeddings and vector search over your notes
├── tools.py # agent tools (time, weather, apps, timers...)
├── fast_commands.py # instant commands without AI
├── knowledge/ # your notes (example file included)
└── requirements.txt


## ⚠️ Limitations

- Windows only (uses `winsound` and Windows speech voices).
- Speech recognition and the natural voice need an internet connection.
- Small local models are less accurate than Gemini, especially with tools.
- Gemini's free tier has daily and per-minute limits; Jarvis switches to Ollama when they run out.

## 🔒 Safety design

- Apps can only be opened from an approved list.
- The agent loop is capped at a few tool calls per request.
- API keys are read from environment variables, never stored in code.

## 🗺️ Roadmap

- [ ] Offline wake word (openWakeWord)
- [ ] Offline speech recognition (Whisper)
- [ ] Long-term memory
- [ ] More tools: calendar, email, music

## 👤 Author

**[Shubam Nath Tiwari]**, [https://www.linkedin.com/in/shubam-nath-tiwari-335502313/] · [https://github.com/ShubamNathTiwari/JARVIS-personal-voice-assistant/blob/main/readme.md]

## 📄 License

MIT License

'-----------------------------------------------------------------------------'

Your project folder should look like this:
C:\JARVIS
├── .gitignore
├── README.md
├── requirements.txt
├── jarvis.py
├── jarvis_ui.py
├── rag.py
├── tools.py
├── fast_commands.py
├── test_rag.py
├── test_tools.py        (optional)
├── list_models.py       (optional)
└── knowledge\
    └── my_notes.example.txt
