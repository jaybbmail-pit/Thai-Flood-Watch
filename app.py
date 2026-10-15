# -*- coding: utf-8 -*-
"""
Thai Flood Watch  -  ระบบติดตามสถานการณ์น้ำเพื่อวางแผนรับมือน้ำท่วม
Single-file Flask app (app.py) + Tailwind CSS (CDN)

แหล่งข้อมูล (เปิดสาธารณะ ไม่ต้องใช้ API key)
  - เขื่อน/อ่างเก็บน้ำ : กรมชลประทาน  app.rid.go.th/reservoir/api/dam/public
  - ระดับน้ำแม่น้ำ     : สสน. ThaiWater  api-v3.thaiwater.net (waterlevel)
  - พยากรณ์อากาศ       : Open-Meteo Forecast API
  - พยากรณ์น้ำท่า      : Open-Meteo Flood API (GloFAS)  ** ค่าจากแบบจำลอง ใช้ประกอบการตัดสินใจเท่านั้น
  - รายชื่ออำเภอ       : github.com/kongvut/thai-province-data

รัน:   pip install flask requests
       python app.py     ->  http://127.0.0.1:5000
"""
import re
import threading
import time
from datetime import datetime, timedelta

import requests
from flask import Flask, Response, jsonify, request

try:
    requests.packages.urllib3.disable_warnings()
except Exception:  # pragma: no cover
    pass

app = Flask(__name__)
app.json.ensure_ascii = False

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
RID_DAM = "https://app.rid.go.th/reservoir/api/dam/public"
TW_WATERLEVEL = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel"
OM_FORECAST = "https://api.open-meteo.com/v1/forecast"
OM_FLOOD = "https://flood-api.open-meteo.com/v1/flood"
OM_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
GEO_BASE = "https://raw.githubusercontent.com/kongvut/thai-province-data/master/api/latest/"
UA = {"User-Agent": "ThaiFloodWatch/1.0 (educational flood-planning dashboard)"}

REGIONS = ["เหนือ", "ตะวันออกเฉียงเหนือ", "กลาง", "ตะวันออก", "ตะวันตก", "ใต้"]

# (รหัสจังหวัด, ชื่อ, ภาค, lat, lon)  แบ่ง 6 ภาคตามราชบัณฑิตยสภา
PROVINCES = [
    ("10", "กรุงเทพมหานคร", "กลาง", 13.7563, 100.5018), ("11", "สมุทรปราการ", "กลาง", 13.5991, 100.5998),
    ("12", "นนทบุรี", "กลาง", 13.8621, 100.5144), ("13", "ปทุมธานี", "กลาง", 14.0208, 100.5250),
    ("14", "พระนครศรีอยุธยา", "กลาง", 14.3532, 100.5689), ("15", "อ่างทอง", "กลาง", 14.5896, 100.4550),
    ("16", "ลพบุรี", "กลาง", 14.7995, 100.6534), ("17", "สิงห์บุรี", "กลาง", 14.8936, 100.3967),
    ("18", "ชัยนาท", "กลาง", 15.1852, 100.1251), ("19", "สระบุรี", "กลาง", 14.5289, 100.9101),
    ("20", "ชลบุรี", "ตะวันออก", 13.3611, 100.9847), ("21", "ระยอง", "ตะวันออก", 12.6814, 101.2816),
    ("22", "จันทบุรี", "ตะวันออก", 12.6114, 102.1039), ("23", "ตราด", "ตะวันออก", 12.2428, 102.5175),
    ("24", "ฉะเชิงเทรา", "ตะวันออก", 13.6904, 101.0780), ("25", "ปราจีนบุรี", "ตะวันออก", 14.0509, 101.3727),
    ("26", "นครนายก", "กลาง", 14.2069, 101.2131), ("27", "สระแก้ว", "ตะวันออก", 13.8240, 102.0646),
    ("30", "นครราชสีมา", "ตะวันออกเฉียงเหนือ", 14.9799, 102.0978), ("31", "บุรีรัมย์", "ตะวันออกเฉียงเหนือ", 14.9930, 103.1029),
    ("32", "สุรินทร์", "ตะวันออกเฉียงเหนือ", 14.8818, 103.4937), ("33", "ศรีสะเกษ", "ตะวันออกเฉียงเหนือ", 15.1186, 104.3220),
    ("34", "อุบลราชธานี", "ตะวันออกเฉียงเหนือ", 15.2287, 104.8564), ("35", "ยโสธร", "ตะวันออกเฉียงเหนือ", 15.7921, 104.1453),
    ("36", "ชัยภูมิ", "ตะวันออกเฉียงเหนือ", 15.8068, 102.0316), ("37", "อำนาจเจริญ", "ตะวันออกเฉียงเหนือ", 15.8657, 104.6258),
    ("38", "บึงกาฬ", "ตะวันออกเฉียงเหนือ", 18.3609, 103.6464), ("39", "หนองบัวลำภู", "ตะวันออกเฉียงเหนือ", 17.2218, 102.4260),
    ("40", "ขอนแก่น", "ตะวันออกเฉียงเหนือ", 16.4322, 102.8236), ("41", "อุดรธานี", "ตะวันออกเฉียงเหนือ", 17.4138, 102.7872),
    ("42", "เลย", "ตะวันออกเฉียงเหนือ", 17.4860, 101.7223), ("43", "หนองคาย", "ตะวันออกเฉียงเหนือ", 17.8783, 102.7420),
    ("44", "มหาสารคาม", "ตะวันออกเฉียงเหนือ", 16.1851, 103.3026), ("45", "ร้อยเอ็ด", "ตะวันออกเฉียงเหนือ", 16.0538, 103.6520),
    ("46", "กาฬสินธุ์", "ตะวันออกเฉียงเหนือ", 16.4314, 103.5059), ("47", "สกลนคร", "ตะวันออกเฉียงเหนือ", 17.1546, 104.1348),
    ("48", "นครพนม", "ตะวันออกเฉียงเหนือ", 17.4048, 104.7784), ("49", "มุกดาหาร", "ตะวันออกเฉียงเหนือ", 16.5426, 104.7235),
    ("50", "เชียงใหม่", "เหนือ", 18.7883, 98.9853), ("51", "ลำพูน", "เหนือ", 18.5744, 99.0087),
    ("52", "ลำปาง", "เหนือ", 18.2888, 99.4908), ("53", "อุตรดิตถ์", "เหนือ", 17.6200, 100.0993),
    ("54", "แพร่", "เหนือ", 18.1446, 100.1410), ("55", "น่าน", "เหนือ", 18.7756, 100.7730),
    ("56", "พะเยา", "เหนือ", 19.1665, 99.9019), ("57", "เชียงราย", "เหนือ", 19.9105, 99.8406),
    ("58", "แม่ฮ่องสอน", "เหนือ", 19.3020, 97.9654), ("60", "นครสวรรค์", "กลาง", 15.7047, 100.1372),
    ("61", "อุทัยธานี", "กลาง", 15.3792, 100.0245), ("62", "กำแพงเพชร", "กลาง", 16.4828, 99.5227),
    ("63", "ตาก", "ตะวันตก", 16.8840, 99.1259), ("64", "สุโขทัย", "กลาง", 17.0056, 99.8264),
    ("65", "พิษณุโลก", "กลาง", 16.8211, 100.2659), ("66", "พิจิตร", "กลาง", 16.4429, 100.3488),
    ("67", "เพชรบูรณ์", "กลาง", 16.4190, 101.1605), ("70", "ราชบุรี", "ตะวันตก", 13.5283, 99.8134),
    ("71", "กาญจนบุรี", "ตะวันตก", 14.0228, 99.5328), ("72", "สุพรรณบุรี", "กลาง", 14.4745, 100.1177),
    ("73", "นครปฐม", "กลาง", 13.8199, 100.0443), ("74", "สมุทรสาคร", "กลาง", 13.5475, 100.2744),
    ("75", "สมุทรสงคราม", "กลาง", 13.4098, 100.0023), ("76", "เพชรบุรี", "ตะวันตก", 13.1112, 99.9447),
    ("77", "ประจวบคีรีขันธ์", "ตะวันตก", 11.8124, 99.7973), ("80", "นครศรีธรรมราช", "ใต้", 8.4304, 99.9631),
    ("81", "กระบี่", "ใต้", 8.0863, 98.9063), ("82", "พังงา", "ใต้", 8.4509, 98.5255),
    ("83", "ภูเก็ต", "ใต้", 7.8804, 98.3923), ("84", "สุราษฎร์ธานี", "ใต้", 9.1382, 99.3217),
    ("85", "ระนอง", "ใต้", 9.9529, 98.6085), ("86", "ชุมพร", "ใต้", 10.4930, 99.1800),
    ("90", "สงขลา", "ใต้", 7.1756, 100.6143), ("91", "สตูล", "ใต้", 6.6238, 100.0674),
    ("92", "ตรัง", "ใต้", 7.5563, 99.6114), ("93", "พัทลุง", "ใต้", 7.6167, 100.0740),
    ("94", "ปัตตานี", "ใต้", 6.8696, 101.2505), ("95", "ยะลา", "ใต้", 6.5411, 101.2804),
    ("96", "นราธิวาส", "ใต้", 6.4255, 101.8253),
]
PROV = {p[0]: {"code": p[0], "name": p[1], "region": p[2], "lat": p[3], "lon": p[4]} for p in PROVINCES}

