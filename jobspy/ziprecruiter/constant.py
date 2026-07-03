import uuid
import base64
import random
from datetime import datetime, timezone

def _generate_headers():
    # Generate fresh device ID each run
    device_id = str(uuid.uuid4()).upper()
    
    # Fresh push notification ID
    push_id = uuid.uuid4().hex + uuid.uuid4().hex
    
    # App versions to rotate
    app_versions = ["93.0", "94.0", "95.0", "96.0"]
    app_build_numbers = ["4801", "4823", "4850", "4901"]
    app_v = random.choice(app_versions)
    build_n = random.choice(app_build_numbers)
    
    return {
        "Host": "api.ziprecruiter.com",
        "accept": "*/*",
        "x-zr-zva-override": f"100000000;vid:ZT1huzm_EQlDTVEc",
        "x-pushnotificationid": push_id,
        "x-deviceid": device_id,
        "user-agent": f"Job Search/{app_v} (iPhone; CPU iOS 16_6_1 like Mac OS X)",
        "authorization": "Basic YTBlZjMyZDYtN2I0Yy00MWVkLWEyODMtYTI1NDAzMzI0YTcyOg==",
        "accept-language": "en-US,en;q=0.9",
        "x-app-version": app_v,
        "x-build-number": build_n,
    }

def _generate_cookie_data():
    app_versions = ["93.0", "94.0", "95.0", "96.0"]
    app_v = random.choice(app_versions)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return [
        ("event_type", "session"),
        ("logged_in", "false"),
        ("number_of_retry", "1"),
        ("property", "model:iPhone"),
        ("property", "os:iOS"),
        ("property", "locale:en_us"),
        ("property", "app_build_number:4850"),
        ("property", f"app_version:{app_v}"),
        ("property", "manufacturer:Apple"),
        ("property", f"timestamp:{ts}"),
        ("property", "screen_height:852"),
        ("property", "os_version:16_6_1"),
        ("property", "source:organic"),
        ("property", "screen_width:393"),
        ("property", "device_model:iPhone 15 Pro"),
        ("property", "brand:Apple"),
    ]

headers = _generate_headers()
get_cookie_data = _generate_cookie_data()