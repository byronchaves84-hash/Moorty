# Moorty Voice Android — proyecto para GitHub

Este proyecto es una **base Android nativa** para continuar la adaptación de Moorty Voice. Incluye:
- Interfaz Android y selección de audio MP3/MPEG/WAV/OGG.
- Reproducción de sonidos locales y control de volumen.
- Voz española usando Android TextToSpeech (sin depender de Edge TTS).
- Prioridad de mensajes recientes activada y cola que conserva solo el evento más nuevo pendiente.
- Cliente de YouTube Live Chat mediante YouTube Data API v3 (requiere API key y `liveChatId`).
- El ZIP original de Windows se conserva sin cambios en `legacy/windows_original/`.

## Importante sobre la funcionalidad completa
No sería honesto afirmar que esta compilación ya reproduce todas las funciones del programa Windows. `TikTokLive` y `Edge TTS` son dependencias Python del original y no se ejecutan directamente en Android. La app Android incluye una interfaz/adaptador preparado para integrar TikTok, pero la conexión real de TikTok LIVE requiere implementar y probar un transporte compatible con el servicio no oficial elegido. TikTok puede cambiarlo y no hay garantía de disponibilidad. YouTube también requiere un `liveChatId` activo; esta versión no hace OAuth de propietario ni descubre automáticamente el ID del chat.

## Compilar con GitHub Actions
1. Crea un repositorio GitHub y sube **todo el contenido** de este ZIP.
2. En GitHub abre **Actions** y permite workflows si te lo pide.
3. Ejecuta el workflow `Build Android APK` (o haz push a `main`).
4. Al terminar, abre la ejecución y descarga el artefacto `MoortyVoice-debug-apk`.
5. Instala el APK en tu teléfono Android. Si Android lo solicita, autoriza instalar apps de esa fuente.

También puedes abrir la carpeta con Android Studio y compilar `app`.

## YouTube
En la app, introduce:
- API key de YouTube Data API v3.
- `liveChatId` del chat en vivo (no es lo mismo que el ID del canal).
- Pulsa **Conectar YouTube**. Debe ser un chat activo y accesible por la API.

## Audio y voz
Los botones de selección aceptan MP3, MPEG, WAV y OGG; el soporte de reproducción de MPEG depende del códec disponible en Android. MP3 es lo recomendado. La voz usa las voces instaladas en el dispositivo.

## Alcance
El proyecto incluye la fuente original para no perderla. No reemplaza automáticamente cada función específica del programa Windows; la adaptación completa de TikTok, OAuth de YouTube, alertas completas y equivalencia de todos los eventos requiere desarrollo y pruebas adicionales.