# พิกัด/ที่ตั้งเขื่อนของกรมชลประทาน (id -> รหัสจังหวัด, อำเภอ, lat, lon)
DAM_META = {
    '100104': ('50', 'สันทราย', 18.9235, 99.1220), '100105': ('52', 'เมืองลำปาง', 18.5238, 99.6248),
    '100106': ('52', 'แจ้ห่ม', 18.8091, 99.6423), '100107': ('65', 'วัดโบสถ์', 17.1822, 100.4156),
    '100108': ('52', 'เถิน', 17.3201, 99.4518), '200101': ('63', 'สามเงา', 17.2419, 98.9715),
    '200102': ('53', 'ท่าปลา', 17.7681, 100.5549), '200103': ('50', 'แม่แตง', 19.1614, 99.0401),
    '100201': ('41', 'กุดจับ', 17.3604, 102.5724), '100202': ('47', 'พังโคน', 17.3000, 103.7500),
    '100206': ('46', 'เมืองกาฬสินธุ์', 16.6024, 103.4385), '100207': ('30', 'สีคิ้ว', 14.8650, 101.5617),
    '100208': ('30', 'ปักธงชัย', 14.5943, 101.8396), '100209': ('30', 'ครบุรี', 14.4842, 102.1471),
    '100210': ('30', 'ครบุรี', 14.4158, 102.2774), '100211': ('31', 'โนนดินแดง', 14.2994, 102.7597),
    '200203': ('47', 'ภูพาน', 16.9717, 103.9380), '200204': ('36', 'คอนสาร', 16.5333, 101.6546),
    '200205': ('40', 'อุบลรัตน์', 16.7703, 102.6213), '200212': ('34', 'สิรินธร', 15.2028, 105.4209),
    '100301': ('19', 'วังม่วง', 14.8569, 101.0761), '100302': ('61', 'ลานสัก', 15.5345, 99.4504),
    '100303': ('72', 'ด่านช้าง', 14.8306, 99.6617), '200401': ('71', 'ศรีสวัสดิ์', 14.4000, 99.1207),
    '200402': ('71', 'ทองผาภูมิ', 14.7975, 98.6041), '100501': ('26', 'เมืองนครนายก', 14.3147, 101.3214),
    '100502': ('24', 'ท่าตะเกียบ', 13.4319, 101.6478), '100503': ('20', 'ศรีราชา', 13.2214, 100.9662),
    '100504': ('21', 'ปลวกแดง', 12.9346, 101.2970), '100505': ('21', 'วังจันทร์', 12.9772, 101.5583),
    '100514': ('25', 'นาดี', 14.0808, 102.0273), '100602': ('77', 'ปราณบุรี', 12.4514, 99.8167),
    '200601': ('76', 'แก่งกระจาน', 12.9170, 99.6299), '200603': ('84', 'บ้านตาขุน', 9.0546, 98.6702),
    '200604': ('95', 'บันนังสตา', 6.1547, 101.2730),
}

# --------------------------------------------------------------------------
# Helpers: cache / http
# --------------------------------------------------------------------------
_cache = {}
_lock = threading.Lock()


def cached(key, ttl, fn):
    """cache พร้อม fallback เป็นข้อมูลเก่าเมื่อต้นทางล่ม"""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
    except Exception:
        if hit:
            return hit[1]
        raise
    with _lock:
        _cache[key] = (now, val)
    return val


def http_json(url, params=None, timeout=25):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=timeout)
    except requests.exceptions.SSLError:
        r = requests.get(url, params=params, headers=UA, timeout=timeout, verify=False)
    r.raise_for_status()
    return r.json()


