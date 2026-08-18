from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, bcrypt, limiter
from app.models.user import User, LoginAttempt
from app.auth.forms import RegisterForm, LoginForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.route("/", methods=["GET"])
def auth_page():
    if current_user.is_authenticated:
        # Check if user has any learning paths
        if current_user.learning_paths:
            return redirect(url_for("learning.dashboard"))
        return redirect(url_for("learning.new_path"))
    return render_template("auth/auth.html", login_form=LoginForm(), register_form=RegisterForm())

@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per hour")
def register():
    form = RegisterForm()
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field.capitalize()}: {error}", "error")
        return redirect(url_for("auth.auth_page"))

    # Check unique email
    email_lower = form.email.data.lower().strip()
    if User.query.filter_by(email=email_lower).first():
        flash("An account with this email already exists.", "error")
        return redirect(url_for("auth.auth_page"))

    pw_hash = bcrypt.generate_password_hash(form.password.data, rounds=12).decode("utf-8")
    user = User(email=email_lower, password_hash=pw_hash, name=form.name.data)
    
    # Initialize StudentProgress
    from app.models.student_progress import StudentProgress
    progress = StudentProgress(user=user, total_xp=0, streak_days=0, badges=[])
    
    db.session.add(user)
    db.session.add(progress)
    db.session.commit()
    
    login_user(user)
    return redirect(url_for("learning.new_path"))

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per 15 minutes", key_func=lambda: request.form.get("email", "unknown"))
def login():
    form = LoginForm()
    email_lower = (form.email.data or "").lower().strip()
    
    if not form.validate_on_submit():
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field.capitalize()}: {error}", "error")
        return redirect(url_for("auth.auth_page"))

    user = User.query.filter_by(email=email_lower).first()
    
    # Track LoginAttempt
    success = False
    if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
        success = True
        
    attempt = LoginAttempt(
        user_id=user.id if user else None,
        email=email_lower,
        success=success,
        ip=request.remote_addr
    )
    db.session.add(attempt)
    db.session.commit()

    if not success:
        flash("Invalid email or password.", "error")
        return redirect(url_for("auth.auth_page"))

    login_user(user, remember=True)
    has_path = len(user.learning_paths) > 0
    return redirect(url_for("learning.dashboard") if has_path else url_for("learning.new_path"))

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.auth_page"))
