import customtkinter as ctk
import pyaudiowpatch as pyaudio
import numpy as np
import lameenc
import socket
import threading
from uvox import UvoxSource, UvoxError
import base64
import time
import json
import os
import queue
import ctypes
import traceback
import warnings
warnings.filterwarnings("ignore")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BITRATE = 256      # kbps MP3
SAMPLE_RATE = 48000  # Hz

class AudioStreamerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Shoutcast v2 Streamer")
        self.geometry("400x700")
        self.resizable(False, False)

        self.is_connected = False
        self.stream_thread = None
        self.source = None
        self.should_stop = False
        self.live_start = None
        self.bytes_sent = 0
        
        self.pa = pyaudio.PyAudio()
        self.capture_rate = SAMPLE_RATE
        self.capture_channels = 2
        self.audio_task_id = 0
        self.audio_thread = None
        self.audio_queue = queue.Queue(maxsize=100)
        self.encoder = lameenc.Encoder()
        self.encoder.set_bit_rate(BITRATE)
        self.encoder.set_in_sample_rate(SAMPLE_RATE)
        self.encoder.set_channels(2)
        self.encoder.set_quality(2)

        self.presets_file = "presets.json"
        self.presets = self.load_presets()

        self.create_widgets()
        self.change_audio_device(self.audio_device_var.get())

    def create_widgets(self):
        # VU meter: columna derecha a lo alto de toda la ventana
        self.vu_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.vu_frame.pack(side="right", fill="y", padx=(0, 20), pady=20)

        self.vu_label = ctk.CTkLabel(self.vu_frame, text="L    R", font=ctk.CTkFont(size=10, weight="bold"))
        self.vu_label.pack(pady=(0, 5))

        self.vu_bars_frame = ctk.CTkFrame(self.vu_frame, fg_color="transparent")
        self.vu_bars_frame.pack(side="top", fill="y", expand=True)

        self.vu_meter_l = ctk.CTkProgressBar(self.vu_bars_frame, orientation="vertical", width=12)
        self.vu_meter_l.set(0)
        self.vu_meter_l.pack(side="left", padx=(0, 3), fill="y", expand=True)

        self.vu_meter_r = ctk.CTkProgressBar(self.vu_bars_frame, orientation="vertical", width=12)
        self.vu_meter_r.set(0)
        self.vu_meter_r.pack(side="left", padx=(3, 0), fill="y", expand=True)

        # Contenido: columna izquierda
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(side="left", fill="both", expand=True)

        # Title
        self.title_label = ctk.CTkLabel(self.content_frame, text="Shoutcast v2 Streamer", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(pady=(20, 15))

        # Audio Input Device (WASAPI: microfonos y loopbacks de salida)
        wasapi_index = self.pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        self.mic_dict = {}
        for dev in self.pa.get_device_info_generator():
            if dev["hostApi"] == wasapi_index and dev["maxInputChannels"] > 0:
                self.mic_dict[dev["name"]] = dev
        device_list = list(self.mic_dict.keys())

        default_val = device_list[0] if device_list else ""
        try:
            default_val = self.pa.get_default_wasapi_loopback()["name"]
        except Exception:
            pass

        self.audio_device_var = ctk.StringVar(value=default_val)
        self.audio_device_menu = ctk.CTkOptionMenu(self.content_frame, values=device_list, variable=self.audio_device_var, command=self.change_audio_device)
        self.audio_device_menu.pack(pady=(0, 10), padx=(30, 15), fill="x")

        # Presets
        self.preset_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.preset_frame.pack(pady=(0, 10), padx=(30, 15), fill="x")
        
        self.preset_var = ctk.StringVar(value="Cargar Preset...")
        options = ["Cargar Preset..."] + list(self.presets.keys()) + ["Limpiar Datos"]
        self.preset_menu = ctk.CTkOptionMenu(self.preset_frame, values=options, variable=self.preset_var, command=self.apply_preset)
        self.preset_menu.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.save_preset_btn = ctk.CTkButton(self.preset_frame, text="Guardar", width=60, command=self.save_preset)
        self.save_preset_btn.pack(side="left", padx=(0, 5))
        
        self.del_preset_btn = ctk.CTkButton(self.preset_frame, text="Borrar", width=60, fg_color="red", hover_color="darkred", command=self.delete_preset)
        self.del_preset_btn.pack(side="left")

        # Hostname or IP
        self.host_entry = ctk.CTkEntry(self.content_frame, placeholder_text="Hostname or IP")
        self.host_entry.pack(pady=(0, 10), padx=(30, 15), fill="x")

        # Port
        self.port_entry = ctk.CTkEntry(self.content_frame, placeholder_text="Port")
        self.port_entry.pack(pady=(0, 10), padx=(30, 15), fill="x")

        # Stream ID (SID)
        self.sid_entry = ctk.CTkEntry(self.content_frame, placeholder_text="Stream ID (SID)")
        self.sid_entry.pack(pady=(0, 10), padx=(30, 15), fill="x")

        # DJ Username
        self.dj_user_entry = ctk.CTkEntry(self.content_frame, placeholder_text="DJ Username")
        self.dj_user_entry.pack(pady=(0, 10), padx=(30, 15), fill="x")

        # Password
        self.pass_entry = ctk.CTkEntry(self.content_frame, placeholder_text="Password", show="*")
        self.pass_entry.pack(pady=(0, 10), padx=(30, 15), fill="x")

        # Bitrate
        self.bitrate_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.bitrate_frame.pack(pady=(0, 20), padx=(30, 15), fill="x")

        self.bitrate_label = ctk.CTkLabel(self.bitrate_frame, text="Bitrate (kbps):", text_color="gray")
        self.bitrate_label.pack(side="left")

        self.bitrate_var = ctk.StringVar(value=str(BITRATE))
        self.bitrate_menu = ctk.CTkOptionMenu(self.bitrate_frame, width=100, values=["128", "192", "256", "320"], variable=self.bitrate_var)
        self.bitrate_menu.pack(side="right")

        # Controles inferiores
        self.controls_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.controls_frame.pack(side="bottom", pady=(0, 20), padx=(30, 15), fill="x")

        # Status Label
        self.status_label = ctk.CTkLabel(self.controls_frame, text="Desconectado", text_color="gray", font=ctk.CTkFont(size=16))
        self.status_label.pack(pady=(0, 2))

        # Estadisticas en vivo (tiempo al aire y datos enviados)
        self.stats_label = ctk.CTkLabel(self.controls_frame, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.stats_label.pack(pady=(0, 8))

        # Connect/Disconnect Button
        self.connect_btn = ctk.CTkButton(self.controls_frame, text="Iniciar Broadcast", font=ctk.CTkFont(size=16, weight="bold"), height=40, command=self.toggle_connection)
        self.connect_btn.pack(pady=(0, 10), fill="x")

    def change_audio_device(self, choice):
        self.audio_task_id += 1
        current_id = self.audio_task_id
        self.audio_thread = threading.Thread(target=self.audio_capture_task, args=(choice, current_id), daemon=True)
        self.audio_thread.start()

    def handle_disconnect(self):
        if self.is_connected:
            self.stop_stream()
            self.update_status("Conexión perdida", "red")

    def audio_capture_task(self, device_name, task_id):
        dev = self.mic_dict.get(device_name)
        if not dev:
            return

        # WASAPI requiere COM inicializado en este hilo (si no, error -9999)
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0)  # MTA
        except Exception:
            pass

        rate = int(dev["defaultSampleRate"])
        channels = min(2, int(dev["maxInputChannels"]))
        self.capture_rate = rate
        self.capture_channels = channels
        state = {"last_vu": 0.0}

        # Captura event-driven: WASAPI entrega los buffers via callback nativo
        # (como Rocket Broadcaster), sin bucle de polling en Python.
        def callback(in_data, frame_count, time_info, status):
            if self.audio_task_id != task_id:
                return (None, pyaudio.paComplete)

            try:
                data = np.frombuffer(in_data, dtype=np.int16).reshape(-1, channels)

                now = time.time()
                if now - state["last_vu"] >= 0.05:
                    state["last_vu"] = now
                    peak_l = min(1.0, np.max(np.abs(data[:, 0])) / 32767.0 * 1.5)
                    peak_r = min(1.0, np.max(np.abs(data[:, 1])) / 32767.0 * 1.5) if channels > 1 else peak_l
                    self.after(0, self.update_vu, peak_l, peak_r)

                if self.is_connected:
                    pcm_data = data if channels == 2 else np.repeat(data, 2, axis=1)
                    try:
                        self.audio_queue.put_nowait(pcm_data)
                    except queue.Full:
                        pass
            except Exception:
                traceback.print_exc()
            return (None, pyaudio.paContinue)

        try:
            stream = self.pa.open(format=pyaudio.paInt16, channels=channels,
                                  rate=rate, input=True,
                                  input_device_index=dev["index"],
                                  frames_per_buffer=2048,
                                  stream_callback=callback)
            try:
                while self.audio_task_id == task_id and stream.is_active():
                    time.sleep(0.2)
            finally:
                stream.stop_stream()
                stream.close()
        except Exception as e:
            traceback.print_exc()
            if self.audio_task_id == task_id:
                self.after(0, self.update_status, f"Error de captura: {e}", "red")
        finally:
            if self.audio_task_id == task_id:
                self.after(0, self.update_vu, 0, 0)

    def update_vu(self, l, r):
        self.vu_meter_l.set(l)
        self.vu_meter_r.set(r)

    def load_presets(self):
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_presets_to_file(self):
        try:
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(self.presets, f)
        except:
            pass

    def update_preset_menu(self):
        options = ["Cargar Preset..."] + list(self.presets.keys()) + ["Limpiar Datos"]
        self.preset_menu.configure(values=options)

    def save_preset(self):
        dialog = ctk.CTkInputDialog(text="Nombre para este preset:", title="Guardar Preset")
        name = dialog.get_input()
        if name and name.strip():
            name = name.strip()
            self.presets[name] = {
                "host": self.host_entry.get().strip(),
                "port": self.port_entry.get().strip(),
                "sid": self.sid_entry.get().strip(),
                "user": self.dj_user_entry.get().strip(),
                "pass": self.pass_entry.get().strip(),
                "bitrate": self.bitrate_var.get(),
            }
            self.save_presets_to_file()
            self.update_preset_menu()
            self.preset_var.set(name)

    def delete_preset(self):
        name = self.preset_var.get()
        if name in self.presets:
            del self.presets[name]
            self.save_presets_to_file()
            self.update_preset_menu()
            self.preset_var.set("Cargar Preset...")

    def apply_preset(self, choice):
        if choice in self.presets:
            p = self.presets[choice]
            self.host_entry.delete(0, 'end'); self.host_entry.insert(0, p.get("host", ""))
            self.port_entry.delete(0, 'end'); self.port_entry.insert(0, p.get("port", ""))
            self.sid_entry.delete(0, 'end'); self.sid_entry.insert(0, p.get("sid", ""))
            self.dj_user_entry.delete(0, 'end'); self.dj_user_entry.insert(0, p.get("user", ""))
            self.pass_entry.delete(0, 'end'); self.pass_entry.insert(0, p.get("pass", ""))
            self.bitrate_var.set(p.get("bitrate", str(BITRATE)))
        elif choice == "Limpiar Datos":
            self.host_entry.delete(0, 'end')
            self.port_entry.delete(0, 'end')
            self.sid_entry.delete(0, 'end')
            self.dj_user_entry.delete(0, 'end')
            self.pass_entry.delete(0, 'end')
        
        if choice != "Cargar Preset...":
            self.preset_var.set(choice)

    def toggle_connection(self):
        if self.is_connected:
            self.stop_stream()
        else:
            self.start_stream()

    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def update_stats(self):
        if not self.is_connected or self.live_start is None:
            self.stats_label.configure(text="")
            return
        elapsed = int(time.time() - self.live_start)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        mb = self.bytes_sent / (1024 * 1024)
        self.stats_label.configure(text=f"Al aire {h:02d}:{m:02d}:{s:02d}  ·  {mb:.1f} MB enviados")
        self.after(1000, self.update_stats)

    def set_btn(self, text):
        self.connect_btn.configure(text=text)

    def reset_btn(self):
        self.is_connected = False
        self.set_btn("Iniciar Broadcast")
        self.bitrate_menu.configure(state="normal")
        if self.status_label.cget("text") == "En Vivo" or self.status_label.cget("text") == "Conectando...":
            self.update_status("Desconectado", "gray")
        self.update_vu(0, 0)

    def stop_stream(self):
        self.should_stop = True
        self.update_status("Desconectado", "gray")
        self.set_btn("Iniciar Broadcast")
        self.is_connected = False
        if self.source:
            self.source.close()

    def start_stream(self):
        self.update_status("Conectando...", "orange")
        self.should_stop = False
        self.stream_thread = threading.Thread(target=self.stream_task, daemon=True)
        self.stream_thread.start()

    def stream_task(self):
        try:
            hostname = self.host_entry.get().strip()
            port = int(self.port_entry.get().strip())
            sid = self.sid_entry.get().strip()
            dj_user = self.dj_user_entry.get().strip()
            dj_pass = self.pass_entry.get().strip()

            if not hostname or not port or not sid or not dj_pass:
                self.after(0, self.update_status, "Error: Faltan campos", "red")
                self.after(0, self.reset_btn)
                return

            bitrate = int(self.bitrate_var.get())
            self.after(0, lambda: self.bitrate_menu.configure(state="disabled"))

            # Protocolo SHOUTcast 2 (Ultravox 2.1): se conecta al puerto base
            # y permite elegir el Stream ID real del servidor.
            self.source = UvoxSource(hostname, port, sid, dj_user, dj_pass,
                                     bitrate=bitrate, name="PyStreamer")
            try:
                self.source.connect()
            except UvoxError as e:
                self.after(0, self.update_status, f"Error: {e}", "red")
                self.after(0, self.reset_btn)
                return

            self.after(0, self.update_status, f"En Vivo (MP3 @ {bitrate} kbps)", "green")
            self.after(0, self.set_btn, "Detener Broadcast")
            # Restaurar el encoder (para evitar el error "not currently encoding" tras un stop)
            self.encoder = lameenc.Encoder()
            self.encoder.set_bit_rate(bitrate)
            self.encoder.set_in_sample_rate(self.capture_rate)
            self.encoder.set_channels(2)
            self.encoder.set_quality(2)
            
            self.is_connected = True
            self.live_start = time.time()
            self.bytes_sent = 0
            self.after(0, self.update_stats)

            while not self.audio_queue.empty():
                try: self.audio_queue.get_nowait()
                except: pass

            # 0.5s de silencio (solo si la captura se detiene por completo)
            silent_pcm = np.zeros((self.capture_rate // 2, 2), dtype=np.int16)

            while not self.should_stop and self.is_connected:
                try:
                    pcm_data = self.audio_queue.get(timeout=0.5)
                except queue.Empty:
                    pcm_data = silent_pcm
                    
                if self.should_stop:
                    break
                mp3_data = self.encoder.encode(pcm_data.tobytes())
                if mp3_data:
                    try:
                        self.source.send_audio(bytes(mp3_data))
                        self.bytes_sent += len(mp3_data)
                    except (socket.error, UvoxError, AttributeError):
                        # AttributeError: el socket ya fue cerrado por stop_stream
                        if not self.should_stop:
                            self.after(0, self.handle_disconnect)
                        break

            # Flush final data
            if self.source and self.source.sock:
                try:
                    mp3_data = self.encoder.flush()
                    if mp3_data:
                        self.source.send_audio(bytes(mp3_data))
                except (socket.error, UvoxError):
                    pass

        except Exception as e:
            self.after(0, self.update_status, f"Error: {str(e)}", "red")
        finally:
            if self.source:
                self.source.close()
            self.after(0, self.reset_btn)

if __name__ == "__main__":
    app = AudioStreamerApp()
    app.mainloop()
