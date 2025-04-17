import os
import re
import json
from pathlib import Path
from dotenv import load_dotenv
import whisper
import openai
from moviepy.config import change_settings
from moviepy.editor import (
    VideoFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips
)

# ---------------------------
# Configuración de rutas FFmpeg / ImageMagick
# ---------------------------
change_settings({
    "FFMPEG_BINARY": r"C:\Program Files\ffmpeg-2025-04-14-git-3b2a9410ef-full_build\bin\ffmpeg.exe",
    "IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe"
})

# ---------------------------
# Carga de variables de entorno
# ---------------------------
dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=dotenv_path)
openai.api_key = os.getenv("OPENAI_API_KEY")

# ---------------------------
# PASO 1: Transcripción con Whisper
# ---------------------------
def transcribe_audio(video_path, transcription_file="transcription.json"):
    if os.path.exists(transcription_file):
        print(f"Cargando transcripción existente desde '{transcription_file}'…")
        return json.load(open(transcription_file, "r", encoding="utf-8"))
    print("Realizando transcripción con Whisper…")
    model = whisper.load_model("base")
    result = model.transcribe(video_path)
    with open(transcription_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    return result

# ---------------------------
# PASO 2: Extracción de clips por chunk con GPT
# ---------------------------
def extract_clips_por_partes(transcript_text, cache_dir="gpt_clips_por_partes", chunk_size=3000):
    os.makedirs(cache_dir, exist_ok=True)
    clips_totales = []
    total = len(transcript_text)
    num_chunk = (total // chunk_size) + (1 if total % chunk_size else 0)

    for i in range(num_chunk):
        idx = i + 1
        cache_file = os.path.join(cache_dir, f"clip_chunk_{idx}.json")
        if os.path.exists(cache_file):
            clips_totales.append(json.load(open(cache_file, "r", encoding="utf-8")))
            continue

        chunk = transcript_text[i*chunk_size:(i+1)*chunk_size]
        prompt = f"""
Tienes la transcripción de un video. Divídela en chunks de {chunk_size} caracteres y para cada chunk regresa UNA LISTA JSON de tamaño 1 con:
- \"title\": título descriptivo,
- \"start\": segundo de inicio,
- \"end\": segundo de fin,
- \"resumen\": breve descripción.
Cada clip debe durar al menos 180 segundos (3 min) y como máximo 300 segundos (5 min).

Chunk #{idx}:
{chunk}
"""
        resp = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4
        )
        clip = json.loads(resp.choices[0].message.content)[0]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(clip, f, ensure_ascii=False, indent=4)
        clips_totales.append(clip)

    return clips_totales

# ---------------------------
# PASO 3: Crear subclips limpios + subtítulos verticales
# ---------------------------
def create_clean_clips(video_path, clips, transcription,
                       min_duration=180, max_duration=300,
                       padding=60, silence_thresh=0.5):
    video    = VideoFileClip(video_path)
    segments = transcription.get("segments", [])

    # Estilo de subtítulos para vertical
    screen_w, screen_h     = video.size
    subtitle_fontsize      = 60
    subtitle_margin_bottom = 50
    subtitle_text_width    = int(screen_w * 0.9)

    # Regex muletillas
    filler_words   = ["eh", "um", "ah", "bueno", "o sea", "pues", "este"]
    filler_pattern = re.compile(r"\b(" + "|".join(filler_words) + r")\b", re.IGNORECASE)

    os.makedirs("clips_clean", exist_ok=True)

    for idx, clip in enumerate(clips, start=1):
        title      = clip.get("title", f"chunk_{idx}")
        start, end = clip["start"], clip["end"]
        new_start  = max(0, start - padding)
        new_end    = min(video.duration, end + padding)

        # Filtrar segmentos dentro del rango
        segs = [s for s in segments if new_start <= s["start"] < s["end"] <= new_end]

        # Detectar muletillas y silencios
        removal = []
        for s in segs:
            if filler_pattern.search(s["text"]):
                removal.append((s["start"], s["end"]))
        times = sorted(segs, key=lambda s: s["start"])
        if times and (times[0]["start"] - new_start) > silence_thresh:
            removal.append((new_start, times[0]["start"]))
        for a, b in zip(times, times[1:]):
            if b["start"] - a["end"] > silence_thresh:
                removal.append((a["end"], b["start"]))
        if times and new_end - times[-1]["end"] > silence_thresh:
            removal.append((times[-1]["end"], new_end))

        # Unir intervalos solapados
        removal.sort(key=lambda x: x[0])
        merged = []
        for rs, re_end in removal:
            if not merged or rs > merged[-1][1]:
                merged.append([rs, re_end])
            else:
                merged[-1][1] = max(merged[-1][1], re_end)

        # Calcular tramos a mantener
        keeps, cursor = [], new_start
        for rs, re_end in merged:
            if cursor < rs:
                keeps.append((cursor, rs))
            cursor = re_end
        if cursor < new_end:
            keeps.append((cursor, new_end))

        # Forzar duraciones
        total_keep = sum(e - s for s, e in keeps)
        if total_keep < min_duration:
            keeps = [(new_start, new_start + min_duration)]
        elif total_keep > max_duration:
            adjusted, acc = [], 0
            for s, e in keeps:
                dur = e - s
                if acc + dur <= max_duration:
                    adjusted.append((s, e))
                    acc += dur
                else:
                    adjusted.append((s, s + (max_duration - acc)))
                    break
            keeps = adjusted

        # Concatenar subclips
        subclips   = [video.subclip(s, e) for s, e in keeps]
        chunk_clip = concatenate_videoclips(subclips, method="compose")

        # Subtítulos ajustados
        durations = [e - s for s, e in keeps]
        offsets   = [0]
        for d in durations[:-1]:
            offsets.append(offsets[-1] + d)

        subtitle_clips = []
        for s in segs:
            if filler_pattern.search(s["text"]):
                continue
            for (ks, ke), off in zip(keeps, offsets):
                if ks <= s["start"] < ke:
                    rel_t = (s["start"] - ks) + off
                    txt = (TextClip(
                                s["text"].strip(),
                                font="Arial",
                                fontsize=subtitle_fontsize,
                                color="white",
                                bg_color="black",
                                size=(subtitle_text_width, None),
                                method="caption"
                            )
                            .margin(bottom=subtitle_margin_bottom, opacity=0)
                            .set_position(("center", "bottom"))
                            .set_start(rel_t)
                            .set_duration(s["end"] - s["start"]))
                    subtitle_clips.append(txt)
                    break

        final_clip = CompositeVideoClip([chunk_clip, *subtitle_clips])
        safe_title = "".join(
            c if c.isalnum() or c in (" ", "_", "-") else "_"
            for c in title
        ).strip().replace(" ", "_")
        out_path = f"clips_clean/{safe_title}.mp4"
        final_clip.write_videofile(out_path, codec="libx264", audio_codec="aac")

# ---------------------------
# PASO 4: Guardar info para redes e índice
# ---------------------------
def save_clips_info(clips, output_json="clips_info.json"):
    info, seen = [], set()
    for i, c in enumerate(clips, start=1):
        base = f"🎬 {c['title']} - {c.get('resumen','')}"
        copy = (base + " ¡No te lo pierdas!").strip()
        while copy in seen:
            copy += " 😊"
        seen.add(copy)
        info.append({"id": i, "title": c['title'], "copy": copy})
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=4)


