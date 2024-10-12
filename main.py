import os
from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(24)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chatrooms.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(6), unique=True, nullable=False)
    members = db.Column(db.Integer, default=0)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)

    user = db.relationship('User', backref=db.backref('messages', lazy=True))
    room = db.relationship('Room', backref=db.backref('messages', lazy=True))

class UserRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    last_visited = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('rooms', lazy='dynamic'))
    room = db.relationship('Room', backref=db.backref('users', lazy='dynamic'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_unique_code(length):
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        if not Room.query.filter_by(code=code).first():
            break
    return code

@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    if request.method == "POST":
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.")

        room = Room.query.filter_by(code=code).first()
        if create != False:
            room = Room(code=generate_unique_code(6))
            db.session.add(room)
            db.session.commit()
        elif not room:
            return render_template("home.html", error="Room does not exist.")

        session["room"] = room.code
        return redirect(url_for("room", code=room.code))

    user_rooms = UserRoom.query.filter_by(user_id=current_user.id).order_by(UserRoom.last_visited.desc()).all()
    return render_template("home.html", user_rooms=user_rooms)

@app.route("/room/<code>")
@login_required
def room(code):
    room = Room.query.filter_by(code=code).first()
    if room is None:
        return redirect(url_for("home"))
    session["room"] = code
    messages = Message.query.filter_by(room_id=room.id).order_by(Message.timestamp).all()
    return render_template("room.html", code=code, messages=messages, username=current_user.username)

# @app.route("/", methods=["GET", "POST"])
# @login_required
# def home():
#     if request.method == "POST":
#         code = request.form.get("code")
#         join = request.form.get("join", False)
#         create = request.form.get("create", False)

#         if join != False and not code:
#             return render_template("home.html", error="Please enter a room code.")

#         room = Room.query.filter_by(code=code).first()
#         if create != False:
#             room = Room(code=generate_unique_code(6))
#             db.session.add(room)
#             db.session.commit()
#         elif not room:
#             return render_template("home.html", error="Room does not exist.")

#         session["room"] = room.code
#         return redirect(url_for("room"))

#     # Fetch user's chat history
#     user_rooms = UserRoom.query.filter_by(user_id=current_user.id).order_by(UserRoom.last_visited.desc()).all()
#     return render_template("home.html", user_rooms=user_rooms)


# @app.route("/room/<code>")
# @login_required
# def room(code):
#     room = Room.query.filter_by(code=code).first()
#     if room is None:
#         return redirect(url_for("home"))
    
#     # Update or create UserRoom entry
#     user_room = UserRoom.query.filter_by(user_id=current_user.id, room_id=room.id).first()
#     if user_room:
#         user_room.last_visited = datetime.utcnow()
#     else:
#         user_room = UserRoom(user_id=current_user.id, room_id=room.id)
#         db.session.add(user_room)
#     db.session.commit()
    
#     session["room"] = code  # Set the room in the session
#     messages = Message.query.filter_by(room_id=room.id).order_by(Message.timestamp).all()
#     return render_template("room.html", code=code, messages=messages, username=current_user.username)
# @app.route("/room")
# @login_required
# def room():
#     room_code = session.get("room")
#     room = Room.query.filter_by(code=room_code).first()
#     if room is None:
#         return redirect(url_for("home"))
#     messages = Message.query.filter_by(room_id=room.id).order_by(Message.timestamp).all()
#     return render_template("room.html", code=room.code, messages=messages, username=current_user.username)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            return render_template('signup.html', error="Passwords do not match")

        if User.query.filter_by(username=username).first():
            return render_template('signup.html', error="Username already exists")

        new_user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash('Signup successful! Welcome to Chat Rooms.')
        return redirect(url_for('home'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Logged in successfully.')
            return redirect(url_for('home'))
        return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on("message")
def message(data):
    room_code = session.get("room")
    room = Room.query.filter_by(code=room_code).first()
    if not room:
        return

    content = data.get("data")
    new_message = Message(content=content, user_id=current_user.id, room_id=room.id)
    db.session.add(new_message)
    db.session.commit()

    send_data = {
        "name": current_user.username,
        "message": content,
        "timestamp": new_message.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }
    send(send_data, to=room_code)
    print(f"{current_user.username} said: {content}")

@socketio.on("connect")
def connect(auth):
    room_code = session.get("room")
    if not room_code:
        return
    room = Room.query.filter_by(code=room_code).first()
    if not room:
        leave_room(room_code)
        return

    join_room(room_code)
    send({"name": current_user.username, "message": "has entered the room"}, to=room_code)
    room.members += 1

    # Add or update UserRoom entry
    user_room = UserRoom.query.filter_by(user_id=current_user.id, room_id=room.id).first()
    if user_room:
        user_room.last_visited = datetime.utcnow()
    else:
        user_room = UserRoom(user_id=current_user.id, room_id=room.id)
        db.session.add(user_room)

    db.session.commit()
    print(f"{current_user.username} joined room {room_code}")

@socketio.on("disconnect")
def disconnect():
    room_code = session.get("room")
    if not room_code:
        print("No room code in session")
        return

    if not current_user.is_authenticated:
        print("Anonymous or no user disconnected")
        return

    room = Room.query.filter_by(code=room_code).first()
    leave_room(room_code)

    if room:
        room.members -= 1
        if room.members <= 0:
            db.session.delete(room)
        db.session.commit()

        send_data = {"name": current_user.username, "message": "has left the room"}
        send(send_data, to=room_code)
        print(f"{current_user.username} has left the room {room_code}")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create database tables
    socketio.run(app, debug=True)