
### 📄 `README.md`

```markdown
# 🎬 Video Clipper + Subtitles Generator with Whisper, GPT and MoviePy

Este proyecto permite procesar un video y generar automáticamente:
- Transcripciones con **Whisper**
- Clips relevantes con ayuda de **GPT-4**
- Archivos `.mp4` recortados por contenido
- Subtítulos sobre el video final
- Copys listos para publicar en redes sociales

---

## ⚙️ Requisitos

- Python 3.10+
- FFmpeg instalado (y su ruta configurada si es necesario)
- `.env` con tu clave de OpenAI:

```env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 📦 Instalación

```bash
# Crea entorno virtual
python -m venv venv
source venv/Scripts/activate  # Windows
# source venv/bin/activate    # Linux/macOS

# Instala dependencias
pip install -r requirements.txt
```

---

## 🧠 ¿Qué hace este script?

1. **Transcribe** el audio del video (`video.mp4`) usando Whisper.
2. Divide la transcripción en fragmentos y usa **GPT-4** para detectar momentos interesantes.
3. Corta automáticamente los clips con MoviePy.
4. Genera un archivo JSON (`clips_info.json`) con títulos y copys listos para publicar.
5. Añade **subtítulos superpuestos** directamente sobre el video final.

---

## 🚀 Uso

Coloca tu video original como `video.mp4` en la raíz del proyecto y corre:

```bash
python video_auto_editor.py
```

El script generará:
- Carpeta `/clips` con clips relevantes
- `clips_info.json` con metadatos
- `video_with_subtitles.mp4` con subtítulos integrados

---

## 📂 Archivos importantes

| Archivo | Descripción |
|--------|-------------|
| `video_auto_editor.py` | Script principal de procesamiento |
| `.env` | Clave de API de OpenAI (no se sube al repo) |
| `clips/` | Clips generados automáticamente |
| `gpt_clips_por_partes/` | Caché por fragmentos de transcripción |
| `clips_info.json` | Títulos y copys para redes sociales |

---

## 🔒 Seguridad

El archivo `.env` está ignorado por `.gitignore`. **Nunca subas tu clave de OpenAI al repositorio**.

---

## ✨ Créditos

- 🧠 Transcripción: [OpenAI Whisper](https://github.com/openai/whisper)
- 🤖 Análisis de texto: [OpenAI GPT-4](https://platform.openai.com)
- 🎬 Edición de video: [MoviePy](https://zulko.github.io/moviepy/)

---

## 🛠️ Roadmap futuro

- Subida automática a YouTube/TikTok
- Exportación de subtítulos como `.srt`
- Soporte multilenguaje
```

---

¿Te gustaría que también te genere un `requirements.txt` listo para usar con todas las dependencias que estás utilizando (`openai`, `moviepy`, `whisper`, etc.)?
