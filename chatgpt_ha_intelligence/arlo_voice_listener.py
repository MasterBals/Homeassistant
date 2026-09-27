from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import time
import unicodedata
import wave
from array import array
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
_LOGGER = logging.getLogger("arlo-voice-listener")

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API = "http://supervisor/core/api"
HA_WS = "ws://supervisor/core/websocket"
STT_ENGINE = os.environ.get("ARLO_VOICE_STT_ENGINE", "stt.home_assistant_cloud")
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_BYTES = SAMPLE_RATE * 2 * FRAME_MS // 1000
PRE_ROLL_FRAMES = 30
START_FRAMES = 3
END_SILENCE_FRAMES = 45
MAX_SPEECH_FRAMES = 600
MIN_SPEECH_FRAMES = 30

CAMERAS = {
    "camera.aarlo_schlafzimmer": {"source": "arlo_schlafzimmer", "label": "Schlafzimmer"},
    "camera.aarlo_rileys_zimmer": {"source": "arlo_rileys_zimmer", "label": "Rileys Zimmer"},
    "camera.aarlo_kianos_zimmer": {"source": "arlo_kianos_zimmer", "label": "Kianos Zimmer"},
}
WAKE_WORDS = {
    "jarvis", "jarwis", "jervis", "jarves", "javis", "charvis",
    "djarvis", "jarvi", "jarvice", "jarwisch", "jarwitz",
    "service", "servis", "schervis", "dschervis", "tscharvis",
}

@dataclass
class CommandDecision:
    command: str | None
    wake_only: bool = False