def num(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def norm_name(s):
    s = (s or "").strip()
    s = re.sub(r"^(อำเภอ|เขต|อ\.)\s*", "", s)
    s = re.sub(r"\s*district$", "", s, flags=re.I)
    return s.strip()


def rnd(v, n=2):
    return None if v is None else round(v, n)


# --------------------------------------------------------------------------
# Data: dams
# --------------------------------------------------------------------------
def _load_dams():
    j = http_json(RID_DAM)
    out = []
    for grp in j.get("data", []):
        for d in grp.get("dam", []):
            meta = DAM_META.get(str(d.get("id")))
            prov = PROV.get(meta[0]) if meta else None
            vol, normal, cap = num(d.get("volume")), num(d.get("storage")), num(d.get("capacity"))
            inflow, outflow = num(d.get("inflow")) or 0.0, num(d.get("outflow")) or 0.0
            pct = num(d.get("percent_storage"))
            net = inflow - outflow  # ล้าน ลบ.ม./วัน
            proj7 = days_full = None
            if vol is not None and normal:
                proj7 = max(0.0, (vol + net * 7) / normal * 100)
                if net > 0 and vol < normal:
                    days_full = (normal - vol) / net
            out.append({
                "id": d.get("id"), "name": d.get("name"), "owner": d.get("owner"),
                "province": prov["name"] if prov else None, "province_code": meta[0] if meta else None,
                "amphoe": meta[1] if meta else None, "region": prov["region"] if prov else None,
                "lat": meta[2] if meta else None, "lon": meta[3] if meta else None,
                "capacity": cap, "normal": normal, "volume": vol, "pct": pct,
                "free": rnd(cap - vol, 1) if cap is not None and vol is not None else None,
                "inflow": inflow, "outflow": outflow, "net": rnd(net, 2),
                "inflow_cms": rnd(inflow * 11.574, 1), "outflow_cms": rnd(outflow * 11.574, 1),
                "proj7": rnd(proj7, 1), "days_full": rnd(days_full, 1),
            })
    return {"date": j.get("date"), "items": out}


def get_dams():
    return cached("dams", 900, _load_dams)


# --------------------------------------------------------------------------
# Data: river water level
# --------------------------------------------------------------------------
RIVER_STATUS = {
    3: ("ล้นตลิ่ง", "red"), 2: ("เสี่ยงสูง", "orange"), 1: ("เฝ้าระวัง", "yellow"),
    0: ("ปกติ", "green"), -1: ("ไม่มีข้อมูลตลิ่ง", "gray"),
}


def _load_rivers():
    j = http_json(TW_WATERLEVEL, timeout=90)
    now = datetime.now()
    out = []
    for r in j.get("data", []):
        st, g = r.get("station") or {}, r.get("geocode") or {}
        lat, lon = num(st.get("tele_station_lat")), num(st.get("tele_station_long"))
        pcode = str(g.get("province_code") or "")
        if lat is None or lon is None or pcode not in PROV:
            continue
        wl, prev = num(r.get("waterlevel_msl")), num(r.get("waterlevel_msl_previous"))
        pct = num(r.get("storage_percent"))
        if pct is None:
            ground, bank = num(st.get("ground_level")), num(st.get("min_bank"))
            if wl is not None and ground is not None and bank is not None and bank > ground:
                pct = (wl - ground) / (bank - ground) * 100
        if pct is None:
            lvl = num(r.get("situation_level"))
            status = 3 if lvl == 5 else -1
        else:
            status = 3 if pct >= 100 else 2 if pct >= 80 else 1 if pct >= 60 else 0
        t = None
        try:
            t = datetime.strptime(r.get("waterlevel_datetime"), "%Y-%m-%d %H:%M")
        except Exception:
            pass
        age_h = (now - t).total_seconds() / 3600 if t else None
        out.append({
            "id": st.get("id"), "name": (st.get("tele_station_name") or {}).get("th"),
            "river": r.get("river_name"), "basin": ((r.get("basin") or {}).get("basin_name") or {}).get("th"),
            "province": PROV[pcode]["name"], "province_code": pcode, "region": PROV[pcode]["region"],
            "amphoe": norm_name((g.get("amphoe_name") or {}).get("th")),
            "tambon": (g.get("tumbon_name") or {}).get("th"),
            "lat": lat, "lon": lon, "wl": wl, "trend": rnd(wl - prev, 2) if wl is not None and prev is not None else None,
            "discharge": num(r.get("discharge")), "pct": rnd(pct, 1), "status": status,
            "status_text": RIVER_STATUS[status][0], "time": r.get("waterlevel_datetime"),
            "stale": bool(age_h is not None and age_h > 72),
        })
    return {"items": out}


def get_rivers():
    return cached("rivers", 900, _load_rivers)


# --------------------------------------------------------------------------
# Data: geography (districts) / geocode
# --------------------------------------------------------------------------
def _load_districts():
    provs = http_json(GEO_BASE + "province.json", timeout=40)
    dists = http_json(GEO_BASE + "district.json", timeout=40)
    pid = {p["name"]["th"]: p["id"] for p in provs}
    by_pid = {}
    for d in dists:
        by_pid.setdefault(d["province_id"], []).append(norm_name(d["name"]["th"]))
    res = {}
    for code, p in PROV.items():
        res[code] = sorted(set(by_pid.get(pid.get(p["name"]), [])))
    return res


def get_districts(code):
    try:
        data = cached("districts", 86400 * 7, _load_districts)
        names = data.get(code, [])
        if names:
            return names
    except Exception:
        pass
    # fallback: อำเภอที่พบจากสถานีวัดน้ำ/เขื่อน
    try:
        names = {r["amphoe"] for r in get_rivers()["items"] if r["province_code"] == code and r["amphoe"]}
        names |= {d["amphoe"] for d in get_dams()["items"] if d["province_code"] == code and d["amphoe"]}
        return sorted(names)
    except Exception:
        return []


def geocode_district(amphoe, prov):
    def _go():
        j = http_json(OM_GEOCODE, {"name": amphoe, "count": 10, "language": "th", "countryCode": "TH"}, timeout=15)
        for r in j.get("results") or []:
            if prov["name"] in (r.get("admin1") or ""):
                return {"lat": r["latitude"], "lon": r["longitude"], "precise": True}
        return None
    try:
        hit = cached(("geo", amphoe, prov["code"]), 86400 * 30, _go)
        if hit:
            return hit
    except Exception:
        pass
    # fallback: ใช้ค่าเฉลี่ยพิกัดสถานีวัดน้ำในอำเภอ
    try:
        pts = [(r["lat"], r["lon"]) for r in get_rivers()["items"]
               if r["province_code"] == prov["code"] and r["amphoe"] == amphoe]
        if pts:
            return {"lat": sum(p[0] for p in pts) / len(pts), "lon": sum(p[1] for p in pts) / len(pts), "precise": True}
    except Exception:
        pass
    try:
        pts = [(d["lat"], d["lon"]) for d in get_dams()["items"]
               if d["province_code"] == prov["code"] and d["amphoe"] == amphoe and d["lat"]]
        if pts:
            return {"lat": pts[0][0], "lon": pts[0][1], "precise": True}
    except Exception:
        pass
    return {"lat": prov["lat"], "lon": prov["lon"], "precise": False}


# --------------------------------------------------------------------------
# Data: weather / river forecast
# --------------------------------------------------------------------------
WMO = {
    0: "ท้องฟ้าแจ่มใส", 1: "ส่วนใหญ่แจ่มใส", 2: "มีเมฆบางส่วน", 3: "มีเมฆมาก", 45: "หมอก", 48: "หมอกน้ำค้างแข็ง",
    51: "ฝนปรอยเล็กน้อย", 53: "ฝนปรอย", 55: "ฝนปรอยหนัก", 61: "ฝนเล็กน้อย", 63: "ฝนปานกลาง", 65: "ฝนหนัก",
    80: "ฝนฟ้าคะนองเล็กน้อย", 81: "ฝนฟ้าคะนอง", 82: "ฝนตกหนักมาก", 95: "พายุฝนฟ้าคะนอง",
    96: "พายุฝนฟ้าคะนอง+ลูกเห็บ", 99: "พายุฝนฟ้าคะนองรุนแรง",
}


def fetch_forecast(lat, lon):
    key = ("fc", round(lat, 2), round(lon, 2))

    def _go():
        return http_json(OM_FORECAST, {
            "latitude": round(lat, 4), "longitude": round(lon, 4), "timezone": "Asia/Bangkok", "forecast_days": 7,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                     "precipitation_probability_max,precipitation_hours,wind_speed_10m_max",
            "hourly": "precipitation,precipitation_probability",
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        })
    return cached(key, 1800, _go)


def fetch_discharge(lat, lon):
    key = ("fl", round(lat, 2), round(lon, 2))

    def _go():
        return http_json(OM_FLOOD, {
            "latitude": round(lat, 4), "longitude": round(lon, 4), "past_days": 5, "forecast_days": 14,
            "daily": "river_discharge,river_discharge_max",
        })
    return cached(key, 3600, _go)


def shape_weather(j):
    d, h, c = j.get("daily", {}), j.get("hourly", {}), j.get("current", {})
    days = []
    for i, t in enumerate(d.get("time", [])):
        code = d["weather_code"][i]
        days.append({
            "date": t, "text": WMO.get(code, "—"), "code": code,
            "tmax": d["temperature_2m_max"][i], "tmin": d["temperature_2m_min"][i],
            "rain": d["precipitation_sum"][i] or 0, "prob": d["precipitation_probability_max"][i],
            "rain_hours": d["precipitation_hours"][i], "wind": d["wind_speed_10m_max"][i],
        })
    now_s = datetime.now().strftime("%Y-%m-%dT%H:00")
    ht = h.get("time", [])
    start = next((i for i, t in enumerate(ht) if t >= now_s), 0)
    hourly = [{"t": ht[i], "rain": h["precipitation"][i] or 0, "prob": h["precipitation_probability"][i]}
              for i in range(start, min(start + 48, len(ht)))]
    return {"current": c, "days": days, "hourly": hourly}


def shape_discharge(j):
    d = j.get("daily", {})
    t, q, qm = d.get("time", []), d.get("river_discharge", []), d.get("river_discharge_max", [])
    today = datetime.now().strftime("%Y-%m-%d")
    series = [{"date": t[i], "q": q[i], "qmax": qm[i] if i < len(qm) else None} for i in range(len(t))]
    fut = [s for s in series if s["date"] >= today and s["q"] is not None]
    info = None
    if fut:
        peak = max(fut, key=lambda s: s["q"])
        cur = fut[0]["q"]
        ratio = peak["q"] / cur if cur else None
        trend = "เพิ่มขึ้น" if ratio and ratio > 1.15 else "ลดลง" if ratio and ratio < 0.87 else "ทรงตัว"
        info = {"now": cur, "peak": peak["q"], "peak_date": peak["date"], "ratio": rnd(ratio, 2), "trend": trend}
    return {"series": series, "info": info, "today": today}


def get_overview_rain():
    """ฝนพยากรณ์ 3 วัน ทุกจังหวัดในคำขอเดียว"""
    def _go():
        codes = [p[0] for p in PROVINCES]
        j = http_json(OM_FORECAST, {
            "latitude": ",".join(str(PROV[c]["lat"]) for c in codes),
            "longitude": ",".join(str(PROV[c]["lon"]) for c in codes),
            "timezone": "Asia/Bangkok", "forecast_days": 3,
            "daily": "precipitation_sum,precipitation_probability_max",
        }, timeout=40)
        if isinstance(j, dict):
            j = [j]
        return {c: j[i]["daily"] for i, c in enumerate(codes) if i < len(j)}
    return cached("ov_rain", 1800, _go)


# --------------------------------------------------------------------------
# Risk assessment
# --------------------------------------------------------------------------
LEVELS = [
    (0, "ต่ำ", "green"), (2, "เฝ้าระวัง", "yellow"), (4, "เตือนภัย", "orange"), (6, "วิกฤต", "red"),
]

ADVICE = {
    "green": ["ติดตามสถานการณ์น้ำและพยากรณ์อากาศทุกวัน", "ตรวจสอบเส้นทางระบายน้ำ ท่อ คูคลอง ไม่ให้อุดตัน",
              "ทบทวนแผนเผชิญเหตุและรายชื่อผู้ประสานงานในพื้นที่"],
    "yellow": ["ติดตามประกาศเตือนภัยจากกรมอุตุนิยมวิทยา/ปภ. อย่างใกล้ชิด", "ตรวจเครื่องสูบน้ำ เครื่องผลักดันน้ำ และกระสอบทราย",
               "แจ้งชุมชนริมน้ำและพื้นที่ลุ่มต่ำให้เตรียมพร้อม", "ตรวจสอบเส้นทางอพยพและศูนย์พักพิงชั่วคราว"],
    "orange": ["เตรียมขนย้ายทรัพย์สิน/ยานพาหนะขึ้นที่สูงในพื้นที่เสี่ยง", "ตั้งศูนย์อำนวยการและสื่อสารเตือนภัยถึงประชาชนล่วงหน้า",
               "เตรียมเรือ รถบรรทุกสูง และเวชภัณฑ์ให้พร้อมใช้งาน", "ประสานกรมชลประทานเรื่องการบริหารจัดการน้ำท้ายเขื่อน/ประตูระบายน้ำ",
               "งดกิจกรรมใกล้ลำน้ำ เฝ้าระวังน้ำป่าไหลหลากและดินถล่มในพื้นที่ภูเขา"],
    "red": ["สั่งการอพยพประชาชนกลุ่มเสี่ยง (ผู้สูงอายุ เด็ก ผู้ป่วย) ไปศูนย์พักพิงทันที", "ตัดไฟฟ้าในพื้นที่น้ำท่วมถึง ป้องกันไฟฟ้าดูด",
            "ปิดเส้นทางที่น้ำท่วมสูง ประกาศเส้นทางสำรอง", "ระดมเรือกู้ภัย เจ้าหน้าที่ และอาหาร/น้ำดื่มเข้าพื้นที่",
            "โทร 1784 (ปภ.) / 1669 (ฉุกเฉินการแพทย์) / 191 เมื่อต้องการความช่วยเหลือ"],
}


def assess(dams, rivers, daily):
    score, reasons = 0, []
    if daily:
        rain = [x or 0 for x in daily.get("precipitation_sum", [])[:3]]
        mx, tot = (max(rain) if rain else 0), sum(rain)
        if mx >= 90 or tot >= 150:
            score += 3; reasons.append(f"คาดการณ์ฝนสูงสุด {mx:.0f} มม./วัน (3 วันรวม {tot:.0f} มม.) – ฝนหนักมาก")
        elif mx >= 35 or tot >= 80:
            score += 2; reasons.append(f"คาดการณ์ฝนสูงสุด {mx:.0f} มม./วัน (3 วันรวม {tot:.0f} มม.) – ฝนหนัก")
        elif mx >= 10:
            score += 1; reasons.append(f"คาดการณ์ฝนสูงสุด {mx:.0f} มม./วัน (3 วันรวม {tot:.0f} มม.)")
    live = [r for r in rivers if not r["stale"]]
    over = [r for r in live if r["status"] == 3]
    high = [r for r in live if r["status"] == 2]
    n = max(len(live), 1)
    if over:
        score += 3 if len(over) >= 3 or len(over) / n > 0.1 else 2
        reasons.append(f"สถานีวัดน้ำล้นตลิ่ง {len(over)} แห่ง")
    if high:
        score += 1
        reasons.append(f"สถานีวัดน้ำระดับเสี่ยงสูง (80–100% ของตลิ่ง) {len(high)} แห่ง")
    d_hi = [d for d in dams if (d["pct"] or 0) >= 90 or (d["proj7"] or 0) >= 100]
    d_mid = [d for d in dams if (d["pct"] or 0) >= 80]
    if d_hi:
        score += 2
        reasons.append("เขื่อนใกล้เต็ม/คาดเต็มใน 7 วัน: " + ", ".join(d["name"] for d in d_hi[:4]))
    elif d_mid:
        score += 1
        reasons.append("เขื่อนมีน้ำเกิน 80%: " + ", ".join(d["name"] for d in d_mid[:4]))
    lvl = LEVELS[0]
    for L in LEVELS:
        if score >= L[0]:
            lvl = L
    if not reasons:
        reasons.append("ไม่พบปัจจัยเสี่ยงที่โดดเด่นจากข้อมูลที่มี")
    return {"score": score, "label": lvl[1], "color": lvl[2], "reasons": reasons, "advice": ADVICE[lvl[2]]}


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/api/geo")
def api_geo():
    return jsonify({"regions": REGIONS, "provinces": list(PROV.values())})


@app.get("/api/districts")
def api_districts():
    return jsonify(get_districts(request.args.get("province", "")))


def _filter(items, region, pcode, amphoe, amphoe_key="amphoe"):
    out = []
    for x in items:
        if region and x.get("region") != region:
            continue
        if pcode and x.get("province_code") != pcode:
            continue
        if amphoe and x.get(amphoe_key) != amphoe:
            continue
        out.append(x)
    return out


@app.get("/api/area")
def api_area():
    region = request.args.get("region", "")
    pcode = request.args.get("province", "")
    amphoe = norm_name(request.args.get("amphoe", ""))
    errors = {}
    dams, rivers, dam_date = [], [], None
    try:
        dd = get_dams()
        dam_date = dd["date"]
        dams = _filter(dd["items"], region, pcode, "")  # เขื่อนแสดงระดับจังหวัด (อำเภอใช้แสดงที่ตั้ง)
    except Exception as e:
        errors["dams"] = f"โหลดข้อมูลเขื่อนไม่สำเร็จ: {e.__class__.__name__}"
    try:
        rivers = _filter(get_rivers()["items"], region, pcode, amphoe)
    except Exception as e:
        errors["rivers"] = f"โหลดข้อมูลระดับน้ำไม่สำเร็จ: {e.__class__.__name__}"

    loc = weather = discharge = None
    if pcode in PROV:
        p = PROV[pcode]
        loc = {"name": p["name"], "lat": p["lat"], "lon": p["lon"], "precise": True, "level": "province"}
        if amphoe:
            g = geocode_district(amphoe, p)
            loc = {"name": f"{amphoe}, {p['name']}", **g, "level": "district"}
        try:
            wj = fetch_forecast(loc["lat"], loc["lon"])
            weather = shape_weather(wj)
        except Exception as e:
            errors["weather"] = f"โหลดพยากรณ์อากาศไม่สำเร็จ: {e.__class__.__name__}"
        try:
            discharge = shape_discharge(fetch_discharge(loc["lat"], loc["lon"]))
        except Exception as e:
            errors["discharge"] = f"โหลดพยากรณ์น้ำท่าไม่สำเร็จ: {e.__class__.__name__}"
        daily = {"precipitation_sum": [d["rain"] for d in weather["days"]]} if weather else None
    else:
        daily = None
        try:  # ระดับภาค: ใช้ฝนสูงสุดของจังหวัดในภาคนั้น
            ov = get_overview_rain()
            cs = [c for c, p in PROV.items() if not region or p["region"] == region]
            days = [ov[c] for c in cs if c in ov]
            if days:
                n = len(days[0]["precipitation_sum"])
                daily = {"precipitation_sum": [max((d["precipitation_sum"][i] or 0) for d in days) for i in range(n)]}
        except Exception as e:
            errors["weather"] = f"โหลดพยากรณ์อากาศไม่สำเร็จ: {e.__class__.__name__}"

    risk = assess(dams, rivers, daily)
    rivers.sort(key=lambda r: (-r["status"] if r["status"] >= 0 else 1, -(r["pct"] or 0)))
    return jsonify({
        "dams": dams, "dam_date": dam_date, "rivers": rivers, "location": loc, "weather": weather,
        "discharge": discharge, "risk": risk, "errors": errors, "updated": datetime.now().strftime("%d/%m/%Y %H:%M"),
    })


@app.get("/api/overview")
def api_overview():
    region = request.args.get("region", "")
    try:
        rain = get_overview_rain()
    except Exception:
        rain = {}
    try:
        dams = get_dams()["items"]
    except Exception:
        dams = []
    try:
        rivers = [r for r in get_rivers()["items"] if not r["stale"]]
    except Exception:
        rivers = []
    rows = []
    for code, p in PROV.items():
        if region and p["region"] != region:
            continue
        d = rain.get(code)
        r3 = [x or 0 for x in d["precipitation_sum"][:3]] if d else []
        pd = [x for x in dams if x["province_code"] == code]
        rv = [x for x in rivers if x["province_code"] == code]
        a = assess(pd, rv, {"precipitation_sum": r3} if r3 else None)
        rows.append({
            "code": code, "name": p["name"], "region": p["region"], "rain": [rnd(x, 1) for x in r3],
            "rain_total": rnd(sum(r3), 1) if r3 else None,
            "prob": max((x or 0) for x in d["precipitation_probability_max"][:3]) if d else None,
            "dams": len(pd), "dam_max": max((x["pct"] or 0) for x in pd) if pd else None,
            "stations": len(rv), "over": sum(1 for x in rv if x["status"] == 3),
            "high": sum(1 for x in rv if x["status"] == 2),
            "score": a["score"], "label": a["label"], "color": a["color"],
        })
    rows.sort(key=lambda r: -r["score"])
    return jsonify(rows)


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


# --------------------------------------------------------------------------
# Front-end (Tailwind CDN + Chart.js + Leaflet)
# --------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thai Flood Watch – ติดตามสถานการณ์น้ำ</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  body{font-family:'Noto Sans Thai',system-ui,sans-serif}
  #map{height:420px;border-radius:.75rem;z-index:0}
  .tab-btn{padding:.5rem 1rem;border-bottom:3px solid transparent;color:#64748b;font-weight:500;white-space:nowrap}
  .tab-btn.active{color:#0369a1;border-color:#0369a1}
  th.sortable{cursor:pointer;user-select:none}
  .bar{height:.5rem;border-radius:9999px;background:#e2e8f0;overflow:hidden}
  .bar>i{display:block;height:100%}
  .spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body class="bg-slate-100 text-slate-800">

<header class="bg-gradient-to-r from-sky-800 to-cyan-600 text-white">
  <div class="max-w-7xl mx-auto px-4 py-5 flex flex-wrap items-center justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold">🌊 Thai Flood Watch</h1>
      <p class="text-sky-100 text-sm">ศูนย์ติดตามน้ำ เขื่อน แม่น้ำ และพยากรณ์ เพื่อวางแผนรับมือน้ำท่วม</p>
    </div>
    <div class="text-right text-sm text-sky-100">
      <div>อัปเดตล่าสุด: <span id="updated">–</span></div>
      <button id="btnRefresh" class="mt-1 bg-white/20 hover:bg-white/30 rounded-lg px-3 py-1">⟳ รีเฟรช</button>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-4 py-5 space-y-5">

  <!-- Filters -->
  <section class="bg-white rounded-xl shadow p-4 grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
    <label class="block"><span class="text-sm text-slate-500">ภาค</span>
      <select id="selRegion" class="mt-1 w-full border rounded-lg px-3 py-2"><option value="">ทั้งประเทศ</option></select></label>
    <label class="block"><span class="text-sm text-slate-500">จังหวัด</span>
      <select id="selProvince" class="mt-1 w-full border rounded-lg px-3 py-2"><option value="">ทุกจังหวัด</option></select></label>
    <label class="block"><span class="text-sm text-slate-500">อำเภอ / เขต</span>
      <select id="selAmphoe" class="mt-1 w-full border rounded-lg px-3 py-2" disabled><option value="">ทุกอำเภอ</option></select></label>
    <div class="text-xs text-slate-500">เลือกจังหวัด/อำเภอเพื่อดูพยากรณ์อากาศและน้ำท่ารายพื้นที่<br>เขื่อนแสดงในระดับจังหวัด</div>
  </section>

  <div id="errors" class="hidden bg-amber-50 border border-amber-300 text-amber-800 rounded-xl p-3 text-sm"></div>

  <!-- Risk banner -->
  <section id="risk" class="rounded-xl shadow p-5 bg-white">
    <div class="text-slate-400">กำลังโหลดข้อมูล…</div>
  </section>

  <!-- KPI -->
  <section id="kpi" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3"></section>

  <!-- Map -->
  <section class="bg-white rounded-xl shadow p-4">
    <div class="flex flex-wrap items-center justify-between mb-2 gap-2">
      <h2 class="font-semibold">แผนที่เขื่อนและสถานีวัดระดับน้ำ</h2>
      <div class="text-xs flex flex-wrap gap-3 text-slate-600">
        <span>■ เขื่อน (สีตาม % น้ำ)</span>
        <span><b class="text-green-600">●</b> ปกติ</span><span><b class="text-yellow-500">●</b> เฝ้าระวัง</span>
        <span><b class="text-orange-500">●</b> เสี่ยงสูง</span><span><b class="text-red-600">●</b> ล้นตลิ่ง</span>
      </div>
    </div>
    <div id="map"></div>
  </section>

  <!-- Tabs -->
  <section class="bg-white rounded-xl shadow">
    <nav class="flex overflow-x-auto border-b px-2" id="tabs">
      <button class="tab-btn active" data-tab="dams">เขื่อน / อ่างเก็บน้ำ</button>
      <button class="tab-btn" data-tab="rivers">ระดับน้ำแม่น้ำ</button>
      <button class="tab-btn" data-tab="weather">พยากรณ์อากาศ</button>
      <button class="tab-btn" data-tab="flood">พยากรณ์น้ำท่า</button>
      <button class="tab-btn" data-tab="overview">ภาพรวมรายจังหวัด</button>
      <button class="tab-btn" data-tab="plan">แผนรับมือ</button>
    </nav>

    <!-- Dams -->
    <div id="tab-dams" class="tab p-4">
      <div class="flex flex-wrap gap-2 justify-between mb-3">
        <input id="damSearch" placeholder="ค้นหาเขื่อน / จังหวัด…" class="border rounded-lg px-3 py-2 text-sm w-64">
        <div class="text-xs text-slate-500 self-center">ข้อมูลกรมชลประทาน ณ <span id="damDate">–</span> · ปริมาณหน่วย: ล้าน ลบ.ม. (อัตราไหล: ล้าน ลบ.ม./วัน และ ลบ.ม./วินาที)</div>
      </div>
      <div class="h-64 mb-4"><canvas id="chDams"></canvas></div>
      <div class="overflow-x-auto"><table class="w-full text-sm" id="tblDams"></table></div>
    </div>

    <!-- Rivers -->
    <div id="tab-rivers" class="tab p-4 hidden">
      <div class="flex flex-wrap gap-2 justify-between mb-3">
        <input id="rvSearch" placeholder="ค้นหาสถานี / แม่น้ำ / อำเภอ…" class="border rounded-lg px-3 py-2 text-sm w-64">
        <select id="rvStatus" class="border rounded-lg px-3 py-2 text-sm">
          <option value="">ทุกสถานะ</option><option value="3">ล้นตลิ่ง</option><option value="2">เสี่ยงสูง</option>
          <option value="1">เฝ้าระวัง</option><option value="0">ปกติ</option>
        </select>
      </div>
      <p class="text-xs text-slate-500 mb-2">% ตลิ่ง = ระดับน้ำเทียบความสูงตลิ่งต่ำสุด (≥100% ล้นตลิ่ง) · ข้อมูล สสน. (ThaiWater) · ซ่อนสถานีที่ไม่อัปเดตเกิน 3 วันจากการประเมินความเสี่ยง</p>
      <div class="overflow-x-auto"><table class="w-full text-sm" id="tblRivers"></table></div>
      <button id="rvMore" class="hidden mt-3 text-sky-700 text-sm underline">แสดงเพิ่ม</button>
    </div>

    <!-- Weather -->
    <div id="tab-weather" class="tab p-4 hidden"><div id="weatherBox"></div></div>

    <!-- Flood forecast -->
    <div id="tab-flood" class="tab p-4 hidden"><div id="floodBox"></div></div>

    <!-- Overview -->
    <div id="tab-overview" class="tab p-4 hidden">
      <p class="text-xs text-slate-500 mb-2">จัดอันดับความเสี่ยงจาก: ฝนพยากรณ์ 3 วัน + สถานีวัดน้ำล้นตลิ่ง + ระดับน้ำเขื่อน · คลิกแถวเพื่อเลือกจังหวัด</p>
      <div class="overflow-x-auto"><table class="w-full text-sm" id="tblOverview"></table></div>
    </div>

    <!-- Plan -->
    <div id="tab-plan" class="tab p-4 hidden">
      <div id="planBox"></div>
    </div>
  </section>

  <footer class="text-xs text-slate-500 pb-8 leading-relaxed">
    แหล่งข้อมูล: กรมชลประทาน (RID), สถาบันสารสนเทศทรัพยากรน้ำ (สสน./ThaiWater), Open-Meteo (พยากรณ์อากาศ + Flood API/GloFAS), kongvut/thai-province-data.
    พยากรณ์น้ำท่ามาจากแบบจำลองกริด ~5 กม. อาจแตกต่างจากสถานการณ์จริงของแม่น้ำสายย่อย — ใช้เพื่อประกอบการวางแผนเท่านั้น
    โปรดยึดประกาศอย่างเป็นทางการจากกรมอุตุนิยมวิทยา (TMD), กรมชลประทาน และกรมป้องกันและบรรเทาสาธารณภัย (ปภ.)
  </footer>
</main>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = (v, d=1) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('th-TH', {minimumFractionDigits: d, maximumFractionDigits: d});
const COLORS = {green:'#16a34a', yellow:'#eab308', orange:'#f97316', red:'#dc2626', gray:'#94a3b8'};
const BADGE = {green:'bg-green-100 text-green-800', yellow:'bg-yellow-100 text-yellow-800', orange:'bg-orange-100 text-orange-800', red:'bg-red-100 text-red-800', gray:'bg-slate-100 text-slate-600'};
const RV_COLOR = {3:'red', 2:'orange', 1:'yellow', 0:'green', '-1':'gray'};
const damColor = p => p == null ? 'gray' : p >= 90 ? 'red' : p >= 80 ? 'orange' : p >= 60 ? 'yellow' : 'green';
const badge = (t, c) => `<span class="px-2 py-0.5 rounded-full text-xs font-medium ${BADGE[c]}">${esc(t)}</span>`;
const dayName = d => new Date(d + 'T00:00:00').toLocaleDateString('th-TH', {weekday:'short', day:'numeric', month:'short'});
const icon = c => c === 0 || c === 1 ? '☀️' : c === 2 ? '⛅' : c === 3 ? '☁️' : (c >= 45 && c < 50) ? '🌫️' : (c >= 95) ? '⛈️' : (c >= 80) ? '🌦️' : '🌧️';

let geo = null, data = null, charts = {}, map = null, layer = null, rvLimit = 100;
let sortDam = {k:'pct', dir:-1}, ovRows = [];

function mkChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($('#' + id), cfg);
}

/* ---------- filters ---------- */
async function init() {
  geo = await (await fetch('/api/geo')).json();
  $('#selRegion').innerHTML += geo.regions.map(r => `<option value="${esc(r)}">ภาค${esc(r)}</option>`).join('');
  fillProvinces();
  $('#selRegion').onchange = () => { fillProvinces(); fillAmphoe(); loadAll(); };
  $('#selProvince').onchange = async () => {
    const p = geo.provinces.find(x => x.code === $('#selProvince').value);
    if (p) $('#selRegion').value = p.region;
    await fillAmphoe(); loadAll();
  };
  $('#selAmphoe').onchange = loadAll;
  $('#btnRefresh').onclick = loadAll;
  document.querySelectorAll('.tab-btn').forEach(b => b.onclick = () => showTab(b.dataset.tab));
  $('#damSearch').oninput = renderDams;
  $('#rvSearch').oninput = () => { rvLimit = 100; renderRivers(); };
  $('#rvStatus').onchange = () => { rvLimit = 100; renderRivers(); };
  $('#rvMore').onclick = () => { rvLimit += 200; renderRivers(); };
  map = L.map('map').setView([13.0, 101.0], 6);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom: 18, attribution: '© OpenStreetMap'}).addTo(map);
  layer = L.layerGroup().addTo(map);
  loadAll();
  setInterval(loadAll, 15 * 60 * 1000);
}

function fillProvinces() {
  const r = $('#selRegion').value, cur = $('#selProvince').value;
  const list = geo.provinces.filter(p => !r || p.region === r).sort((a, b) => a.name.localeCompare(b.name, 'th'));
  $('#selProvince').innerHTML = '<option value="">ทุกจังหวัด</option>' + list.map(p => `<option value="${p.code}">${esc(p.name)}</option>`).join('');
  if (list.some(p => p.code === cur)) $('#selProvince').value = cur;
}

async function fillAmphoe() {
  const code = $('#selProvince').value, el = $('#selAmphoe');
  el.innerHTML = '<option value="">ทุกอำเภอ</option>';
  el.disabled = !code;
  if (!code) return;
  try {
    const list = await (await fetch('/api/districts?province=' + code)).json();
    el.innerHTML += list.map(a => `<option>${esc(a)}</option>`).join('');
  } catch (e) {}
}

function showTab(t) {
  document.querySelectorAll('.tab').forEach(x => x.classList.add('hidden'));
  document.querySelectorAll('.tab-btn').forEach(x => x.classList.toggle('active', x.dataset.tab === t));
  $('#tab-' + t).classList.remove('hidden');
  if (data) renderTab(t);
}

/* ---------- load ---------- */
async function loadAll() {
  const q = new URLSearchParams({region: $('#selRegion').value, province: $('#selProvince').value, amphoe: $('#selAmphoe').value});
  $('#btnRefresh').classList.add('opacity-60');
  $('#btnRefresh').firstChild.textContent = '⏳ กำลังโหลด… ';
  try {
    const [a, o] = await Promise.all([
      fetch('/api/area?' + q).then(r => r.json()),
      fetch('/api/overview?region=' + encodeURIComponent($('#selRegion').value)).then(r => r.json()).catch(() => [])
    ]);
    data = a; ovRows = o;
  } catch (e) {
    $('#risk').innerHTML = `<div class="text-red-600">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</div>`;
    return;
  } finally {
    $('#btnRefresh').classList.remove('opacity-60');
    $('#btnRefresh').firstChild.textContent = '⟳ รีเฟรช';
  }
  $('#updated').textContent = data.updated;
  const errs = Object.values(data.errors || {});
  $('#errors').classList.toggle('hidden', !errs.length);
  $('#errors').innerHTML = errs.map(esc).join('<br>');
  renderRisk(); renderKpi(); renderMap();
  renderTab(document.querySelector('.tab-btn.active').dataset.tab);
}

function areaName() {
  const a = $('#selAmphoe').value, p = $('#selProvince'), r = $('#selRegion').value;
  if (a) return `${a}, ${p.selectedOptions[0].text}`;
  if (p.value) return 'จ.' + p.selectedOptions[0].text;
  if (r) return 'ภาค' + r;
  return 'ทั้งประเทศ';
}

function renderRisk() {
  const r = data.risk, c = COLORS[r.color];
  $('#risk').style.borderLeft = `8px solid ${c}`;
  $('#risk').innerHTML = `
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div class="text-sm text-slate-500">ระดับความเสี่ยงน้ำท่วม · ${esc(areaName())}</div>
        <div class="text-3xl font-bold" style="color:${c}">${esc(r.label)} <span class="text-base font-normal text-slate-400">(คะแนน ${r.score}/9)</span></div>
        <ul class="mt-2 text-sm list-disc ml-5 space-y-0.5">${r.reasons.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>
      <div class="md:max-w-md text-sm bg-slate-50 rounded-lg p-3">
        <div class="font-semibold mb-1">ข้อแนะนำเบื้องต้น</div>
        <ul class="list-disc ml-5 space-y-0.5">${r.advice.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      </div>
    </div>`;
}

function kpi(label, val, sub, color) {
  return `<div class="bg-white rounded-xl shadow p-3"><div class="text-xs text-slate-500">${label}</div>
    <div class="text-2xl font-bold" style="color:${COLORS[color] || '#0f172a'}">${val}</div><div class="text-xs text-slate-400">${sub || ''}</div></div>`;
}

function renderKpi() {
  const D = data.dams, R = data.rivers.filter(r => !r.stale);
  const volSum = D.reduce((s, d) => s + (d.volume || 0), 0), nSum = D.reduce((s, d) => s + (d.normal || 0), 0);
  const free = D.reduce((s, d) => s + (d.free || 0), 0);
  const over = R.filter(r => r.status === 3).length, high = R.filter(r => r.status === 2).length;
  const rain3 = data.weather ? data.weather.days.slice(0, 3).reduce((s, d) => s + d.rain, 0) : null;
  const di = data.discharge && data.discharge.info;
  $('#kpi').innerHTML = [
    kpi('จำนวนเขื่อน', D.length, 'ในพื้นที่ที่เลือก'),
    kpi('ปริมาณน้ำรวมเขื่อน', nSum ? fmt(volSum / nSum * 100, 0) + '%' : '–', nSum ? `${fmt(volSum, 0)} / ${fmt(nSum, 0)} ล้าน ลบ.ม.` : '', nSum ? damColor(volSum / nSum * 100) : ''),
    kpi('พื้นที่ว่างรับน้ำ', D.length ? fmt(free, 0) : '–', 'ล้าน ลบ.ม. (ความจุสูงสุด − ปัจจุบัน)'),
    kpi('สถานีล้นตลิ่ง', over, `เสี่ยงสูง ${high} · จาก ${R.length} สถานี`, over ? 'red' : 'green'),
    kpi('ฝนพยากรณ์ 3 วัน', rain3 == null ? '–' : fmt(rain3, 0) + ' มม.', data.weather ? esc(data.location.name) : 'เลือกจังหวัดเพื่อดู', rain3 >= 80 ? 'red' : rain3 >= 35 ? 'orange' : ''),
    kpi('น้ำท่า (GloFAS)', di ? di.trend : '–', di ? `สูงสุด ${fmt(di.peak, 0)} ลบ.ม./วิ (${dayName(di.peak_date)})` : 'เลือกจังหวัดเพื่อดู', di && di.ratio > 1.5 ? 'orange' : ''),
  ].join('');
}

function renderMap() {
  layer.clearLayers();
  const pts = [];
  data.rivers.forEach(r => {
    if (r.status < 0 || r.stale) return;
    L.circleMarker([r.lat, r.lon], {radius: r.status >= 2 ? 6 : 4, color: COLORS[RV_COLOR[r.status]], fillColor: COLORS[RV_COLOR[r.status]], fillOpacity: .75, weight: 1})
      .bindPopup(`<b>${esc(r.name)}</b><br>${esc(r.river || '')}<br>อ.${esc(r.amphoe)} จ.${esc(r.province)}<br>ระดับ ${fmt(r.wl, 2)} ม.รทก. · ${fmt(r.pct, 0)}% ของตลิ่ง<br>${esc(r.status_text)} · ${esc(r.time)}`)
      .addTo(layer);
    pts.push([r.lat, r.lon]);
  });
  data.dams.forEach(d => {
    if (d.lat == null) return;
    const c = COLORS[damColor(d.pct)];
    L.marker([d.lat, d.lon], {icon: L.divIcon({className: '', iconSize: [18, 18], html: `<div style="width:18px;height:18px;background:${c};border:2px solid #fff;box-shadow:0 0 3px #000;border-radius:3px"></div>`})})
      .bindPopup(`<b>${esc(d.name)}</b><br>จ.${esc(d.province)}<br>น้ำ ${fmt(d.volume, 1)} / ${fmt(d.normal, 0)} ล้าน ลบ.ม. (${fmt(d.pct, 0)}%)<br>ไหลเข้า ${fmt(d.inflow_cms, 0)} · ปล่อย ${fmt(d.outflow_cms, 0)} ลบ.ม./วิ`)
      .addTo(layer);
    pts.push([d.lat, d.lon]);
  });
  if (data.location) {
    L.circleMarker([data.location.lat, data.location.lon], {radius: 9, color: '#0369a1', fillOpacity: 0, weight: 3})
      .bindTooltip('จุดพยากรณ์: ' + data.location.name).addTo(layer);
    if (!pts.length) pts.push([data.location.lat, data.location.lon]);
  }
  setTimeout(() => { map.invalidateSize(); if (pts.length) map.fitBounds(pts, {padding: [30, 30], maxZoom: 11}); }, 50);
}

/* ---------- tabs ---------- */
function renderTab(t) {
  ({dams: renderDams, rivers: renderRivers, weather: renderWeather, flood: renderFlood, overview: renderOverview, plan: renderPlan})[t]();
}

function th(label, key, cur) {
  const arrow = cur && cur.k === key ? (cur.dir > 0 ? ' ▲' : ' ▼') : '';
  return `<th class="sortable px-2 py-2 text-left whitespace-nowrap" data-k="${key}">${label}${arrow}</th>`;
}

function renderDams() {
  $('#damDate').textContent = data.dam_date || '–';
  const q = $('#damSearch').value.trim();
  let rows = data.dams.filter(d => !q || (d.name + (d.province || '')).includes(q));
  rows.sort((a, b) => ((a[sortDam.k] ?? -1) > (b[sortDam.k] ?? -1) ? 1 : -1) * sortDam.dir);
  if (sortDam.k === 'name' || sortDam.k === 'province') rows.sort((a, b) => String(a[sortDam.k] ?? '').localeCompare(String(b[sortDam.k] ?? ''), 'th') * sortDam.dir);
  const hdr = [['เขื่อน', 'name'], ['จังหวัด', 'province'], ['น้ำปัจจุบัน', 'volume'], ['% ของความจุ', 'pct'], ['ว่างรับน้ำ', 'free'],
    ['ไหลเข้า', 'inflow'], ['ระบาย', 'outflow'], ['สุทธิ/วัน', 'net'], ['คาด 7 วัน', 'proj7']];
  $('#tblDams').innerHTML = `<thead class="bg-slate-50 text-slate-600"><tr>${hdr.map(h => th(h[0], h[1], sortDam)).join('')}<th class="px-2 py-2">สถานะ</th></tr></thead><tbody>` +
    (rows.map(d => {
      const c = damColor(d.pct), pc = d.proj7 == null ? '' : damColor(d.proj7);
      const st = d.pct >= 90 ? ['เสี่ยงล้นอ่าง', 'red'] : d.pct >= 80 ? ['น้ำมาก', 'orange'] : d.pct >= 60 ? ['ปานกลาง', 'yellow'] : d.pct >= 30 ? ['ปกติ', 'green'] : ['น้ำน้อย', 'gray'];
      return `<tr class="border-t hover:bg-slate-50">
        <td class="px-2 py-2 font-medium">${esc(d.name)}</td><td class="px-2">${esc(d.province || '–')}</td>
        <td class="px-2">${fmt(d.volume, 1)} <span class="text-slate-400">/ ${fmt(d.normal, 0)}</span></td>
        <td class="px-2 w-40"><div class="flex items-center gap-2"><div class="bar flex-1"><i style="width:${Math.min(d.pct || 0, 100)}%;background:${COLORS[c]}"></i></div><b>${fmt(d.pct, 0)}%</b></div></td>
        <td class="px-2">${fmt(d.free, 1)}</td>
        <td class="px-2">${fmt(d.inflow, 2)} <span class="text-slate-400 text-xs">(${fmt(d.inflow_cms, 0)} ลบ.ม./วิ)</span></td>
        <td class="px-2">${fmt(d.outflow, 2)} <span class="text-slate-400 text-xs">(${fmt(d.outflow_cms, 0)} ลบ.ม./วิ)</span></td>
        <td class="px-2 ${d.net > 0 ? 'text-red-600' : 'text-green-600'}">${d.net > 0 ? '+' : ''}${fmt(d.net, 2)}</td>
        <td class="px-2"><b style="color:${COLORS[pc] || '#334155'}">${fmt(d.proj7, 0)}%</b>${d.days_full != null && d.days_full <= 30 ? `<div class="text-xs text-red-600">เต็มใน ~${fmt(d.days_full, 0)} วัน</div>` : ''}</td>
        <td class="px-2">${badge(st[0], st[1])}</td></tr>`;
    }).join('') || `<tr><td colspan="10" class="p-6 text-center text-slate-400">ไม่พบเขื่อนของกรมชลประทานในพื้นที่ที่เลือก</td></tr>`) + '</tbody>';
  $('#tblDams').querySelectorAll('th.sortable').forEach(h => h.onclick = () => {
    sortDam = {k: h.dataset.k, dir: sortDam.k === h.dataset.k ? -sortDam.dir : -1}; renderDams();
  });
  const top = [...rows].sort((a, b) => (b.pct || 0) - (a.pct || 0)).slice(0, 15);
  mkChart('chDams', {type: 'bar', data: {labels: top.map(d => d.name.replace('เขื่อน', '')),
    datasets: [{label: '% น้ำปัจจุบัน', data: top.map(d => d.pct), backgroundColor: top.map(d => COLORS[damColor(d.pct)])},
               {label: 'คาดการณ์ 7 วัน', data: top.map(d => d.proj7), backgroundColor: '#cbd5e1'}]},
    options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, suggestedMax: 100, title: {display: true, text: '% ของความจุใช้การ'}}}}});
}

