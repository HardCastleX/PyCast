# PyCast

Transmisor de audio para **SHOUTcast v2** con interfaz gráfica, escrito en Python.

Captura el audio del sistema (loopback WASAPI) o un micrófono, lo codifica a MP3 en tiempo real y lo envía a un servidor SHOUTcast DNAS v2 usando el **protocolo nativo SHOUTcast 2 (Ultravox 2.1)**.

## ¿Por qué el protocolo nativo?

Los encoders clásicos que usan el protocolo SHOUTcast v1 (contraseña por el puerto +1) no pueden elegir el Stream ID en un DNAS 2.x: el audio termina montado en un stream nuevo (sid 1) y tu enlace de escucha queda "offline" aunque el encoder diga que está transmitiendo. PyCast implementa el handshake Ultravox 2.1 completo (autenticación cifrada con XTEA, negociación de stream y envío de datos encapsulado), por lo que el audio llega al Stream ID correcto en servidores multi-stream.

## Características

- Protocolo SHOUTcast 2 nativo (Ultravox 2.1) con selección de Stream ID
- Captura del audio del sistema (loopback) o micrófono, vía WASAPI
- MP3 a 128 / 192 / 256 / 320 kbps (48 kHz), seleccionable desde la interfaz
- VU meter estéreo en tiempo real
- Presets de servidores (se guardan en `presets.json`, local y fuera del repositorio)
- Cronómetro al aire y contador de datos enviados
- Mensajes de error claros: stream ocupado por el AutoDJ, credenciales inválidas, etc.

## Requisitos

- Windows con Python 3.10 o superior
- Dependencias: `pip install -r requirements.txt`

## Uso

```
py main.py
```

1. Elige el dispositivo de audio (el "Loopback" de tus altavoces transmite lo que suena en tu PC).
2. Rellena host, puerto base del servidor, Stream ID, usuario DJ y contraseña.
3. Selecciona el bitrate y pulsa **Iniciar Broadcast**.

La URL para los oyentes es `http://HOST:PUERTO/stream/STREAMID/`.

> **Nota:** si tu hosting usa AutoDJ, deténlo desde el panel antes de conectar; mientras esté activo el servidor rechaza cualquier fuente en vivo con "stream ocupado".

## Estructura

- `main.py` — interfaz gráfica (customtkinter), captura de audio y encoding MP3
- `uvox.py` — implementación del protocolo Ultravox 2.1: framing de mensajes, cifrado XTEA, handshake de autenticación/configuración y envío de audio

## Licencia

GPL-3.0 — ver [LICENSE](LICENSE).
