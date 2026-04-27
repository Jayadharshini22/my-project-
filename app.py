from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
import MySQLdb.cursors
import re
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import threading

app = Flask(__name__)
app.secret_key = 'womens_safety_secret_key'

# ---------------- DATABASE CONFIG ---------------- #

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'womens_safety'

mysql = MySQL(app)

# ---------------- MAIL CONFIG ---------------- #

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'jeyadharshini707@gmail.com'

# ⚠️ USE ENV VARIABLE (IMPORTANT)
app.config['MAIL_PASSWORD'] = 'prgmtjhhnkogcisx'

mail = Mail(app)

# ---------------- FILE UPLOAD ---------------- #

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------- HELPER ---------------- #

def is_logged_in():
    return 'user_id' in session

# 🔥 Async mail sending (fast)
def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_emergency_email(to_email, location, lat, lng):
    try:
        user_name = session.get('full_name', 'User')

        msg = Message(
            '🚨 EMERGENCY ALERT - SheSafe',
            sender=app.config['MAIL_USERNAME'],
            recipients=[to_email]
        )

        msg.body = f"""
🚨 EMERGENCY ALERT 🚨

User: {user_name} is in danger!

📍 Location: {location}
🗺️ https://www.google.com/maps?q={lat},{lng}

Please respond immediately!
        """

        threading.Thread(target=send_async_email, args=(app, msg)).start()
        print(f"Email triggered to {to_email}")

    except Exception as e:
        print(f"Email Error: {e}")

# ---------------- HOME ---------------- #

@app.route('/')
def index():
    return redirect(url_for('dashboard')) if is_logged_in() else redirect(url_for('login'))

# ---------------- AUTH ---------------- #

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            session['is_admin'] = user.get('is_admin', 0)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password'].strip()

        if not full_name or not phone or not email or not password:
            flash('Please fill all fields', 'danger')
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email format', 'danger')
        else:
            hashed_password = generate_password_hash(password)

            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            if cursor.fetchone():
                flash('Account already exists!', 'danger')
            else:
                cursor.execute(
                    'INSERT INTO users (full_name, phone, email, password) VALUES (%s, %s, %s, %s)',
                    (full_name, phone, email, hashed_password)
                )
                mysql.connection.commit()
                flash('Registered successfully!', 'success')
                return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# ---------------- DASHBOARD ---------------- #

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# ---------------- CONTACTS ---------------- #

@app.route('/contacts', methods=['GET', 'POST'])
def contacts():
    if not is_logged_in():
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        name = request.form['contact_name']
        phone = request.form['contact_phone']
        email = request.form.get('contact_email', '').strip()

        cursor.execute(
            'INSERT INTO contacts (user_id, contact_name, contact_phone, contact_email) VALUES (%s, %s, %s, %s)',
            (session['user_id'], name, phone, email)
        )
        mysql.connection.commit()
        flash('Contact added successfully!', 'success')

    cursor.execute('SELECT * FROM contacts WHERE user_id = %s', (session['user_id'],))
    contact_list = cursor.fetchall()

    return render_template('contacts.html', contacts=contact_list)

@app.route('/delete_contact/<int:id>')
def delete_contact(id):
    if not is_logged_in():
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(
        'DELETE FROM contacts WHERE id = %s AND user_id = %s',
        (id, session['user_id'])
    )
    mysql.connection.commit()
    flash('Contact deleted.', 'info')

    return redirect(url_for('contacts'))

# ---------------- SOS ---------------- #

@app.route('/sos', methods=['POST'])
def sos():
    if not is_logged_in():
        return jsonify({'status': 'error'}), 401

    data = request.get_json()

    lat = data.get('latitude')
    lng = data.get('longitude')
    address = data.get('address', 'Unknown location')

    # ✅ validation
    if not lat or not lng:
        return jsonify({'status': 'error', 'message': 'Location missing'}), 400

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(
        'INSERT INTO alerts (user_id, latitude, longitude, address) VALUES (%s, %s, %s, %s)',
        (session['user_id'], lat, lng, address)
    )
    alert_id = cursor.lastrowid
    mysql.connection.commit()

    # 🔥 send mails
    cursor.execute('SELECT contact_email FROM contacts WHERE user_id = %s', (session['user_id'],))
    contacts = cursor.fetchall()

    for contact in contacts:
        if contact['contact_email'] and contact['contact_email'].strip():
            send_emergency_email(contact['contact_email'], address, lat, lng)

    return jsonify({
        'status': 'success',
        'alert_id': alert_id,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

# ---------------- EVIDENCE ---------------- #

@app.route('/evidence', methods=['GET', 'POST'])
def evidence():
    if not is_logged_in():
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files.get('media')
        file_type = request.form.get('type')
        duration = request.form.get('duration', 0)

        if file:
            filename = f"{session['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            cursor.execute(
                'INSERT INTO evidence (user_id, file_path, file_type, duration) VALUES (%s, %s, %s, %s)',
                (session['user_id'], filename, file_type, duration)
            )
            mysql.connection.commit()

            return jsonify({'status': 'success'})

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(
        'SELECT * FROM evidence WHERE user_id = %s ORDER BY timestamp DESC',
        (session['user_id'],)
    )
    evidence_list = cursor.fetchall()

    return render_template('evidence.html', evidence_list=evidence_list)

# ---------------- POLICE ---------------- #

@app.route('/police')
def police():
    if not is_logged_in():
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM police_stations')
    stations = cursor.fetchall()

    return render_template('police.html', stations=stations)

# ---------------- HISTORY ---------------- #

@app.route('/history')
def history():
    if not is_logged_in():
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(
        'SELECT * FROM alerts WHERE user_id = %s ORDER BY timestamp DESC',
        (session['user_id'],)
    )
    alerts = cursor.fetchall()

    return render_template('history.html', alerts=alerts)

# ---------------- RUN ---------------- #

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