function renderRivers() {
  const q = $('#rvSearch').value.trim(), s = $('#rvStatus').value;
  const all = data.rivers.filter(r => (!q || (r.name + r.river + r.amphoe + r.province).includes(q)) && (s === '' || String(r.status) === s));
  const rows = all.slice(0, rvLimit);
  $('#tblRivers').innerHTML = `<thead class="bg-slate-50 text-slate-600"><tr>${['สถานี', 'แม่น้ำ', 'อำเภอ', 'จังหวัด', 'ระดับน้ำ (ม.รทก.)', 'แนวโน้ม', '% ตลิ่ง', 'อัตราไหล (ลบ.ม./วิ)', 'สถานะ', 'เวลา'].map(h => `<th class="px-2 py-2 text-left whitespace-nowrap">${h}</th>`).join('')}</tr></thead><tbody>` +
    (rows.map(r => `<tr class="border-t hover:bg-slate-50 ${r.stale ? 'opacity-50' : ''}">
      <td class="px-2 py-1.5 font-medium">${esc(r.name)}</td><td class="px-2">${esc(r.river || '–')}</td><td class="px-2">${esc(r.amphoe)}</td><td class="px-2">${esc(r.province)}</td>
      <td class="px-2">${fmt(r.wl, 2)}</td>
      <td class="px-2 ${r.trend > 0 ? 'text-red-600' : r.trend < 0 ? 'text-green-600' : ''}">${r.trend == null ? '–' : (r.trend > 0 ? '▲ +' : r.trend < 0 ? '▼ ' : '– ') + fmt(r.trend, 2)}</td>
      <td class="px-2 w-32">${r.pct == null ? '–' : `<div class="flex items-center gap-1"><div class="bar flex-1"><i style="width:${Math.max(0, Math.min(r.pct, 100))}%;background:${COLORS[RV_COLOR[r.status]]}"></i></div><b class="text-xs">${fmt(r.pct, 0)}%</b></div>`}</td>
      <td class="px-2">${fmt(r.discharge, 1)}</td><td class="px-2">${badge(r.stale ? 'ข้อมูลเก่า' : r.status_text, r.stale ? 'gray' : RV_COLOR[r.status])}</td>
      <td class="px-2 text-xs text-slate-500 whitespace-nowrap">${esc(r.time)}</td></tr>`).join('') ||
      `<tr><td colspan="10" class="p-6 text-center text-slate-400">ไม่พบสถานีวัดระดับน้ำ</td></tr>`) + '</tbody>';
  $('#rvMore').classList.toggle('hidden', all.length <= rvLimit);
  $('#rvMore').textContent = `แสดงเพิ่ม (เหลือ ${all.length - rvLimit} สถานี)`;
}

