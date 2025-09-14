from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User
from forms import RegisterForm, LoginForm
from werkzeug.security import generate_password_hash, check_password_hash
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = 'your_secret_key_here'

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# -------------------- Teacher Config --------------------
TEACHER_USERNAME = "teacher"
TEACHER_PASSWORD = "password123"
TEACHER_EMAIL = "teacher@example.com"  # replace with actual email
ATTENDANCE_FOLDER = "attendance"
os.makedirs(ATTENDANCE_FOLDER, exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------- User Routes --------------------
@app.route('/')
def home():
    return render_template('home.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        pw = form.password.data

        user = User.query.filter_by(username=username).first()
        if not user:
            flash("Invalid username", "danger")
            return render_template("login.html", form=form)

        try:
            valid = check_password_hash(user.password, pw)
        except Exception:
            valid = False

        if not valid and user.password == pw:  # legacy plaintext
            valid = True

        if not valid:
            flash("Invalid password", "danger")
            return render_template("login.html", form=form)

        login_user(user)
        flash("Logged in successfully.", "success")
        next_page = request.args.get("next")
        return redirect(next_page or url_for("home"))

    return render_template("login.html", form=form)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip().lower()

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "danger")
            return render_template("signup.html", form=form)
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("signup.html", form=form)

        hashed_pw = generate_password_hash(form.password1.data)
        new_user = User(
            username=username,
            email=email,
            phone=form.phone.data.strip(),
            college=form.college.data.strip(),
            password=hashed_pw,
            profile_pic=None
        )

        if form.profile_pic.data:
            from werkzeug.utils import secure_filename
            f = form.profile_pic.data
            filename = secure_filename(f.filename)
            upload_dir = "static/uploads"
            os.makedirs(upload_dir, exist_ok=True)
            f.save(os.path.join(upload_dir, filename))
            new_user.profile_pic = f"uploads/{filename}"

        db.session.add(new_user)
        db.session.commit()
        flash("Account created successfully! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("home"))

@app.route('/password_reset')
def password_reset():
    return render_template('password_reset.html')

@app.route("/mark_attendance", methods=["POST", "GET"])
@login_required
def mark_attendance():
    return render_template("main.html")

# -------------------- Teacher Routes --------------------
@app.route("/teacher/login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == TEACHER_USERNAME and password == TEACHER_PASSWORD:
            session["teacher_logged_in"] = True
            return redirect(url_for("teacher_dashboard"))
        else:
            flash("Invalid teacher credentials", "danger")

    return render_template("teacher_login.html")

@app.route("/teacher/dashboard")
def teacher_dashboard():
    if not session.get("teacher_logged_in"):
        return redirect(url_for("teacher_login"))
    return render_template("dashboard.html")

@app.route("/teacher/send_attendance")
def send_attendance():
    if not session.get("teacher_logged_in"):
        return redirect(url_for("teacher_login"))

    files = [f for f in os.listdir(ATTENDANCE_FOLDER) if f.endswith(".csv")]
    if not files:
        return "No attendance file found"

    latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(ATTENDANCE_FOLDER, x)))
    file_path = os.path.join(ATTENDANCE_FOLDER, latest_file)

    sender = "yourgmail@gmail.com"
    password = "your_app_password"  # use Gmail App Password
    receiver = TEACHER_EMAIL

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = receiver
    msg["Subject"] = "Attendance Report"
    msg.attach(MIMEText("Please find attached the latest attendance report.", "plain"))

    with open(file_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={latest_file}")
    msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())
        server.quit()
        return "Attendance sent successfully!"
    except Exception as e:
        return f"Error sending email: {e}"

# -------------------- Run --------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
