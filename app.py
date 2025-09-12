from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User
from forms import RegisterForm, LoginForm
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = 'your_secret_key_here'

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
            app.logger.debug("Login failed: username not found: %s", username)
            flash("Invalid username", "danger")
            return render_template("login.html", form=form)

        # Preferred: check hashed password
        try:
            valid = check_password_hash(user.password, pw)
        except Exception as e:
            app.logger.debug("check_password_hash error: %s", e)
            valid = False

        # Fallback for legacy plaintext passwords (only keep during migration)
        if not valid and user.password == pw:
            app.logger.warning("Legacy plaintext password used for user %s — migrate to hashed.", user.username)
            valid = True

        if not valid:
            flash("Invalid password", "danger")
            return render_template("login.html", form=form)

        # Successful login
        login_user(user)
        flash("Logged in successfully.", "success")

        # redirect to next or home
        next_page = request.args.get("next")
        return redirect(next_page or url_for("home"))

    # If POST but not validate_on_submit, show validation errors (including CSRF)
    if request.method == "POST" and not form.validate_on_submit():
        for field_name, errors in form.errors.items():
            for err in errors:
                flash(f"{getattr(form, field_name).label.text}: {err}", "danger")

    return render_template("login.html", form=form)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = RegisterForm()
    if form.validate_on_submit():
        # normalize fields
        username = form.username.data.strip()
        email = form.email.data.strip().lower()

        # check existing user
        if User.query.filter_by(username=username).first():
            flash("Username already exists. Choose a different one.", "danger")
            return render_template("signup.html", form=form)
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Use a different one.", "danger")
            return render_template("signup.html", form=form)

        # hash password (use password1 field name you used in your form)
        hashed_pw = generate_password_hash(form.password1.data)

        new_user = User(
            username=username,
            email=email,
            phone=form.phone.data.strip(),
            college=form.college.data.strip(),
            password=hashed_pw,
            profile_pic=None  # handle file saving below if you want
        )

        # save profile pic if provided
        if form.profile_pic.data:
            from werkzeug.utils import secure_filename
            f = form.profile_pic.data
            filename = secure_filename(f.filename)
            # ensure you have a folder 'static/uploads' and it exists
            f.save(f"static/uploads/{filename}")
            new_user.profile_pic = f"uploads/{filename}"

        db.session.add(new_user)
        db.session.commit()
        flash("Account created successfully! Please login.", "success")
        return redirect(url_for("login"))

    # if GET or invalid POST -> render template with form and any errors shown below
    return render_template("signup.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()  # Logs out the current user
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("home"))  # Redirect to home page

@app.route('/password_reset')
def password_reset():
    return render_template('password_reset.html')

@app.route("/mark_attendance", methods=["POST", "GET"])
@login_required
def mark_attendance():
    return render_template("main.html")

   
    

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
