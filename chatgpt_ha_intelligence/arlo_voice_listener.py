from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import unicodedata
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
CAPTURE_SECONDS = float(os.environ.get("ARLO_VOICE_CAPTURE_SECONDS", "8"))
RECORDING_FALLBACK = os.environ.get("ARLO_VOICE_RECORDING_FALLBACK", "true").lower() == "true"
STT_ENGINE = os.environ.get("ARLO_VOICE_STT_ENGINE", "stt.home_assistant_cloud")

CAMERAS = {
    "binary_sensor.aarlo_sound_schlafzimmer": {
        "camera": "camera.aarlo_schlafzimmer",
        "source": "arlo_schlafzimmer",
        "label": "Schlafzimmer",
    },
    "binary_sensor.aarlo_sound_rileys_zimmer": {
        "camera": "camera.aarlo_rileys_zimmer",
        "source": "arlo_rileys_zimmer",
        "label": "Rileys Zimmer",
    },
    "binary_sensor.aarlo_sound_kianos_zimmer": {
        "camera": "camera.aarlo_kianos_zimmer",
        "source": "arlo_kianos_zimmer",
        "label": "Kianos Zimmer",
    },
}

WAKE_WORDS = {
    "jarvis", "jarwis", "jervis", "jarves", "javis", "charvis",
    "djarvis", "jarvi", "jarvice", "jarwisch", "jarwitz",
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


class HAWebSocket:
    def __init__(self, token: str, on_event):
        self.token = token
        self.on_event = on_event
        self.ws = None
        self.receiver_task: asyncio.Task | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.next_id = 10

    async def connect(self) -> None:
        self.ws = await websockets.connect(
            HA_WS,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
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
        result = await self.rpc({"type": "subscribe_events", "event_type": "state_changed"})
        if not result.get("success"):
            raise RuntimeError(f"state_changed subscription failed: {result}")

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
                    continue
                if msg.get("type") == "event":
                    try:
                        self.on_event(msg.get("event") or {})
                    except Exception:
                        _LOGGER.exception("Event handler failed")
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
            timeout=httpx.Timeout(40.0, connect=10.0),
            follow_redirects=True,
        )
        self.locks = {cfg["camera"]: asyncio.Lock() for cfg in CAMERAS.values()}
        self.last_trigger: dict[str, float] = {}
        self.armed_until: dict[str, float] = {}
        self.last_command = ""
        self.last_command_at = 0.0

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

    async def get_state(self, entity_id: str) -> dict[str, Any] | None:
        try:
            response = await self.http.get(f"{HA_API}/states/{entity_id}")
            if response.status_code != 200:
                return None
            return response.json()
        except Exception:
            return None

    def event(self, event: dict[str, Any]) -> None:
        data = event.get("data") or {}
        entity_id = data.get("entity_id")
        cfg = CAMERAS.get(entity_id)
        if cfg is None:
            return
        new_state = data.get("new_state") or {}
        old_state = data.get("old_state") or {}
        if new_state.get("state") != "on" or old_state.get("state") == "on":
            return
        now = time.monotonic()
        if now - self.last_trigger.get(entity_id, 0.0) < 8.0:
            return
        self.last_trigger[entity_id] = now
        asyncio.create_task(self.handle_sound(cfg))

    async def stream_url(self, camera: str) -> str:
        if self.ws is None:
            raise RuntimeError("Home Assistant websocket unavailable")
        last_error = ""
        for agent in ("arlo", "linux"):
            try:
                result = await self.ws.rpc(
                    {
                        "type": "aarlo_stream_url",
                        "entity_id": camera,
                        "user_agent": agent,
                    },
                    timeout=25,
                )
                if result.get("success"):
                    url = (result.get("result") or {}).get("url")
                    if url:
                        return str(url)
                last_error = str(result)
            except Exception as err:
                last_error = f"{type(err).__name__}: {err}"
        raise RuntimeError(f"Unable to obtain Arlo stream URL: {last_error}")

    async def audio_to_wav(self, source: str, seconds: float) -> bytes:
        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
        if source.lower().startswith(("rtsp://", "rtsps://")):
            cmd += ["-rtsp_transport", "tcp"]
        cmd += [
            "-i", source,
            "-map", "0:a:0?",
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            "-t", str(max(2.0, seconds)),
            "-f", "wav",
            "pipe:1",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=max(25.0, seconds + 20.0)
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError("ffmpeg audio capture timed out")
        if proc.returncode not in (0, None) and len(stdout) < 1024:
            raise RuntimeError(
                f"ffmpeg failed ({proc.returncode}): {stderr.decode(errors='ignore')[-500:]}"
            )
        if len(stdout) < 1024:
            raise RuntimeError("Arlo stream contained no usable audio")
        return stdout

    async def transcribe(self, wav_data: bytes) -> str | None:
        response = await self.http.post(
            f"{HA_API}/stt/{STT_ENGINE}",
            headers={
                "X-Speech-Content": (
                    "language=de-DE; format=wav; codec=pcm; bit_rate=16; "
                    "sample_rate=16000; channel=1"
                ),
                "Content-Type": "audio/wav",
            },
            content=wav_data,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"STT HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        if data.get("result") != "success":
            return None
        text = str(data.get("text") or "").strip()
        return text or None

    async def execute_text(self, cfg: dict[str, str], text: str) -> bool:
        label = cfg["label"]
        source = cfg["source"]
        await self.set_helper(
            "input_text.assist_arlo_letzte_erkennung", f"{label}: {text}"
        )
        decision = parse_wake(text)
        now = time.monotonic()
        command = decision.command
        if decision.wake_only:
            self.armed_until[source] = now + 15.0
            await self.status(f"Arlo Voice {label}: Jarvis erkannt, 15 s Folgefenster")
            return True
        if command is None and self.armed_until.get(source, 0.0) > now:
            command = normalize(text)
            self.armed_until[source] = 0.0
        if not command:
            await self.status(f"Arlo Voice {label}: Sprache erkannt, kein Jarvis")
            return False
        normalized = normalize(command)
        if normalized == self.last_command and now - self.last_command_at < 12.0:
            return True
        self.last_command = normalized
        self.last_command_at = now
        self.armed_until[source] = 0.0
        await self.status(f"Arlo Voice {label}: Befehl -> {command}")
        response = await self.http.post(
            f"{HA_API}/services/script/jarvis_sprachbefehl",
            json={
                "befehl": command,
                "quelle": source,
                "antwort_ausgeben": True,
            },
        )
        response.raise_for_status()
        return True

    async def recording_fallback(
        self,
        cfg: dict[str, str],
        previous_video: str | None,
    ) -> None:
        if not RECORDING_FALLBACK:
            return
        camera = cfg["camera"]
        label = cfg["label"]
        for _ in range(8):
            await asyncio.sleep(5)
            state = await self.get_state(camera)
            video = ((state or {}).get("attributes") or {}).get("last_video")
            if not video or video == previous_video:
                continue
            try:
                await self.status(f"Arlo Voice {label}: prüfe neuen Arlo-Clip")
                wav = await self.audio_to_wav(str(video), 15)
                text = await self.transcribe(wav)
                if text:
                    await self.execute_text(cfg, text)
            except Exception as err:
                _LOGGER.warning("Recording fallback failed for %s: %s", label, err)
            return

    async def handle_sound(self, cfg: dict[str, str]) -> None:
        camera = cfg["camera"]
        label = cfg["label"]
        lock = self.locks[camera]
        if lock.locked():
            return
        async with lock:
            state = await self.get_state(camera)
            previous_video = ((state or {}).get("attributes") or {}).get("last_video")
            handled = False
            try:
                await self.status(f"Arlo Voice {label}: Sound erkannt, öffne Audiostream")
                url = await self.stream_url(camera)
                wav = await self.audio_to_wav(url, CAPTURE_SECONDS)
                text = await self.transcribe(wav)
                if text:
                    handled = await self.execute_text(cfg, text)
                else:
                    await self.status(f"Arlo Voice {label}: keine Sprache erkannt")
            except Exception as err:
                _LOGGER.warning("Live audio failed for %s: %s", label, err)
                await self.status(
                    f"Arlo Voice {label}: Live-Audio Fehler {type(err).__name__}"
                )
            if not handled:
                await self.recording_fallback(cfg, previous_video)

    async def run_once(self) -> None:
        self.ws = HAWebSocket(self.token, self.event)
        await self.ws.connect()
        await self.status("Arlo Voice: verbunden / 3 Kamera-Mikrofone bereit")
        assert self.ws.receiver_task is not None
        await self.ws.receiver_task

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.exception("Arlo voice websocket loop failed")
                await self.status(
                    f"Arlo Voice: Verbindung unterbrochen ({type(err).__name__})"
                )
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
