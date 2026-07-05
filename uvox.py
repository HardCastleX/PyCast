"""Protocolo de fuente SHOUTcast 2 (Ultravox 2.1) para DNAS v2.

Implementa el handshake completo: peticion de cifra (0x1009), autenticacion
XTEA (0x1001), configuracion del stream y envio de audio MP3 (0x7000).
"""
import socket
import struct

_MASK = 0xFFFFFFFF
_DELTA = 0x9E3779B9


class UvoxError(Exception):
    """Error de protocolo con mensaje apto para mostrar al usuario."""


def _xtea_block(v0, v1, k):
    s = 0
    for _ in range(32):
        v0 = (v0 + ((((v1 << 4) ^ (v1 >> 5)) + v1) ^ (s + k[s & 3]))) & _MASK
        s = (s + _DELTA) & _MASK
        v1 = (v1 + ((((v0 << 4) ^ (v0 >> 5)) + v0) ^ (s + k[(s >> 11) & 3]))) & _MASK
    return v0, v1


def xtea_hex(data: bytes, key: bytes) -> str:
    """Cifra `data` con XTEA (clave de 128 bits, relleno con ceros) y
    devuelve el resultado como hex, tal como exige Ultravox 2.1."""
    key = key[:16].ljust(16, b"\x00")
    k = struct.unpack(">4I", key)
    if len(data) % 8:
        data = data + b"\x00" * (8 - len(data) % 8)
    out = []
    for i in range(0, len(data), 8):
        v0, v1 = struct.unpack(">2I", data[i:i + 8])
        v0, v1 = _xtea_block(v0, v1, k)
        out.append(f"{v0:08x}{v1:08x}")
    return "".join(out)


class UvoxSource:
    """Conexion de fuente (broadcaster) a un SHOUTcast DNAS v2."""

    MSG_AUTH = 0x1001
    MSG_SETUP = 0x1002
    MSG_BUFFER = 0x1003
    MSG_STANDBY = 0x1004
    MSG_TERMINATE = 0x1005
    MSG_MAX_PAYLOAD = 0x1008
    MSG_CIPHER = 0x1009
    MSG_MIME = 0x1040
    MSG_ICY_NAME = 0x1100
    MSG_ICY_GENRE = 0x1101
    MSG_ICY_PUB = 0x1103
    MSG_MP3_DATA = 0x7000

    def __init__(self, host, port, sid, user, password,
                 bitrate=128, name="PyStreamer", genre="Variado"):
        self.host = host
        self.port = port
        self.sid = int(sid)
        self.user = user
        self.password = password
        self.bitrate = bitrate
        self.name = name
        self.genre = genre
        self.sock = None
        self.max_payload = 16377

    def _send(self, msgtype, payload: bytes):
        frame = b"\x5a\x00" + struct.pack(">HH", msgtype, len(payload)) + payload + b"\x00"
        self.sock.sendall(frame)

    def _recv(self):
        hdr = b""
        while len(hdr) < 6:
            c = self.sock.recv(6 - len(hdr))
            if not c:
                raise UvoxError("El servidor cerró la conexión")
            hdr += c
        if hdr[0] != 0x5A:
            raise UvoxError("Respuesta no válida del servidor")
        msgtype = struct.unpack(">H", hdr[2:4])[0]
        ln = struct.unpack(">H", hdr[4:6])[0]
        payload = b""
        while len(payload) < ln + 1:  # +1 por el byte terminador
            c = self.sock.recv(ln + 1 - len(payload))
            if not c:
                raise UvoxError("El servidor cerró la conexión")
            payload += c
        return msgtype, payload[:ln].rstrip(b"\x00")

    def _request(self, msgtype, payload: str, step: str) -> bytes:
        self._send(msgtype, payload.encode("utf-8", "replace") + b"\x00")
        _, resp = self._recv()
        if not resp.startswith(b"ACK"):
            reason = resp.decode("utf-8", "replace")
            raise UvoxError(self._friendly_error(reason, step))
        return resp

    @staticmethod
    def _friendly_error(reason, step):
        if "Stream In Use" in reason:
            return "Stream ocupado: detén el AutoDJ en tu panel"
        if "Deny" in reason:
            return "Usuario, contraseña o Stream ID incorrectos"
        if "Stream ID Error" in reason:
            return "Stream ID inválido"
        return f"{step}: {reason}"

    def connect(self, timeout=8.0):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError as e:
            raise UvoxError(f"No se pudo conectar: {e}") from e
        try:
            resp = self._request(self.MSG_CIPHER, "2.1", "Cifra")
            key = resp.split(b":", 1)[1] if b":" in resp else b""
            uid = xtea_hex(self.user.encode("utf-8", "replace"), key)
            blob = xtea_hex(self.password.encode("utf-8", "replace"), key)
            self._request(self.MSG_AUTH, f"2.1:{self.sid}:{uid}:{blob}", "Autenticación")
            self._request(self.MSG_MIME, "audio/mpeg", "Formato")
            self._request(self.MSG_SETUP, f"{self.bitrate}:{self.bitrate}", "Bitrate")
            self._request(self.MSG_BUFFER, "32:16", "Buffer")
            resp = self._request(self.MSG_MAX_PAYLOAD, "16377:1024", "Tamaño de mensaje")
            try:
                self.max_payload = int(resp.split(b":", 1)[1])
            except (IndexError, ValueError):
                pass
            self._request(self.MSG_ICY_NAME, self.name, "Nombre")
            self._request(self.MSG_ICY_GENRE, self.genre, "Género")
            self._request(self.MSG_ICY_PUB, "0", "Publicación")
            self.sock.settimeout(timeout)
            self._send(self.MSG_STANDBY, b"")
            _, resp = self._recv()
            if not resp.startswith(b"ACK"):
                raise UvoxError(self._friendly_error(resp.decode("utf-8", "replace"), "Standby"))
            self.sock.settimeout(None)
        except UvoxError:
            self.close(terminate=False)
            raise
        except OSError as e:
            self.close(terminate=False)
            raise UvoxError(f"Error de red: {e}") from e

    def send_audio(self, mp3_data: bytes):
        for i in range(0, len(mp3_data), self.max_payload):
            self._send(self.MSG_MP3_DATA, mp3_data[i:i + self.max_payload])

    def close(self, terminate=True):
        if self.sock is None:
            return
        try:
            if terminate:
                self._send(self.MSG_TERMINATE, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.sock = None