function renderWeather() {
  const box = $('#weatherBox');
  if (!data.weather) {
    box.innerHTML = `<div class="p-8 text-center text-slate-400">เลือก <b>จังหวัด</b> (และอำเภอ) เพื่อดูพยากรณ์อากาศ 7 วัน และรายชั่วโมง 48 ชม.ข้างหน้า<br>หรือดูตารางฝนรายจังหวัดในแท็บ “ภาพรวมรายจังหวัด”</div>`;
    return;
  }
  const w = data.weather, c = w.current || {}, loc = data.location;
  box.innerHTML = `
    <div class="flex flex-wrap justify-between gap-2 mb-3">
      <div><div class="font-semibold">${esc(loc.name)}</div>
      <div class="text-xs text-slate-500">${loc.precise ? '' : '⚠ ไม่พบพิกัดอำเภอ ใช้พิกัดกลางจังหวัดแทน · '}พิกัด ${fmt(loc.lat, 3)}, ${fmt(loc.lon, 3)}</div></div>
      <div class="text-sm bg-sky-50 rounded-lg px-3 py-2">ขณะนี้ ${fmt(c.temperature_2m, 1)}°C · ความชื้น ${fmt(c.relative_humidity_2m, 0)}% · ลม ${fmt(c.wind_speed_10m, 0)} กม./ชม. · ฝน ${fmt(c.precipitation, 1)} มม.</div>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
      ${w.days.map(d => `<div class="border rounded-lg p-2 text-center ${d.rain >= 90 ? 'bg-red-50 border-red-300' : d.rain >= 35 ? 'bg-orange-50 border-orange-300' : d.rain >= 10 ? 'bg-yellow-50 border-yellow-300' : ''}">
        <div class="text-xs text-slate-500">${dayName(d.date)}</div><div class="text-3xl">${icon(d.code)}</div>
        <div class="text-xs">${esc(d.text)}</div><div class="text-sm font-semibold">${fmt(d.tmax, 0)}° <span class="text-slate-400 font-normal">${fmt(d.tmin, 0)}°</span></div>
        <div class="text-sm text-sky-700 font-semibold">${fmt(d.rain, 1)} มม.</div><div class="text-xs text-slate-500">โอกาสฝน ${fmt(d.prob, 0)}% · ${fmt(d.rain_hours, 0)} ชม.</div></div>`).join('')}
    </div>
    <div class="grid md:grid-cols-2 gap-4">
      <div><div class="text-sm font-semibold mb-1">ปริมาณฝนรายวัน (มม.) และโอกาสเกิดฝน (%)</div><div class="h-64"><canvas id="chRainDay"></canvas></div></div>
      <div><div class="text-sm font-semibold mb-1">ฝนรายชั่วโมง 48 ชม.ข้างหน้า (มม.)</div><div class="h-64"><canvas id="chRainHour"></canvas></div></div>
    </div>
    <p class="text-xs text-slate-500 mt-2">เกณฑ์ฝน/วัน: ≥10 มม. ฝนปานกลาง · ≥35 มม. ฝนหนัก · ≥90 มม. ฝนหนักมาก</p>`;
  mkChart('chRainDay', {data: {labels: w.days.map(d => dayName(d.date)), datasets: [
    {type: 'bar', label: 'ฝน (มม.)', data: w.days.map(d => d.rain), backgroundColor: w.days.map(d => d.rain >= 90 ? COLORS.red : d.rain >= 35 ? COLORS.orange : d.rain >= 10 ? COLORS.yellow : '#38bdf8'), yAxisID: 'y'},
    {type: 'line', label: 'โอกาสฝน (%)', data: w.days.map(d => d.prob), borderColor: '#6366f1', yAxisID: 'y1', tension: .3}]},
    options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true}, y1: {position: 'right', min: 0, max: 100, grid: {drawOnChartArea: false}}}}});
  mkChart('chRainHour', {type: 'bar', data: {labels: w.hourly.map(h => h.t.slice(5, 10).replace('-', '/') + ' ' + h.t.slice(11)), datasets: [{label: 'ฝน (มม.)', data: w.hourly.map(h => h.rain), backgroundColor: '#0ea5e9'}]},
    options: {maintainAspectRatio: false, plugins: {legend: {display: false}}, scales: {x: {ticks: {maxTicksLimit: 8}}, y: {beginAtZero: true}}}});
}