def save_index_txt(clips, filename="clips_index.txt"):
    lines = []
    for i, c in enumerate(clips, start=1):
        m, s = divmod(int(c["start"]), 60)
        lines.append(f"{i}. [{m:02d}:{s:02d}] - {c['title']}")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ---------------------------
# PASO 5: Generar resumen final de subclips
# ---------------------------
def generate_final_summary(clips_info_file="clips_info.json", clips_dir="clips_clean"):
    # Cargar info de clips
    clips_info = json.load(open(clips_info_file, "r", encoding="utf-8"))
    entries = [f"{c['id']}. {c['title']} - {c['copy']}" for c in clips_info]
    prompt = (
        "Estos son los clips generados:\n" + "\n".join(entries) +
        "\n\nDevuélveme **solo** un array JSON de nombres de archivos (sin ruta) de los clips "
        "que mejor resuman el video, en orden lógico, eligiendo entre 5 y 10 clips."
    )
    resp = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role":"user","content":prompt}],
        temperature=0.3
    )
    content = resp.choices[0].message.content
    m = re.search(r"\[.*\]", content, re.DOTALL)
    if m:
        try:
            names = json.loads(m.group(0))
        except json.JSONDecodeError:
            names = sorted(os.listdir(clips_dir))[:5]
    else:
        names = sorted(os.listdir(clips_dir))[:5]

    # Concatenar
    subclips = []
    for name in names:
        path = os.path.join(clips_dir, name)
        subclips.append(VideoFileClip(path))
    final = concatenate_videoclips(subclips, method="compose")
    os.makedirs("output", exist_ok=True)
    final.write_videofile("output/final_summary.mp4", codec="libx264", audio_codec="aac")
    print("✅ Final summary generado en output/final_summary.mp4")

# ---------------------------
# BLOQUE PRINCIPAL
# ---------------------------
if __name__ == "__main__":
    video_file     = "video.mp4"
    transcription  = transcribe_audio(video_file)
    transcript_text= transcription.get("text", "")

    print("Extrayendo clips por chunk…")
    clips_data     = extract_clips_por_partes(transcript_text)

    print("Creando videos limpios por chunk…")
    create_clean_clips(video_file, clips_data, transcription)

    print("Guardando info para redes…")
    save_clips_info(clips_data)

    print("Guardando índice para YouTube…")
    save_index_txt(clips_data)

    print("✅ Proceso completado de subclips.")
    print("Generando resumen final de subclips…")
    generate_final_summary()
    print("✅ Proceso completo.")
