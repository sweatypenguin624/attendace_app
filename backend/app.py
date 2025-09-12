# recognize_server.py
import os
import base64
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import cv2
import numpy as np
from deepface import DeepFace
from werkzeug.utils import secure_filename
import csv

app = Flask(__name__)
CORS(app)  # enable CORS for all routes

# --- CONFIG ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")        # student images folder
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")      # temporary uploads (optional)
ATTENDANCE_DIR = os.path.join(BASE_DIR, "attendance")
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(ATTENDANCE_DIR, exist_ok=True)

# DeepFace settings
MODEL_NAME = "ArcFace"
DETECTOR_BACKEND = "opencv"
DISTANCE_METRIC = "cosine"
THRESHOLD = 0.6   # <= threshold => match. tune as needed.

ALLOWED_EXT = {"png", "jpg", "jpeg"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_base64_image(b64data, save_folder=UPLOADS_DIR, ext="jpg"):
    """Save a base64 data URL or raw base64 string to a timestamped file. Return filepath."""
    if b64data.startswith("data:"):
        # remove header
        b64data = b64data.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(b64data)
    except Exception:
        return None
    fname = datetime.now().strftime("%Y%m%d%H%M%S%f") + f".{ext}"
    path = os.path.join(save_folder, secure_filename(fname))
    with open(path, "wb") as fh:
        fh.write(img_bytes)
    return path


def load_image_cv(path_or_bytes):
    """
    Given a filesystem path (str) or raw bytes, return cv2 image (BGR).
    """
    if isinstance(path_or_bytes, str) and os.path.exists(path_or_bytes):
        img = cv2.imread(path_or_bytes)
        return img
    if isinstance(path_or_bytes, (bytes, bytearray)):
        nparr = np.frombuffer(path_or_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    return None


def parse_name_roll_from_filename(identity_path):
    """
    identity_path example: '/full/path/images/Student_Name_123.jpg'
    parse into (name, roll)
    Logic: strip extension, split by underscore. If at least 2 tokens,
    roll_number = second last token (or last but one), name = everything before roll joined by '_'.
    If no roll detected, roll='Unknown' and name = whole base.
    """
    base = os.path.basename(identity_path)
    name_noext = os.path.splitext(base)[0]
    parts = name_noext.split("_")
    if len(parts) >= 2:
        # assume last token is maybe an index; roll probably second-last
        roll = parts[-1]
        name = "_".join(parts[:-1])
        return name, roll
    else:
        return name_noext, "Unknown"


def attendance_filepath_for_today():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(ATTENDANCE_DIR, f"attendance_{today}.txt")


def is_within_one_hour(name, filepath):
    """Return True if `name` has an entry in filepath whose time is within last hour."""
    if not os.path.isfile(filepath):
        return False
    try:
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if not row:
                    continue
                # row format: Name,Time,Distance
                rname = row[0]
                rtime_str = row[1] if len(row) > 1 else None
                if rname == name and rtime_str:
                    try:
                        last_time = datetime.strptime(rtime_str, "%H:%M:%S")
                    except Exception:
                        # if stored differently, ignore
                        continue
                    # make last_time same date as today
                    now = datetime.now()
                    last_time = last_time.replace(year=now.year, month=now.month, day=now.day)
                    diff_seconds = (now - last_time).total_seconds()
                    return diff_seconds < 3600
    except Exception:
        return False
    return False


@app.route("/api/recognize", methods=["POST"])
def api_recognize():
    """
    Accepts:
      - multipart/form-data with file field 'frame'
      - JSON body with 'image': dataURL or base64 string
      - optionally 'time' field in form or json (ignored if not provided)
    Returns JSON:
      { success: True/False, name: str or None, roll: str or None, distance: float or None, message: str }
    """
    probe_img = None
    tmp_path = None

    # 1) multipart upload
    if "frame" in request.files:
        f = request.files["frame"]
        if f.filename == "":
            return jsonify(success=False, message="No selected file"), 400
        if not allowed_file(f.filename):
            return jsonify(success=False, message="File type not allowed"), 400
        saved_name = datetime.now().strftime("%Y%m%d%H%M%S%f") + "_" + secure_filename(f.filename)
        tmp_path = os.path.join(UPLOADS_DIR, saved_name)
        f.save(tmp_path)
        probe_img = load_image_cv(tmp_path)

    else:
        # 2) JSON body with base64 image
        data = request.get_json(silent=True)
        if data and ("image" in data or "frame" in data):
            img_b64 = data.get("image") or data.get("frame")
            # save to tmp file and load
            tmp_path = save_base64_image(img_b64)
            if tmp_path:
                probe_img = load_image_cv(tmp_path)

    if probe_img is None:
        # cleanup
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return jsonify(success=False, message="No image provided or failed to decode"), 400

    # optional time field (not used for matching, only for logging)
    time_val = None
    if request.form and request.form.get("time"):
        time_val = request.form.get("time")
    else:
        j = request.get_json(silent=True)
        if j:
            time_val = j.get("time")

    # Run DeepFace.find against IMAGES_DIR.
    try:
        # DeepFace.find expects either image path or numpy array; pass probe_img
        result = DeepFace.find(
            img_path=probe_img,
            db_path=IMAGES_DIR,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR_BACKEND,
            distance_metric=DISTANCE_METRIC,
            enforce_detection=False
        )

        matched = False
        response = {"success": False, "name": None, "roll": None, "distance": None, "message": "No face detected or no match."}

        if isinstance(result, list) and len(result) > 0 and len(result[0]) > 0:
            # best match is first row
            row = result[0].iloc[0]
            identity_path = row.get("identity") or row.get("Identity") or row.get("img") or None
            # distance column name varies by deepface version; try common names
            distance = None
            for k in ("distance", "cosine", "VGG-Face", "facenet", "cosine_similarity"):
                if k in row:
                    try:
                        distance = float(row[k])
                        break
                    except Exception:
                        continue
            # fallback: try to parse any numeric column
            if distance is None:
                for col in row.index:
                    try:
                        val = float(row[col])
                        distance = val
                        break
                    except Exception:
                        continue

            if distance is None:
                # Couldn't find numeric distance; treat as no match
                response["message"] = "No numeric distance found in DeepFace output."
            else:
                if distance <= THRESHOLD:
                    # parse name and roll
                    name, roll = parse_name_roll_from_filename(identity_path)
                    # attendance logging: only if not within last hour
                    attendance_file = attendance_filepath_for_today()
                    if not is_within_one_hour(name, attendance_file):
                        header_needed = not os.path.exists(attendance_file)
                        with open(attendance_file, "a") as af:
                            if header_needed:
                                af.write("Name,Time,Distance\n")
                            af.write(f"{name},{time_val or datetime.now().strftime('%H:%M:%S')},{distance}\n")
                        response = {"success": True, "name": name, "roll": roll, "distance": distance,
                                    "message": f"Matched: {name} (roll={roll}) distance={distance:.4f}"}
                    else:
                        response = {"success": True, "name": name, "roll": roll, "distance": distance,
                                    "message": f"Already marked within last hour: {name} (roll={roll}) with distane: {distance:.4f}"}
                else:
                    response = {"success": False, "name": None, "roll": None, "distance": distance,
                                "message": "No close match (distance too high)."}

        else:
            response = {"success": False, "message": "No face detected or no match found."}

    except Exception as e:
        response = {"success": False, "message": f"Recognition error: {str(e)}"}

    # cleanup temporary file
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    return jsonify(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5008, debug=True)