function renderFlood() {
  const box = $('#floodBox'), f = data.discharge;
  if (!f) {
    box.innerHTML = `<div class="p-8 text-center text-slate-400">เลือก <b>จังหวัด</b> (และอำเภอ) เพื่อดูพยากรณ์ปริมาณน้ำท่าในแม่น้ำล่วงหน้า 14 วัน</div>`;
    return;
  }
  const i = f.info;
  box.innerHTML = `
    <div class="mb-3 text-sm grid md:grid-cols-4 gap-2">
      <div class="bg-slate-50 rounded-lg p-3"><div class="text-xs text-slate-500">ปริมาณน้ำท่าวันนี้</div><div class="text-xl font-bold">${i ? fmt(i.now, 1) : '–'} <span class="text-sm font-normal">ลบ.ม./วิ</span></div></div>
      <div class="bg-slate-50 rounded-lg p-3"><div class="text-xs text-slate-500">คาดว่าสูงสุดใน 14 วัน</div><div class="text-xl font-bold">${i ? fmt(i.peak, 1) : '–'} <span class="text-sm font-normal">ลบ.ม./วิ</span></div><div class="text-xs">${i ? dayName(i.peak_date) : ''}</div></div>
      <div class="bg-slate-50 rounded-lg p-3"><div class="text-xs text-slate-500">แนวโน้ม</div><div class="text-xl font-bold">${i ? esc(i.trend) : '–'}</div><div class="text-xs">${i && i.ratio ? 'สูงสุด = ' + fmt(i.ratio, 2) + ' เท่าของวันนี้' : ''}</div></div>
      <div class="bg-slate-50 rounded-lg p-3"><div class="text-xs text-slate-500">พื้นที่</div><div class="font-semibold">${esc(data.location.name)}</div></div>
    </div>
    <div class="h-72"><canvas id="chFlood"></canvas></div>
    <p class="text-xs text-slate-500 mt-2">ที่มา: Open-Meteo Flood API (GloFAS) ปริมาณน้ำท่าที่จุดกริดใกล้พื้นที่ที่เลือก (ไม่ใช่ระดับน้ำที่สถานีวัด) · เส้นประ = ค่าสูงสุดจากชุดการพยากรณ์ (ensemble) · เส้นแนวตั้ง = วันนี้</p>
    <div class="mt-4"><div class="text-sm font-semibold mb-1">คาดการณ์ระดับน้ำเขื่อนล่วงหน้า 7 วัน (สมมติอัตราไหลเข้า–ระบายคงที่)</div><div id="damProj" class="text-sm"></div></div>`;
  const s = f.series, ti = s.findIndex(x => x.date === f.today);
  mkChart('chFlood', {type: 'line', data: {labels: s.map(x => dayName(x.date)), datasets: [
    {label: 'ปริมาณน้ำท่า (ลบ.ม./วิ)', data: s.map(x => x.q), borderColor: '#0284c7', backgroundColor: 'rgba(2,132,199,.12)', fill: true, tension: .3,
      segment: {borderDash: c => c.p0DataIndex < ti ? [] : undefined}},
    {label: 'ค่าสูงสุดของ ensemble', data: s.map(x => x.qmax), borderColor: '#f97316', borderDash: [5, 4], pointRadius: 0, tension: .3}]},
    options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, title: {display: true, text: 'ลบ.ม./วินาที'}}},
      plugins: {tooltip: {mode: 'index', intersect: false}}}, plugins: [{id: 'today', afterDraw(ch) {
        if (ti < 0) return; const x = ch.scales.x.getPixelForValue(ti), a = ch.chartArea, g = ch.ctx;
        g.save(); g.strokeStyle = '#64748b'; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, a.top); g.lineTo(x, a.bottom); g.stroke(); g.restore(); }}]});
  const dm = data.dams.filter(d => d.proj7 != null).sort((a, b) => b.proj7 - a.proj7).slice(0, 8);
  $('#damProj').innerHTML = dm.length ? `<div class="grid md:grid-cols-2 gap-x-6 gap-y-1">${dm.map(d =>
    `<div class="flex justify-between border-b py-1"><span>${esc(d.name)}</span><span>${fmt(d.pct, 0)}% → <b style="color:${COLORS[damColor(d.proj7)]}">${fmt(d.proj7, 0)}%</b>${d.days_full != null && d.days_full <= 30 ? ` <span class="text-xs text-red-600">(เต็มใน ~${fmt(d.days_full, 0)} วัน)</span>` : ''}</span></div>`).join('')}</div>`
    : '<span class="text-slate-400">ไม่มีเขื่อนในพื้นที่ที่เลือก</span>';
}

