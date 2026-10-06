from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from collections import defaultdict
from typing import Any

IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
DASH_IPV4_RE = re.compile(r"(?<!\d)(\d{1,3})-(\d{1,3})-(\d{1,3})-(\d{1,3})(?!\d)")
MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])")


def _norm_mac(value: Any) -> str:
    return re.sub(r"[^0-9a-f]", "", str(value or "").lower())


def _valid_ipv4(value: str) -> str | None:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return None
    return str(addr) if addr.version == 4 else None


def _extract_ips_from_text(text: str) -> set[str]:
    out: set[str] = set()
    for match in IPV4_RE.finditer(text):
        ip = _valid_ipv4(match.group(0))
        if ip:
            out.add(ip)
    for match in DASH_IPV4_RE.finditer(text):
        ip = _valid_ipv4(".".join(match.groups()))
        if ip:
            out.add(ip)
    return out


def _extract_macs_from_text(text: str) -> set[str]:
    return {_norm_mac(m.group(0)) for m in MAC_RE.finditer(text)}


def _device_blob(device: dict[str, Any]) -> str:
    return json.dumps(device, ensure_ascii=False, sort_keys=True).lower()


def _device_network_identity(device: dict[str, Any]) -> tuple[set[str], set[str]]:
    blob = _device_blob(device)
    ips = _extract_ips_from_text(blob)
    macs = _extract_macs_from_text(blob)
    for conn in device.get("connections") or []:
        if isinstance(conn, (list, tuple)) and len(conn) >= 2:
            kind = str(conn[0] or "").lower()
            value = str(conn[1] or "")
            if kind in ("mac", "network_mac", "ethernet", "wifi"):
                norm = _norm_mac(value)
                if len(norm) == 12:
                    macs.add(norm)
            ip = _valid_ipv4(value)
            if ip:
                ips.add(ip)
    return ips, macs


def _state_network_identity(state: dict[str, Any]) -> tuple[set[str], set[str]]:
    attrs = state.get("attributes") or {}
    text = json.dumps(attrs, ensure_ascii=False, sort_keys=True).lower()
    return _extract_ips_from_text(text), _extract_macs_from_text(text)


def _local_ipv4s() -> set[str]:
    try:
        raw = subprocess.check_output(
            ["ip", "-j", "-4", "addr", "show"],
            text=True,
            timeout=10,
        )
        out: set[str] = set()
        for iface in json.loads(raw):
            name = str(iface.get("ifname") or "").lower()
            if name in ("lo", "hassio", "docker0") or name.startswith(("veth", "br-")):
                continue
            for info in iface.get("addr_info") or []:
                if str(info.get("family") or "") != "inet":
                    continue
                local = _valid_ipv4(str(info.get("local") or ""))
                if not local:
                    continue
                addr = ipaddress.ip_address(local)
                if addr.is_loopback or addr.is_link_local:
                    continue
                out.add(local)
        return out
    except Exception:
        return set()


def _ports(host: dict[str, Any]) -> set[int]:
    return {
        int(p.get("port"))
        for p in (host.get("ports") or [])
        if isinstance(p, dict) and str(p.get("port") or "").isdigit()
    }


def _summary(
    device: dict[str, Any],
    by_dev: dict[str, list[dict[str, Any]]],
    *,
    reasons: list[str],
    confidence: float,
) -> dict[str, Any]:
    did = device.get("id")
    return {
        "device_id": did,
        "name": device.get("name_by_user") or device.get("name"),
        "manufacturer": device.get("manufacturer"),
        "model": device.get("model"),
        "confidence": round(float(confidence), 2),
        "reasons": reasons,
        "entities": [
            e.get("entity_id")
            for e in by_dev.get(did, [])
            if e.get("entity_id")
        ][:50],
    }


def _add(
    bucket: dict[str, dict[str, Any]],
    device: dict[str, Any],
    by_dev: dict[str, list[dict[str, Any]]],
    *,
    reasons: list[str],
    confidence: float,
) -> None:
    did = str(device.get("id") or "")
    if not did:
        return
    current = bucket.get(did)
    if current:
        merged_reasons = list(dict.fromkeys((current.get("reasons") or []) + reasons))
        current["reasons"] = merged_reasons
        current["confidence"] = max(float(current.get("confidence") or 0), confidence)
        return
    bucket[did] = _summary(
        device,
        by_dev,
        reasons=reasons,
        confidence=confidence,
    )


