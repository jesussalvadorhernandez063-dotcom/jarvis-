"""JARVIS v2: asistente de voz que corre en segundo plano en tu computadora.
Di "Jarvis" y tu orden, desde cualquier ventana."""
import asyncio, datetime, json, os, re, subprocess, sys, tempfile, threading, time, unicodedata, webbrowser
from pathlib import Path
import requests
import speech_recognition as sr
import edge_tts
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame

# ====================== CONFIGURACIÓN ======================
PROVIDER = "gemini"   # "gemini" (gratis) | "ollama" (gratis, local) | "anthropic" (de pago)
MODELS = {"gemini": "gemini-flash-latest", "ollama": "llama3.2", "anthropic": "claude-haiku-5-5"}
BASES = {"gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
         "ollama": "http://localhost:11434/v1"}
WAKE = "jarvis"            # palabra para despertarlo
VOICE = "es-MX-JorgeNeural"  # otras: es-MX-DaliaNeural, es-ES-AlvaroNeural
CIUDAD = "Xalapa"          # ciudad por defecto para el clima
VENTANA_CONVERSACION = 20  # segundos que sigue escuchando sin repetir "Jarvis"
# ===========================================================

AQUI = Path(os.environ.get("APPDATA", Path.home())) / "Jarvis"  # clave, memoria y notas viven aquí
AQUI.mkdir(parents=True, exist_ok=True)
if sys.stdout is None:  # al correr con pythonw no hay consola: guardamos el registro
    sys.stdout = sys.stderr = open(AQUI / "jarvis.log", "a", encoding="utf-8", buffering=1)

def leer_clave():
    f = AQUI / "clave.txt"
    if f.exists():
        return f.read_text().strip()
    if PROVIDER == "ollama":
        return ""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk(); root.withdraw()
        k = simpledialog.askstring("JARVIS", "Pega tu clave de API de Google AI Studio\n(aistudio.google.com):", show="*")
        root.destroy()
        if k:
            f.write_text(k.strip()); return k.strip()
    except Exception as e:
        print("No pude pedir la clave:", e)
    return ""
KEY = leer_clave()
MEMORIA = AQUI / "memoria.json"
NOTAS = AQUI / "notas.txt"
historial = json.loads(MEMORIA.read_text(encoding="utf-8")) if MEMORIA.exists() else []
hablando = threading.Event()
ultima = 0.0

def sistema():
    ahora = datetime.datetime.now().strftime("%A %d de %B de %Y, %H:%M")
    return ("Eres JARVIS, el asistente personal de voz de tu usuario, con el estilo educado, ingenioso y eficiente "
            "del de Iron Man. Responde siempre en español, de forma breve (una a tres oraciones), sin markdown, "
            "sin listas, sin emojis, porque tu respuesta se lee en voz alta. Si no sabes algo, dilo. "
            f"Fecha y hora actuales: {ahora}.")

# ---------- Cerebro (IA) ----------
def preguntar_ia(texto):
    global historial
    historial.append({"role": "user", "content": texto})
    historial = historial[-20:]
    while historial and historial[0]["role"] != "user":
        historial.pop(0)
    try:
        if PROVIDER == "anthropic":
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=60,
                headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": MODELS[PROVIDER], "max_tokens": 400, "system": sistema(), "messages": historial})
            r.raise_for_status()
            resp = r.json()["content"][0]["text"]
        else:
            r = requests.post(BASES[PROVIDER] + "/chat/completions", timeout=60,
                headers={"Authorization": "Bearer " + (KEY or "ollama")},
                json={"model": MODELS[PROVIDER], "max_tokens": 400,
                      "messages": [{"role": "system", "content": sistema()}] + historial})
            r.raise_for_status()
            resp = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("Error de IA:", e)
        historial.pop()
        return "No pude conectar con mi cerebro. Revisa tu clave y tu conexión a internet."
    historial.append({"role": "assistant", "content": resp})
    MEMORIA.write_text(json.dumps(historial, ensure_ascii=False), encoding="utf-8")
    return resp

# ---------- Voz ----------
def limpiar(t):
    t = re.sub(r"https?://\S+", "", t)
    return re.sub(r"[*#_`>]", "", t).strip()

def hablar(texto):
    texto = limpiar(texto)
    print("JARVIS:", texto)
    if not texto:
        return
    hablando.set()
    try:
        mp3 = Path(tempfile.gettempdir()) / "jarvis_voz.mp3"
        asyncio.run(edge_tts.Communicate(texto, VOICE).save(str(mp3)))
        pygame.mixer.music.load(str(mp3))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
        pygame.mixer.music.unload()
    except Exception as e:
        print("Error de voz:", e)
    finally:
        time.sleep(0.4)
        hablando.clear()

# ---------- Herramientas ----------
def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()

SITIOS = {"youtube": "https://www.youtube.com", "google": "https://www.google.com", "gmail": "https://mail.google.com",
          "whatsapp": "https://web.whatsapp.com", "netflix": "https://www.netflix.com", "github": "https://github.com",
          "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai", "maps": "https://maps.google.com"}
APPS_WIN = {"calculadora": "calc", "bloc de notas": "notepad", "explorador": "explorer", "word": "winword",
            "excel": "excel", "powerpoint": "powerpnt", "chrome": "chrome", "spotify": "spotify", "paint": "mspaint"}

def abrir(nombre):
    for k, url in SITIOS.items():
        if k in nombre:
            webbrowser.open(url)
            return f"Abriendo {k}."
    if sys.platform == "win32":
        for k, cmd in APPS_WIN.items():
            if k in nombre:
                subprocess.Popen(f'start "" {cmd}', shell=True)
                return f"Abriendo {k}."
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-a", nombre.title()])
        return f"Intentando abrir {nombre}."
    return f"No conozco la aplicación {nombre}. Puedes agregarla a la lista APPS_WIN en mi código."