function renderOverview() {
  const rows = ovRows;
  $('#tblOverview').innerHTML = `<thead class="bg-slate-50 text-slate-600"><tr>${['จังหวัด', 'ภาค', 'ฝน 3 วัน (มม.)', 'วันที่ 1 / 2 / 3', 'โอกาสฝนสูงสุด', 'เขื่อน (สูงสุด %)', 'สถานีล้นตลิ่ง / เสี่ยงสูง', 'ความเสี่ยง'].map(h => `<th class="px-2 py-2 text-left whitespace-nowrap">${h}</th>`).join('')}</tr></thead><tbody>` +
    rows.map(r => `<tr class="border-t hover:bg-sky-50 cursor-pointer" data-code="${r.code}">
      <td class="px-2 py-1.5 font-medium">${esc(r.name)}</td><td class="px-2">${esc(r.region)}</td>
      <td class="px-2 font-semibold ${r.rain_total >= 80 ? 'text-red-600' : r.rain_total >= 35 ? 'text-orange-600' : ''}">${fmt(r.rain_total, 0)}</td>
      <td class="px-2 text-xs text-slate-500">${r.rain.map(x => fmt(x, 0)).join(' / ')}</td><td class="px-2">${r.prob == null ? '–' : r.prob + '%'}</td>
      <td class="px-2">${r.dams ? `${r.dams} (${fmt(r.dam_max, 0)}%)` : '–'}</td>
      <td class="px-2">${r.stations ? `<b class="${r.over ? 'text-red-600' : ''}">${r.over}</b> / ${r.high} <span class="text-xs text-slate-400">จาก ${r.stations}</span>` : '–'}</td>
      <td class="px-2">${badge(r.label, r.color)}</td></tr>`).join('') + '</tbody>';
  $('#tblOverview').querySelectorAll('tr[data-code]').forEach(tr => tr.onclick = async () => {
    const p = geo.provinces.find(x => x.code === tr.dataset.code);
    $('#selRegion').value = p.region; fillProvinces(); $('#selProvince').value = p.code;
    await fillAmphoe(); await loadAll(); showTab('weather'); window.scrollTo({top: 0, behavior: 'smooth'});
  });
}