def _physical_candidates(
    devices: list[dict[str, Any]],
    manufacturer: str,
    model_contains: str | None = None,
) -> list[dict[str, Any]]:
    m = manufacturer.casefold()
    result: list[dict[str, Any]] = []
    for d in devices:
        if str(d.get("entry_type") or "").lower() == "service":
            continue
        dm = str(d.get("manufacturer") or "").casefold()
        model = str(d.get("model") or "")
        if m not in dm:
            continue
        if model_contains and model_contains.casefold() not in model.casefold():
            continue
        result.append(d)
    return result


def _adjacent_mac_candidate(device: dict[str, Any], host_mac: str) -> bool:
    if len(host_mac) != 12:
        return False
    _, macs = _device_network_identity(device)
    host_prefix = host_mac[:10]
    host_last = int(host_mac[10:], 16)
    for mac in macs:
        if len(mac) != 12 or mac[:10] != host_prefix:
            continue
        try:
            if abs(int(mac[10:], 16) - host_last) <= 2:
                return True
        except ValueError:
            pass
    return False


def install_enhanced_correlation(base: Any) -> None:
    async def correlate(hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        regs = await base.registries()
        devices = regs.get("devices") or []
        entities = regs.get("entities") or []

        by_dev: dict[str, list[dict[str, Any]]] = defaultdict(list)
        entity_to_device: dict[str, str] = {}
        by_id: dict[str, dict[str, Any]] = {}
        for d in devices:
            if d.get("id"):
                by_id[str(d["id"])] = d
        for e in entities:
            did = e.get("device_id")
            eid = e.get("entity_id")
            if did:
                by_dev[str(did)].append(e)
            if did and eid:
                entity_to_device[str(eid)] = str(did)

        states: list[dict[str, Any]] = []
        try:
            raw_states = await base.ha_get("/states")
            if isinstance(raw_states, list):
                states = raw_states
        except Exception:
            states = []

        state_identity: list[tuple[str, set[str], set[str]]] = []
        for state in states:
            eid = str(state.get("entity_id") or "")
            did = entity_to_device.get(eid)
            if not did:
                continue
            ips, macs = _state_network_identity(state)
            if ips or macs:
                state_identity.append((did, ips, macs))

        device_identity: dict[str, tuple[set[str], set[str]]] = {}
        for d in devices:
            did = str(d.get("id") or "")
            if did:
                device_identity[did] = _device_network_identity(d)

        local_ips = _local_ipv4s()

        for host in hosts:
            confirmed: dict[str, dict[str, Any]] = {}
            candidates: dict[str, dict[str, Any]] = {}
            families: list[dict[str, Any]] = []

            ip = str(host.get("ip") or "")
            mac = _norm_mac(host.get("mac"))
            vendor = str(host.get("vendor") or "")
            vendor_cf = vendor.casefold()
            ports = _ports(host)

            for d in devices:
                did = str(d.get("id") or "")
                if not did:
                    continue
                ips, macs = device_identity.get(did, (set(), set()))
                reasons: list[str] = []
                if ip and ip in ips:
                    if re.search(rf"(?<!\d){re.escape(ip)}(?!\d)", _device_blob(d)):
                        reasons.append("exact_device_ip")
                    else:
                        reasons.append("exact_device_ip_encoded")
                if mac and mac in macs:
                    reasons.append("exact_device_mac")
                if mac:
                    rincon = f"rincon_{mac.upper()}01400".lower()
                    if rincon in _device_blob(d):
                        reasons.append("sonos_rincon_from_mac")
                if reasons:
                    _add(
                        confirmed,
                        d,
                        by_dev,
                        reasons=list(dict.fromkeys(reasons)),
                        confidence=1.0,
                    )

            for did, ips, macs in state_identity:
                reasons: list[str] = []
                if ip and ip in ips:
                    reasons.append("exact_entity_attribute_ip")
                if mac and mac in macs:
                    reasons.append("exact_entity_attribute_mac")
                if reasons and did in by_id:
                    _add(
                        confirmed,
                        by_id[did],
                        by_dev,
                        reasons=reasons,
                        confidence=1.0,
                    )

            if ip and ip in local_ips:
                ha_host_devices = [
                    d
                    for d in devices
                    if (
                        str(d.get("manufacturer") or "").casefold() == "home assistant"
                        and str(d.get("model") or "").casefold() == "home assistant host"
                    )
                    or (
                        str(d.get("manufacturer") or "").casefold() == "raspberry pi"
                        and str(d.get("model") or "").casefold().startswith("5")
                    )
                ]
                for d in ha_host_devices:
                    _add(
                        confirmed,
                        d,
                        by_dev,
                        reasons=["local_home_assistant_host"],
                        confidence=1.0,
                    )
                host["is_home_assistant_host"] = True

            # High-confidence multi-interface match, useful for devices such as
            # NVIDIA Shield where Wi-Fi/Ethernet interfaces can differ by one MAC.
            if "nvidia" in vendor_cf and {5555, 8008, 8009}.intersection(ports):
                shield_devices = _physical_candidates(devices, "nvidia", "shield")
                adjacent = [d for d in shield_devices if _adjacent_mac_candidate(d, mac)]
                if adjacent:
                    for d in adjacent:
                        if str(d.get("id") or "") not in confirmed:
                            _add(
                                candidates,
                                d,
                                by_dev,
                                reasons=["nvidia_adjacent_interface_mac", "shield_service_profile"],
                                confidence=0.96,
                            )
                else:
                    families.append(
                        {
                            "manufacturer": "NVIDIA",
                            "model_hint": "SHIELD Android TV",
                            "confidence": 0.82,
                            "reason": "nvidia_vendor_and_shield_service_profile",
                            "ambiguous": True,
                        }
                    )

            if "apple" in vendor_cf and {5000, 7000, 7100}.intersection(ports):
                apple_tvs = _physical_candidates(devices, "apple", "apple tv")
                if len(apple_tvs) == 1:
                    d = apple_tvs[0]
                    if str(d.get("id") or "") not in confirmed:
                        _add(
                            candidates,
                            d,
                            by_dev,
                            reasons=["apple_vendor", "airplay_service_profile"],
                            confidence=0.88,
                        )
                else:
                    families.append(
                        {
                            "manufacturer": "Apple",
                            "model_hint": "Apple TV / AirPlay device",
                            "confidence": 0.78,
                            "reason": "apple_vendor_and_airplay_service_profile",
                            "ambiguous": True,
                        }
                    )

            if "logitech" in vendor_cf:
                harmony = _physical_candidates(devices, "logitech", "harmony")
                if len(harmony) == 1:
                    d = harmony[0]
                    if str(d.get("id") or "") not in confirmed:
                        _add(
                            candidates,
                            d,
                            by_dev,
                            reasons=["logitech_vendor", "unique_harmony_device"],
                            confidence=0.9,
                        )
                else:
                    families.append(
                        {
                            "manufacturer": "Logitech",
                            "model_hint": "Logitech network device",
                            "confidence": 0.7,
                            "reason": "logitech_vendor",
                            "ambiguous": True,
                        }
                    )

            if "arlo" in vendor_cf and {554, 5051}.intersection(ports):
                arlo = _physical_candidates(devices, "arlo", "ABC1000")
                if arlo:
                    for d in arlo[:8]:
                        if str(d.get("id") or "") not in confirmed:
                            _add(
                                candidates,
                                d,
                                by_dev,
                                reasons=["arlo_vendor", "arlo_rtsp_device_profile"],
                                confidence=0.66,
                            )
                    families.append(
                        {
                            "manufacturer": "Arlo",
                            "model_hint": "ABC1000",
                            "confidence": 0.66,
                            "reason": "arlo_vendor_and_rtsp_profile",
                            "ambiguous": len(arlo) != 1,
                        }
                    )

            if "sonos" in vendor_cf and not confirmed:
                families.append(
                    {
                        "manufacturer": "Sonos",
                        "model_hint": "Sonos network component",
                        "confidence": 0.8,
                        "reason": "sonos_oui",
                        "ambiguous": True,
                    }
                )

            if "tuya" in vendor_cf and not confirmed:
                families.append(
                    {
                        "manufacturer": "Tuya",
                        "model_hint": "Tuya network device",
                        "confidence": 0.7,
                        "reason": "tuya_oui",
                        "ambiguous": True,
                    }
                )

            # Candidates are intentionally kept separate. Only deterministic
            # evidence enters home_assistant_matches, so unmanaged reporting
            # remains conservative and false positive resistant.
            host["home_assistant_matches"] = list(confirmed.values())
            host["home_assistant_candidates"] = [
                value
                for did, value in candidates.items()
                if did not in confirmed
            ]
            host["home_assistant_family_matches"] = families
            if confirmed:
                classification = "confirmed"
            elif candidates:
                classification = "candidate"
            elif families:
                classification = "family_only"
            else:
                classification = "unknown"
            host["home_assistant_correlation"] = {
                "classification": classification,
                "confirmed_count": len(confirmed),
                "candidate_count": len(candidates),
                "family_match_count": len(families),
            }

        return hosts

    base.correlate = correlate