def temporizador(n, unidad):
    seg = n * {"segundo": 1, "minuto": 60, "hora": 3600}[unidad]
    threading.Timer(seg, lambda: hablar(f"Tu temporizador de {n} {unidad}{'s' if n != 1 else ''} ha terminado.")).start()
    return f"Temporizador de {n} {unidad}{'s' if n != 1 else ''} iniciado."

def clima(ciudad):
    try:
        r = requests.get(f"https://wttr.in/{ciudad}?format=%C,+%t,+humedad+%h&lang=es", timeout=15)
        return f"En {ciudad}: {r.text.strip()}."
    except Exception:
        return "No pude consultar el clima ahora."

def captura():
    from PIL import ImageGrab
    carpeta = Path.home() / "Pictures"
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / f"captura_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab().save(ruta)
    return "Captura guardada en tu carpeta de imágenes."

def nota(texto):
    with open(NOTAS, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] {texto}\n")
    return "Anotado."

def leer_notas():
    if not NOTAS.exists():
        return "Aún no tienes notas."
    return "Tus últimas notas: " + " ".join(l.split("] ", 1)[-1].strip() + "." for l in NOTAS.read_text(encoding="utf-8").splitlines()[-5:])

def comando_local(q, raw):
    global historial
    if re.search(r"\b(apagate|cierrate|adios jarvis|hasta luego)\b", q):
        hablar("Hasta luego. Apagando sistemas.")
        os._exit(0)
    if re.search(r"que hora es|dime la hora", q):
        return f"Son las {datetime.datetime.now():%H:%M}."
    if re.search(r"que dia es|fecha de hoy", q):
        return "Hoy es " + datetime.datetime.now().strftime("%d/%m/%Y") + "."
    if re.search(r"olvida (todo|la conversacion)|borra (la )?memoria", q):
        historial = []; MEMORIA.unlink(missing_ok=True)
        return "Conversación reiniciada."
    m = re.search(r"(?:temporizador|alarma|recuerdame en|avisame en).*?(\d+)\s*(segundo|minuto|hora)", q)
    if m:
        return temporizador(int(m.group(1)), m.group(2))
    m = re.search(r"(?:anota|apunta|nota que|toma nota)\s+(?:que\s+)?(.+)", q)
    if m:
        return nota(m.group(1))
    if re.search(r"(lee|dime) (mis )?notas", q):
        return leer_notas()
    m = re.search(r"clima(?: en| de)?\s*(.*)", q) or re.search(r"como esta el tiempo(?: en)?\s*(.*)", q)
    if m:
        return clima(m.group(1).strip() or CIUDAD)
    if "captura de pantalla" in q:
        return captura()
    if re.search(r"bloquea (la )?(pantalla|computadora)", q) and sys.platform == "win32":
        subprocess.Popen("rundll32.exe user32.dll,LockWorkStation")
        return "Bloqueando la pantalla."
    m = re.search(r"(?:pon|reproduce|ponme)\s+(.+)", q)
    if m:
        webbrowser.open("https://www.youtube.com/results?search_query=" + requests.utils.quote(m.group(1)))
        return f"Buscando {m.group(1)} en YouTube."
    m = re.search(r"(?:busca|buscame|investiga)\s+(?:en google\s+)?(.+)", q)
    if m:
        webbrowser.open("https://www.google.com/search?q=" + requests.utils.quote(m.group(1)))
        return f"Buscando {m.group(1)}."
    m = re.search(r"\b(?:abre|abrir|abreme|ejecuta)\s+(.+)", q)
    if m:
        return abrir(m.group(1))
    return None

# ---------- Escucha permanente ----------
def procesar(texto):
    global ultima
    q = norm(texto)
    print("Oído:", texto)
    despierto = WAKE in q
    if not despierto and time.time() - ultima > VENTANA_CONVERSACION:
        return
    q = q.replace(WAKE, "").strip()
    ultima = time.time()
    if not q:
        hablar("Dime.")
        return
    resp = comando_local(q, texto)
    hablar(resp if resp else preguntar_ia(re.sub(rf"(?i)\b{WAKE}\b[,]?", "", texto).strip()))
    ultima = time.time()

def bucle():
    r = sr.Recognizer()
    r.pause_threshold = 0.8
    r.dynamic_energy_threshold = True
    with sr.Microphone() as mic:
        r.adjust_for_ambient_noise(mic, duration=1.5)
        print("Escuchando. Di:", WAKE)
        hablar("Sistemas en línea.")
        while True:
            if hablando.is_set():
                time.sleep(0.2)
                continue
            try:
                audio = r.listen(mic, timeout=5, phrase_time_limit=15)
                texto = r.recognize_google(audio, language="es-MX")
            except (sr.WaitTimeoutError, sr.UnknownValueError):
                continue
            except sr.RequestError as e:
                print("Error de reconocimiento:", e)
                time.sleep(3)
                continue
            try:
                procesar(texto)
            except Exception as e:
                print("Error:", e)

def iniciar_con_windows():
    """Cuando corre como .exe, se registra para arrancar al encender la PC."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "JARVIS", 0, winreg.REG_SZ, f'"{sys.executable}"')
    except Exception as e:
        print("No pude registrar el inicio automático:", e)

def instancia_unica():
    import socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 48653))
    except OSError:
        os._exit(0)  # ya hay un Jarvis corriendo
    return s

if __name__ == "__main__":
    _candado = instancia_unica()
    iniciar_con_windows()
    pygame.mixer.init()
    bucle()