function renderPlan() {
  const phase = (t, items) => `<div class="border rounded-lg p-3"><div class="font-semibold mb-1">${t}</div><ul class="space-y-1 text-sm">${items.map(i => `<li><label class="flex gap-2"><input type="checkbox" class="mt-1"><span>${i}</span></label></li>`).join('')}</ul></div>`;
  $('#planBox').innerHTML = `
    <div class="mb-3 text-sm">ระดับความเสี่ยงปัจจุบันของ <b>${esc(areaName())}</b>: ${badge(data.risk.label, data.risk.color)}</div>
    <div class="grid md:grid-cols-3 gap-3">
      ${phase('1) เตรียมความพร้อม (ก่อนเกิดเหตุ)', ['ตรวจสอบพยากรณ์อากาศและระดับน้ำทุกวันผ่านหน้านี้', 'จัดทำแผนที่เสี่ยงน้ำท่วม จุดอพยพ และเส้นทางสำรอง', 'ตรวจเครื่องสูบน้ำ/เรือ/กระสอบทราย/ไฟฉาย/วิทยุ', 'จัดเตรียมถุงยังชีพ น้ำดื่ม ยาประจำตัว เอกสารสำคัญกันน้ำ', 'ขุดลอกคูคลอง เปิดทางน้ำ ตรวจประตูระบายน้ำ', 'ซักซ้อมแผนกับชุมชนและอาสาสมัคร'])}
      ${phase('2) ระหว่างเหตุการณ์', ['ติดตามประกาศเตือนภัยทางการ ไม่เชื่อข่าวลือ', 'ขนย้ายทรัพย์สิน/รถยนต์ขึ้นที่สูง ตัดไฟชั้นล่าง', 'อพยพกลุ่มเปราะบางก่อน (ผู้สูงอายุ เด็ก ผู้ป่วย ผู้พิการ)', 'หลีกเลี่ยงการเดินลุยน้ำเชี่ยว/น้ำป่า/สายไฟ', 'รายงานสถานการณ์ผ่านศูนย์อำนวยการ', 'ประสานกรมชลประทานเรื่องการพร่องน้ำ/ผันน้ำ'])}
      ${phase('3) ฟื้นฟูหลังน้ำลด', ['ตรวจสอบความปลอดภัยโครงสร้าง ระบบไฟฟ้า ประปา', 'ทำความสะอาดและฆ่าเชื้อ ป้องกันโรคน้ำกัดเท้า/ฉี่หนู/อหิวาต์', 'สำรวจความเสียหายเพื่อขอรับการช่วยเหลือ', 'ถอดบทเรียนและปรับปรุงแผนรอบถัดไป'])}
    </div>
    <div class="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-2 text-sm">
      ${[['ปภ. สายด่วนนิรภัย', '1784'], ['กรมชลประทาน', '1460'], ['กรมอุตุนิยมวิทยา', '1182'], ['ฉุกเฉินการแพทย์', '1669']].map(c => `<div class="bg-sky-50 rounded-lg p-3"><div class="text-xs text-slate-500">${c[0]}</div><div class="text-2xl font-bold text-sky-800">${c[1]}</div></div>`).join('')}
    </div>`;
}

init();
</script>
</body>
</html>
"""

def _warm():
    for fn in (get_dams, get_rivers, get_overview_rain):
        try:
            fn()
        except Exception:
            pass


if __name__ == "__main__":
    threading.Thread(target=_warm, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