def normalize(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").lower())
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = "".join(ch if (ch.isalnum() or ch in " äöüß") else " " for ch in value)
    return " ".join(value.split())

def distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def parse_wake(text: str) -> CommandDecision:
    words = normalize(text).split()
    for idx, word in enumerate(words):
        if word in WAKE_WORDS or (4 <= len(word) <= 8 and distance(word, "jarvis") <= 2):
            command = " ".join(words[idx + 1:]).strip()
            return CommandDecision(command=command or None, wake_only=not bool(command))
    return CommandDecision(command=None, wake_only=False)

def frame_rms(frame: bytes) -> float:
    if len(frame) < 2:
        return 0.0
    samples = array("h")
    samples.frombytes(frame)
    if not samples:
        return 0.0
    total = sum(int(v) * int(v) for v in samples)
    return (total / len(samples)) ** 0.5

def wav_bytes(raw_pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(raw_pcm)
    return buf.getvalue()

class HAWebSocket:
    def __init__(self, token: str):
        self.token = token
        self.ws = None
        self.receiver_task: asyncio.Task | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.next_id = 20

    async def connect(self) -> None:
        self.ws = await websockets.connect(
            HA_WS, ping_interval=20, ping_timeout=20, close_timeout=5,
            max_size=16 * 1024 * 1024,
        )
        hello = json.loads(await self.ws.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"Unexpected websocket greeting: {hello}")
        await self.ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        auth = json.loads(await self.ws.recv())
        if auth.get("type") != "auth_ok":
            raise RuntimeError(f"Home Assistant websocket authentication failed: {auth}")
        self.receiver_task = asyncio.create_task(self._receiver())

    async def _receiver(self) -> None:
        assert self.ws is not None
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                msg_id = msg.get("id")
                if msg_id in self.pending and msg.get("type") in {"result", "pong"}:
                    fut = self.pending.pop(msg_id)
                    if not fut.done():
                        fut.set_result(msg)
        finally:
            err = ConnectionError("Home Assistant websocket closed")
            for fut in list(self.pending.values()):
                if not fut.done():
                    fut.set_exception(err)
            self.pending.clear()

    async def rpc(self, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        if self.ws is None:
            raise ConnectionError("Websocket is not connected")
        msg_id = self.next_id
        self.next_id += 1
        body = dict(payload)
        body["id"] = msg_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[msg_id] = fut
        await self.ws.send(json.dumps(body))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self.pending.pop(msg_id, None)

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()

class ArloVoiceListener:
    def __init__(self, token: str):
        self.token = token
        self.ws: HAWebSocket | None = None
        self.http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(45.0, connect=10.0),
            follow_redirects=True,
        )
        self.armed_until: dict[str, float] = {}
        self.last_command = ""
        self.last_command_at = 0.0
        self.stt_locks = {camera: asyncio.Lock() for camera in CAMERAS}

    async def close(self) -> None:
        await self.http.aclose()

    async def set_helper(self, entity_id: str, value: str) -> None:
        try:
            await self.http.post(
                f"{HA_API}/services/input_text/set_value",
                json={"entity_id": entity_id, "value": str(value)[:255]},
            )
        except Exception as err:
            _LOGGER.debug("Unable to update %s: %s", entity_id, err)

    async def status(self, value: str) -> None:
        _LOGGER.info(value)
        await self.set_helper("input_text.assist_arlo_status", value)

    async def camera_status(self, cfg: dict[str, str], value: str) -> None:
        mapping = {
            "arlo_schlafzimmer": "input_text.assist_arlo_status_schlafzimmer",
            "arlo_rileys_zimmer": "input_text.assist_arlo_status_riley",
            "arlo_kianos_zimmer": "input_text.assist_arlo_status_kiano",
        }
        entity_id = mapping.get(cfg["source"])
        _LOGGER.info("%s: %s", cfg["label"], value)
        if entity_id:
            await self.set_helper(entity_id, value)

    async def reset_camera_stream(self, camera: str) -> None:
        try:
            await self.http.post(
                f"{HA_API}/services/aarlo/camera_stop_activity",
                json={"entity_id": camera},
            )
            await asyncio.sleep(1.0)
        except Exception as err:
            _LOGGER.debug("Unable to reset %s before stream: %s", camera, err)

    async def stream_url(self, camera: str) -> str:
        if self.ws is None:
            raise RuntimeError("Home Assistant websocket unavailable")

        await self.reset_camera_stream(camera)
        errors = []

        try:
            result = await self.ws.rpc(
                {"type": "camera/stream", "entity_id": camera, "format": "hls"},
                timeout=40,
            )
            if result.get("success"):
                url = (result.get("result") or {}).get("url")
                if url:
                    value = str(url)
                    if value.startswith("/"):
                        value = "http://supervisor/core" + value
                    return value
            errors.append("camera/stream: " + str(result))
        except Exception as err:
            errors.append(f"camera/stream {type(err).__name__}: {err}")

        for agent in ("linux", "arlo"):
            try:
                result = await self.ws.rpc(
                    {"type": "aarlo_stream_url", "entity_id": camera, "user_agent": agent},
                    timeout=30,
                )
                if result.get("success"):
                    url = (result.get("result") or {}).get("url")
                    if url:
                        return str(url)
                errors.append(f"aarlo/{agent}: {result}")
            except Exception as err:
                errors.append(f"aarlo/{agent} {type(err).__name__}: {err}")

        raise RuntimeError("; ".join(errors)[-900:])

    async def transcribe(self, raw_pcm: bytes) -> str | None:
        response = await self.http.post(
            f"{HA_API}/stt/{STT_ENGINE}",
            headers={
                "X-Speech-Content": (
                    "language=de-DE; format=wav; codec=pcm; bit_rate=16; "
                    "sample_rate=16000; channel=1"
                ),
                "Content-Type": "audio/wav",
            },
            content=wav_bytes(raw_pcm),
        )
        if response.status_code != 200:
            raise RuntimeError(f"STT HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        if data.get("result") != "success":
            return None
        text = str(data.get("text") or "").strip()
        return text or None

    async def execute_text(self, camera: str, cfg: dict[str, str], text: str) -> None:
        label, source = cfg["label"], cfg["source"]
        await self.set_helper("input_text.assist_arlo_letzte_erkennung", f"{label}: {text}")
        decision = parse_wake(text)
        now = time.monotonic()
        command = decision.command
        if decision.wake_only:
            self.armed_until[source] = now + 15.0
            await self.status(f"Arlo {label}: Jarvis erkannt, warte 15 s auf Befehl")
            return
        if command is None and self.armed_until.get(source, 0.0) > now:
            command = normalize(text)
        if not command:
            return
        normalized = normalize(command)
        if normalized == self.last_command and now - self.last_command_at < 10.0:
            return
        self.last_command, self.last_command_at = normalized, now
        self.armed_until[source] = 0.0
        await self.status(f"Arlo {label}: Befehl -> {command}")
        response = await self.http.post(
            f"{HA_API}/services/script/jarvis_sprachbefehl",
            json={"befehl": command, "quelle": source, "antwort_ausgeben": True},
        )
        response.raise_for_status()

    async def process_segment(self, camera: str, cfg: dict[str, str], raw_pcm: bytes) -> None:
        lock = self.stt_locks[camera]
        if lock.locked():
            return
        async with lock:
            try:
                text = await self.transcribe(raw_pcm)
                if text:
                    await self.execute_text(camera, cfg, text)
            except Exception as err:
                _LOGGER.warning("STT failed for %s: %s", cfg["label"], err)

    async def camera_loop(self, camera: str, cfg: dict[str, str]) -> None:
        label = cfg["label"]
        while True:
            proc = None
            try:
                await self.camera_status(cfg, "Verbinde Dauerstream")
                url = await self.stream_url(camera)
                await self.camera_status(cfg, "HA-Stream-URL erhalten")
                cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
                if url.startswith("http://supervisor/core/"):
                    cmd += ["-headers", f"Authorization: Bearer {self.token}\\r\\n"]
                if url.lower().startswith(("rtsp://", "rtsps://")):
                    cmd += ["-rtsp_transport", "tcp"]
                cmd += [
                    "-i", url, "-map", "0:a:0?", "-vn",
                    "-ac", "1", "-ar", str(SAMPLE_RATE),
                    "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1",
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                assert proc.stdout is not None
                pre = deque(maxlen=PRE_ROLL_FRAMES)
                noise = 180.0
                hot = 0
                speaking = False
                speech: list[bytes] = []
                silence = 0
                connected_announced = False
                first_frame = True
                while True:
                    if first_frame:
                        try:
                            frame = await asyncio.wait_for(proc.stdout.readexactly(FRAME_BYTES), timeout=45.0)
                        except TimeoutError as err:
                            stderr_text = ""
                            if proc.returncode is None:
                                proc.kill()
                            try:
                                _out, _err = await asyncio.wait_for(proc.communicate(), timeout=3.0)
                                stderr_text = _err.decode(errors="ignore").strip().replace("\n", " ")[-500:]
                            except Exception:
                                pass
                            detail = f" / ffmpeg: {stderr_text}" if stderr_text else ""
                            raise RuntimeError(f"Kein Audioframe innerhalb 45 s{detail}") from err
                        first_frame = False
                    else:
                        frame = await proc.stdout.readexactly(FRAME_BYTES)
                    rms = frame_rms(frame)
                    if not speaking:
                        noise = noise * 0.985 + min(rms, max(noise * 3, 1200)) * 0.015
                    threshold = max(380.0, noise * 2.6)
                    active = rms >= threshold
                    pre.append(frame)
                    if not connected_announced:
                        connected_announced = True
                        await self.camera_status(cfg, "Hört dauerhaft")
                    if not speaking:
                        hot = hot + 1 if active else max(0, hot - 1)
                        if hot >= START_FRAMES:
                            speaking = True
                            speech = list(pre)
                            silence = 0
                    else:
                        speech.append(frame)
                        if active:
                            silence = 0
                        else:
                            silence += 1
                        if silence >= END_SILENCE_FRAMES or len(speech) >= MAX_SPEECH_FRAMES:
                            frames = speech[:-silence] if silence and len(speech) > silence else speech
                            if len(frames) >= MIN_SPEECH_FRAMES:
                                asyncio.create_task(self.process_segment(camera, cfg, b"".join(frames)))
                            speaking = False
                            speech = []
                            hot = 0
                            silence = 0
                            pre.clear()
            except asyncio.IncompleteReadError:
                _LOGGER.warning("Arlo audio stream ended for %s", label)
            except asyncio.CancelledError:
                if proc and proc.returncode is None:
                    proc.kill()
                raise
            except Exception as err:
                _LOGGER.warning("Arlo continuous audio failed for %s: %s", label, err)
                await self.camera_status(cfg, f"Streamfehler: {type(err).__name__}: {str(err)[:140]}")
            finally:
                if proc and proc.returncode is None:
                    proc.kill()
                    try:
                        await proc.wait()
                    except Exception:
                        pass
            await asyncio.sleep(3)

    async def run_once(self) -> None:
        self.ws = HAWebSocket(self.token)
        await self.ws.connect()
        await self.status("Arlo Voice: starte 3 dauerhafte Mikrofonstreams")
        tasks = [
            asyncio.create_task(self.camera_loop(camera, cfg))
            for camera, cfg in CAMERAS.items()
        ]
        assert self.ws.receiver_task is not None
        tasks.append(self.ws.receiver_task)
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            exc = task.exception()
            if exc:
                raise exc

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.exception("Arlo voice loop failed")
                await self.status(f"Arlo Voice: Verbindung unterbrochen ({type(err).__name__})")
                await asyncio.sleep(5)
            finally:
                if self.ws is not None:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                self.ws = None

async def main() -> None:
    if not TOKEN:
        raise SystemExit("SUPERVISOR_TOKEN missing")
    listener = ArloVoiceListener(TOKEN)
    try:
        await listener.run()
    finally:
        await listener.close()

if __name__ == "__main__":
    asyncio.run(main())
