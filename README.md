# hostdomi-reels-mixer

Servicio privado para convertir una imagen estática y una locución MP3 en un
reel MP4 vertical. No publica contenido.

## `POST /compose-approved`

Genera el vídeo a partir de un arte ya aprobado. Añade únicamente el logo oficial
configurado por `HOSTDOMI_LOGO_PATH`, con la misma área máxima de 650×150,
posición y fondo protector que usa `/compose`; no dibuja ni altera texto, CTA u
otros elementos gráficos. Recibe `multipart/form-data`:

- `image`: PNG final de cualquier tamaño (máximo 32 MB). El servicio lo
  encuadra al lienzo vertical 1080×1920 con el mismo método que `/compose`.
- `audio`: MP3 de 12 a 25 segundos (máximo 20 MB).
- Cabecera `X-Mixer-Key`: el mismo valor configurado en `MIXER_API_KEY`.

Devuelve `video/mp4` con vídeo H.264, audio AAC, 1080×1920, 30 fps y duración
igual a la locución. Si el PNG no tiene proporción 9:16, el servicio usa un
encuadre centrado para llenar 1080×1920; el logo es la única superposición
aplicada.

Ejemplo:

```bash
curl -X POST http://localhost:8080/compose-approved \
  -H "X-Mixer-Key: $MIXER_API_KEY" \
  -F "image=@final.png;type=image/png" \
  -F "audio=@voice.mp3;type=audio/mpeg" \
  --output reel.mp4
```

## Dokploy

El `Dockerfile` ya instala FFmpeg y las dependencias necesarias. Antes de
desplegar, falta crear el secreto `MIXER_API_KEY` en Dokploy con un valor largo
y único, seleccionar este directorio como fuente de la aplicación y confirmar
que existe la red externa `dokploy-network`. Mantén el puerto 8080 sin publicar:
el worker está pensado para ser llamado sólo desde n8n u otros servicios de la
misma red.
