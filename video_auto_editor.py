import os
from dotenv import load_dotenv
import json
import whisper
import openai
import moviepy.editor as mp
import moviepy.config as mpcfg
from pathlib import Path

# ---------------------------
# CONFIGURATION & ENVIRONMENT
# ---------------------------
dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

# Opción A: Cargar la API key desde el .env
# openai.api_key = os.getenv("OPENAI_API_KEY")

# Opción B: Hardcodear la API key para pruebas (remueve o protege la clave en producción)
openai.api_key = "REDACTED_KEY"

# (Opcional) Especifica la ruta del binario de FFmpeg si no se detecta automáticamente
mpcfg.change_settings({"FFMPEG_BINARY": r"C:\Program Files\ffmpeg-2025-04-14-git-3b2a9410ef-full_build\bin\ffmpeg.exe"})

# ---------------------------
# PASO 1: Transcripción con Whisper
# ---------------------------
def transcribe_audio(video_path, transcription_file="transcription.json"):
    if os.path.exists(transcription_file):
        print(f"Cargando transcripción existente desde '{transcription_file}'...")
        with open(transcription_file, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        print("Realizando transcripción con Whisper...")
        model = whisper.load_model("base")
        result = model.transcribe(video_path)
        with open(transcription_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
        return result

# ---------------------------
# PASO 2: Extracción de Clips por Partes con GPT (con caché)
# ---------------------------
def extract_clips_por_partes(transcript_text, cache_dir="gpt_clips_por_partes", chunk_size=3000, start_chunk=1):
    """
    Procesa la transcripción en partes de tamaño 'chunk_size'.
    'start_chunk' es 1-indexado (p. ej., start_chunk=2 omite el primer chunk).
    """
    os.makedirs(cache_dir, exist_ok=True)
    clips_totales = []
    total = len(transcript_text)
    num_chunk = (total // chunk_size) + (1 if total % chunk_size != 0 else 0)
    print(f"Se procesarán {num_chunk} segmento(s) en total...")
    
    for i in range(start_chunk - 1, num_chunk):
        start_index = i * chunk_size
        chunk = transcript_text[start_index:start_index+chunk_size]
        chunk_index = i + 1
        cache_file = os.path.join(cache_dir, f"gpt_clips_part_{chunk_index}.json")
        
        if os.path.exists(cache_file):
            print(f"Cargando clips de caché para el segmento {chunk_index} desde '{cache_file}'...")
            with open(cache_file, "r", encoding="utf-8") as f:
                clips = json.load(f)
        else:
            prompt = f"""
A continuación tienes la transcripción de un video en el que se mezcla una canción con la narración de "Isaias Cabrera" (yo, programador). En este video, mientras programo, se escucha un DJ set. Analiza la transcripción y regresa una lista de clips interesantes que tengan sentido en este contexto.

Cada clip debe ser un objeto JSON con las siguientes claves EXACTAS:
- "title": un título breve del clip.
- "start": timestamp de inicio en segundos (número).
- "end": timestamp de fin en segundos (número).
- "resumen": un resumen breve del clip.

**Importante:** Cada clip debe tener una duración mínima de 90 segundos (es decir, "end" - "start" debe ser al menos 90).

Devuelve solamente un array de estos objetos JSON. No incluyas comentarios adicionales.
Texto:
{chunk}
"""
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4
            )
            result = response.choices[0].message.content
            try:
                clips = json.loads(result)
                # Normalización de claves en caso de nombres alternativos
                for clip in clips:
                    if "timestamp inicio" in clip and "start" not in clip:
                        clip["start"] = clip.pop("timestamp inicio")
                    if "timestamp fin" in clip and "end" not in clip:
                        clip["end"] = clip.pop("timestamp fin")
                    if "título" in clip and "title" not in clip:
                        clip["title"] = clip.pop("título")
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(clips, f, ensure_ascii=False, indent=4)
            except json.JSONDecodeError:
                print(f"Error al parsear JSON para el segmento {chunk_index}. Resultado:")
                print(result)
                clips = []
        clips_totales.extend(clips)
    return clips_totales

# ---------------------------
# PASO 3: Crear Subclips con MoviePy (mínimo 60 segundos)
# ---------------------------
def create_clips(video_path, clips, min_duration=60, padding=5):
    video = mp.VideoFileClip(video_path)
    os.makedirs("clips", exist_ok=True)
    
    for idx, clip in enumerate(clips):
        if "start" not in clip or "end" not in clip or "title" not in clip:
            print(f"Clip {idx} missing required keys: {clip}")
            continue
        
        start = clip["start"]
        end = clip["end"]
        
        # Primer intento: agregar padding (opcional) y asegurar duración mínima
        new_start = max(0, start - padding)
        new_end = min(video.duration, end + padding)
        duration = new_end - new_start
        if duration < min_duration:
            delta = min_duration - duration
            # Intenta extender hacia adelante
            new_end = min(video.duration, new_end + delta)
            # Si aún no alcanza, extiende hacia atrás (sin pasar de 0)
            if new_end - new_start < min_duration:
                new_start = max(0, new_start - (min_duration - (new_end - new_start)))
        
        print(f"Creando subclip {idx+1} desde {new_start} hasta {new_end} (duración {new_end-new_start} segundos)...")
        subclip = video.subclip(new_start, new_end)
        output_path = f"clips/clip_{idx+1}.mp4"
        subclip.write_videofile(output_path, codec="libx264", audio_codec="aac")

# ---------------------------
# PASO 4: Generar y Guardar Información de Clips con Copy para Redes
# ---------------------------
def generate_social_copy(title, resumen, existing_copies):
    """
    Genera un copy para redes con base en el título y resumen.
    Se asegura de no repetir un copy ya existente agregando variación si es necesario.
    """
    base = f"🎬 {title}"
    if resumen.strip():
        base += f" - {resumen}"
    copy_text = base + " ¡No te lo pierdas!"
    
    # Si ya existe, se le agregan variaciones hasta que sea único
    while copy_text in existing_copies:
        copy_text += " 😊"
    return copy_text

def save_clips_info(clips, output_json="clips_info.json"):
    """
    Genera y guarda un archivo JSON con la información de cada clip:
    id, título y copy para post en redes.
    """
    clips_info = []
    existing_copies = set()
    
    for idx, clip in enumerate(clips, start=1):
        title = clip.get("title", f"Clip {idx}")
        resumen = clip.get("resumen", "").strip()
        copy_text = generate_social_copy(title, resumen, existing_copies)
        existing_copies.add(copy_text)
        
        clip_info = {"id": idx, "title": title, "copy": copy_text}
        clips_info.append(clip_info)
    
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(clips_info, f, ensure_ascii=False, indent=4)
    print(f"Información de clips guardada en: {output_json}")

# ---------------------------
# BLOQUE PRINCIPAL
# ---------------------------
if __name__ == "__main__":
    video_file = "video.mp4"
    
    print("🎧 Transcribiendo...")
    transcription = transcribe_audio(video_file)
    transcript_text = transcription["text"]

    # Puedes ajustar 'start_chunk' para omitir segmentos ya procesados.
    print("📚 Extrayendo clips con GPT por partes...")
    clips_data = extract_clips_por_partes(transcript_text, chunk_size=3000, start_chunk=1)

    print("✂️ Generando subclips (mínimo 60 segundos)...")
    create_clips(video_file, clips_data, min_duration=60, padding=5)
    
    print("💾 Guardando información de clips en JSON...")
    save_clips_info(clips_data, output_json="clips_info.json")

    print("✅ Listo. Revisa la carpeta 'clips' y el archivo 'clips_info.json'")
