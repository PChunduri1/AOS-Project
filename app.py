from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from flask_mysqldb import MySQL
from flask_bcrypt import Bcrypt
import os
import psutil
import shutil
import time

app = Flask(__name__)
app.secret_key = 'f4ebd21dccf42ec8d3d8468a5a616366'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'prathyusha@12'
app.config['MYSQL_DB'] = 'nas_management'

mysql = MySQL(app)
bcrypt = Bcrypt(app)

# Upload and Backup Directories
UPLOAD_FOLDER = '/home/prathyusha/project2/uploads'
BACKUP_FOLDER = '/home/prathyusha/project2/backups'

MAX_BACKUPS = 5

# -------------------- User Management --------------------
@app.route('/')
def home():
    if 'username' in session:
        return render_template('dashboard.html', username=session['username'])
    return redirect(url_for('login'))
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']

        # Hash the password using bcrypt
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Insert the new user into the database
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            return render_template('register.html', error="Username already exists")
        
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", 
                    (username, hashed_password, role))
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('login'))  # Redirect to login after successful registration

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    
    username = request.form['username']
    password = request.form['password']

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()

    if user and bcrypt.check_password_hash(user[2], password):  # user[2] is the password_hash field
        session['username'] = username
        session['role'] = user[3]  # Assuming the role is stored in the 4th column
        return redirect(url_for('home'))
    else:
        return render_template('login.html', error="Invalid credentials")



@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/users', methods=['GET', 'POST'])
def manage_users():
    if session.get('role') != 'admin':
        return "Unauthorized", 403
    
    if request.method == 'GET':
        # Fetch users from the database
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, username, role FROM users")
        
        # Fetch the result and the description
        users = cur.fetchall()
        column_names = [desc[0] for desc in cur.description]  # Get column names from description
        
        cur.close()

        # Convert each row into a dictionary using column names
        users = [dict(zip(column_names, row)) for row in users]

        return render_template('user_management.html', users=users)
    
    elif request.method == 'POST':
        data = request.form
        username = data['username']
        password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        role = data['role']

        # Insert the new user into the database
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)", (username, password, role))
        mysql.connection.commit()
        cur.close()
        return redirect(url_for('manage_users'))
        
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('role') != 'admin':
        return "Unauthorized", 403

    # Perform the deletion using the user_id
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    mysql.connection.commit()
    cur.close()

    return redirect(url_for('manage_users'))



# -------------------- File Management --------------------
@app.route('/files', methods=['GET', 'POST', 'DELETE'])
def file_management():
    if request.method == 'GET':
        files = os.listdir(UPLOAD_FOLDER)
        return render_template('file_management.html', files=files)
    
    elif request.method == 'POST':
        if '_method' in request.form and request.form['_method'] == 'DELETE':
            # Handle file deletion
            file_name = request.form['file_name']
            os.remove(os.path.join(UPLOAD_FOLDER, file_name))
            return redirect(url_for('file_management'))
        
        # Handle file upload
        file = request.files['file']
        file.save(os.path.join(UPLOAD_FOLDER, file.filename))
        return redirect(url_for('file_management'))


# -------------------- System Monitoring --------------------
@app.route('/monitor')
def system_monitoring():
    cpu_usage = psutil.cpu_percent(interval=1)
    disk_usage = psutil.disk_usage('/').percent
    memory_usage = psutil.virtual_memory().percent  # Get memory usage percentage

    return render_template('system_monitoring.html', cpu_usage=cpu_usage, disk_usage=disk_usage, memory_usage=memory_usage)


# -------------------- Backup and Restore --------------------
def cleanup_backups():
    # List all backups in the backup folder
    backups = os.listdir(BACKUP_FOLDER)
    backups.sort()  # Sort backups by name (which includes timestamps)

    # If there are more than the allowed number of backups, delete the oldest ones
    if len(backups) > MAX_BACKUPS:
        for backup in backups[:-MAX_BACKUPS]:
            backup_path = os.path.join(BACKUP_FOLDER, backup)
            os.remove(backup_path)  # Remove the old backup file

@app.route('/backup', methods=['GET', 'POST'])
def backup_restore():
    if request.method == 'GET':
        # List all backup files in the backup folder
        backups = os.listdir(BACKUP_FOLDER)
        return render_template('backup_restore.html', backups=backups)
    
    elif request.method == 'POST':
        # Create a new backup by zipping the UPLOAD_FOLDER contents
        timestamp = int(time.time())
        backup_file = os.path.join(BACKUP_FOLDER, f"backup_{timestamp}.zip")
        shutil.make_archive(backup_file.replace('.zip', ''), 'zip', UPLOAD_FOLDER)

        # Clean up old backups if the number exceeds the limit
        cleanup_backups()

        return redirect(url_for('backup_restore'))

@app.route('/download_backup/<string:backup_name>', methods=['GET'])
def download_backup(backup_name):
    # Send the requested backup file for download
    return send_from_directory(BACKUP_FOLDER, backup_name)

@app.route('/restore_backup/<string:backup_name>', methods=['POST'])
def restore_backup(backup_name):
    # Path to the backup file
    backup_file_path = os.path.join(BACKUP_FOLDER, backup_name)

    if os.path.exists(backup_file_path):
        # Extract the backup zip file to the upload folder
        shutil.unpack_archive(backup_file_path, UPLOAD_FOLDER)
        return redirect(url_for('backup_restore'))
    else:
        return "Backup file not found", 404


# Run the app
if __name__ == '__main__':
    app.run(debug=True)

