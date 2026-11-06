import random
import string
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__, static_folder='font', static_url_path='/font')
app.secret_key = 'your_super_secret_key_here_change_it'

EMAIL = "qiq4077@gmail.com"
PASSWORD = "actbadwtnbomblnl"

otp_storage = {} 

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # جدول المستخدمين (محدث ليشمل الأفاتار والسيرة الذاتية)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT NOT NULL,
            avatar TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            balance INTEGER DEFAULT 0,
            is_exempt INTEGER DEFAULT 0,
            device_info TEXT DEFAULT 'غير معروف',
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول حفظ الجلسات لكل شخص داخل قاعدة البيانات (Database Sessions)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_sessions (
            session_token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # جدول الأكواد
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            package_value INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,
            times_used INTEGER DEFAULT 0,
            is_used INTEGER DEFAULT 0
        )
    ''')

    # جدول تتبع الزوار
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS site_visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_or_session TEXT UNIQUE NOT NULL,
            last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # تدارك النقص في الأعمدة القديمة للمستخدمين
    for col, definition in [
        ("avatar", "TEXT DEFAULT ''"),
        ("bio", "TEXT DEFAULT ''"),
        ("balance", "INTEGER DEFAULT 0"),
        ("is_exempt", "INTEGER DEFAULT 0"),
        ("device_info", "TEXT DEFAULT 'غير معروف'"),
        ("last_active", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass

    # تدارك النقص في أعمدة الأكواد
    for col, definition in [
        ("max_uses", "INTEGER DEFAULT 1"),
        ("times_used", "INTEGER DEFAULT 0")
    ]:
        try:
            cursor.execute(f"ALTER TABLE promo_codes ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass
    
    # إدراج الأكواد الافتراضية
    default_codes = [
        ("ali", 1, 1),
        ("mahdi", 1, 1),
        ("kkos", 5, 5),
        ("boos", 10, 10),
        ("iop", 20, 20)
    ]
    
    for code, val, max_u in default_codes:
        cursor.execute("SELECT id FROM promo_codes WHERE code = ?", (code,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO promo_codes (code, package_value, max_uses, times_used, is_used) VALUES (?, ?, ?, 0, 0)", (code, val, max_u))

    conn.commit()
    conn.close()

init_db()

def send_email_message(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

def parse_device_info(user_agent_string):
    ua = user_agent_string
    device = "جهاز غير معروف"
    
    if "Tekno" in ua or "TEKNO" in ua:
        device = "Tecno Pova 5" if "Pova 5" in ua else "Tecno Device"
    elif "iPhone" in ua or "CPU OS" in ua:
        device = "iPhone (آبل)"
    elif "iPad" in ua:
        device = "iPad (آبل)"
    elif "Samsung" in ua or "SM-" in ua:
        device = "Samsung Galaxy"
    elif "Xiaomi" in ua or "Redmi" in ua or "POCO" in ua:
        device = "Xiaomi / Redmi"
    elif "Android" in ua:
        device = "هاتف Android عام"
    elif "Windows" in ua:
        device = "كمبيوتر (Windows)"
    elif "Macintosh" in ua or "Mac OS" in ua:
        device = "حاسوب (Mac)"

    browser = ""
    if "Chrome" in ua and "Edg" not in ua and "OPR" not in ua:
        browser = "متصفح Chrome"
    elif "Safari" in ua and "Chrome" not in ua:
        browser = "متصفح Safari"
    elif "Edg" in ua:
        browser = "متصفح Edge"
    elif "Firefox" in ua:
        browser = "متصفح Firefox"

    return f"{device} ({browser})" if browser else device

# دالة لجلب الـ user_id الحقيقي المرتبط بجلسة هذا المتصفح من قاعدة البيانات مباشرة
def get_current_user_id():
    token = session.get('session_token')
    if not token:
        return None
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM user_sessions WHERE session_token = ?", (token,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

@app.before_request
def track_visitor_and_activity():
    identifier = request.remote_addr
    if identifier:
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO site_visitors (ip_or_session, last_visit) 
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(ip_or_session) DO UPDATE SET last_visit = CURRENT_TIMESTAMP
            ''', (identifier,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    user_id = get_current_user_id()
    if user_id:
        user_agent = request.headers.get('User-Agent', 'غير معروف')
        device_formatted = parse_device_info(user_agent)
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET last_active = CURRENT_TIMESTAMP, device_info = ? 
                WHERE id = ?
            ''', (device_formatted, user_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

@app.route('/')
def home():
    user_id = get_current_user_id()
    is_logged_in = bool(user_id)
    return render_template('index.html', is_logged_in=is_logged_in)

@app.route('/alkoa3d')
def alkoa3d(): return render_template('8oa3d.html')
@app.route('/story')
def story(): return render_template('story.html')
@app.route('/faq')
def faq(): return render_template('faq.html')
@app.route('/contact')
def contact(): return render_template('contact.html')
@app.route('/df3as3ar')
def df3as3ar(): return render_template('df3as3ar.html')
@app.route('/terms')
def terms(): return render_template('terms.html')
@app.route('/privacy')
def privacy(): return render_template('privacy.html')
@app.route('/login')
def login(): return render_template('login.html')

@app.route('/api/get-user-profile')
def api_get_user_profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({}), 401
    
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT name, email, phone, avatar, bio FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({}), 404
        
    return jsonify({
        'name': user['name'],
        'email': user['email'],
        'phone': user['phone'],
        'avatar': user['avatar'] if user['avatar'] else 'https://files.catbox.moe/0rnwon.jpg',
        'bio': user['bio']
    })

@app.route('/api/update-profile', methods=['POST'])
def api_update_profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'success': False}), 401
        
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    bio = data.get('bio')
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET name = ?, email = ?, phone = ?, bio = ?
        WHERE id = ?
    """, (name, email, phone, bio, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/delete-account')
def delete_account():
    user_id = get_current_user_id()
    if not user_id:
        return redirect('/')
        
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # 1. حذف جلسة المستخدم من جدول الجلسات أولاً
        cursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        
        # 2. حذف المستخدم من جدول users
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"حدث خطأ أثناء حذف الحساب: {e}")
    
    # التوجيه للصفحة الرئيسية بعد الحذف
    return redirect('/')


@app.route('/profile')
def profile():
    if not get_current_user_id(): 
        return redirect(url_for('login'))
    return render_template('profile.html')

@app.route('/logout')
def logout():
    token = session.get('session_token')
    if token:
        try:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_sessions WHERE session_token = ?", (token,))
            conn.commit()
            conn.close()
        except Exception:
            pass
    session.pop('session_token', None)
    return redirect(url_for('home'))

@app.route('/community')
def community(): return render_template('community.html')
@app.route('/admin')
def admin_dashboard(): return render_template('admin.html')

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_registered = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM site_visitors')
        total_unregistered = cursor.fetchone()[0]

        active_threshold = (datetime.now() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('SELECT COUNT(*) FROM users WHERE last_active >= ?', (active_threshold,))
        active_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM users WHERE last_active < ?', (active_threshold,))
        inactive_users = cursor.fetchone()[0]

        cursor.execute('SELECT device_info, COUNT(*) as cnt FROM users GROUP BY device_info ORDER BY cnt DESC LIMIT 10')
        top_devices = [{'device': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        cursor.execute('SELECT id, name, email, phone, balance, device_info, last_active FROM users')
        users_list = [{
            'id': row[0], 'name': row[1], 'email': row[2], 'phone': row[3],
            'balance': row[4], 'device_info': row[5], 'last_active': row[6]
        } for row in cursor.fetchall()]

        cursor.execute('SELECT id, code, package_value, max_uses, times_used, is_used FROM promo_codes')
        codes_list = [{
            'id': row[0], 'code': row[1], 'package_value': row[2],
            'max_uses': row[3], 'times_used': row[4], 'is_used': row[5]
        } for row in cursor.fetchall()]
            
        conn.close()
        return jsonify({
            'status': 'success',
            'total_users': total_registered,
            'stats': {
                'registered': total_registered, 'unregistered': total_unregistered,
                'active': active_users, 'inactive': inactive_users, 'top_devices': top_devices
            },
            'users': users_list,
            'codes': codes_list
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/admin/create-code', methods=['POST'])
def admin_create_code():
    try:
        data = request.get_json() or {}
        code = data.get('code', '').strip().lower()
        package_value = data.get('package_value')
        max_uses = data.get('max_uses', 1)
        
        if not code or not package_value:
            return jsonify({'success': False, 'message': 'يرجى إدخال الكود وقيمة الألعاب'})
            
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM promo_codes WHERE code = ?', (code,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'هذا الكود موجود مسبقاً!'})
            
        cursor.execute('INSERT INTO promo_codes (code, package_value, max_uses, times_used, is_used) VALUES (?, ?, ?, 0, 0)', (code, int(package_value), int(max_uses)))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'تم إنشاء الكود بنجاح'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/delete-code', methods=['POST'])
def admin_delete_code():
    try:
        data = request.get_json() or {}
        code_id = data.get('id')
        if not code_id: return jsonify({'success': False, 'message': 'معرف الكود مطلوب'})
            
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM promo_codes WHERE id = ?', (code_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'تم حذف الكود بنجاح'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/update-balance', methods=['POST'])
def admin_update_balance():
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        amount = int(data.get('amount', 0))
        action = data.get('action')

        if not user_id or amount <= 0:
            return jsonify({'success': False, 'message': 'يرجى اختيار المستخدم وإدخال مبلغ صحيح'})

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        if action == 'add':
            cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, user_id))
        elif action == 'deduct':
            cursor.execute('UPDATE users SET balance = MAX(0, balance - ?) WHERE id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'تم تحديث رصيد المستخدم بنجاح'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json() or {}
        name, email, password, phone = data.get('name'), data.get('email'), data.get('password'), data.get('phone')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'message': 'البريد الإلكتروني مستخدم بالفعل!'})

        cursor.execute('INSERT INTO users (name, email, password, phone, balance, is_exempt) VALUES (?, ?, ?, ?, 0, 0)', (name, email, password, phone))
        conn.commit()
        
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        user_id = cursor.fetchone()[0]
        
        # إنشاء جلسة جديدة وحفظها بقاعدة البيانات
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        cursor.execute('INSERT INTO user_sessions (session_token, user_id) VALUES (?, ?)', (session_token, user_id))
        conn.commit()
        conn.close()
        
        session['session_token'] = session_token
        return jsonify({'success': True, 'message': 'تم إنشاء الحساب وتسجيل الدخول بنجاح'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ غير متوقع'})

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json() or {}
        identifier, password = data.get('identifier'), data.get('password')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, password FROM users WHERE email = ?', (identifier,))
        user = cursor.fetchone()
        
        if not user or user[1] != password:
            conn.close()
            return jsonify({'success': False, 'message': 'البريد الإلكتروني أو كلمة المرور غير صحيحة'})
        
        user_id = user[0]
        session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        
        # حفظ السيشن في قاعدة البيانات
        cursor.execute('INSERT OR REPLACE INTO user_sessions (session_token, user_id) VALUES (?, ?)', (session_token, user_id))
        conn.commit()
        conn.close()
        
        session['session_token'] = session_token
        return jsonify({'success': True, 'message': 'تم تسجيل الدخول بنجاح'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ في تسجيل الدخول'})

@app.route('/api/send-otp', methods=['POST'])
def api_send_otp():
    try:
        data = request.get_json() or {}
        email = data.get('email')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        if not user: return jsonify({'success': False, 'message': 'البريد الإلكتروني غير مسجل معنا'})
        code = ''.join(random.choices(string.digits, k=6))
        otp_storage[email] = code
        if send_email_message(email, "رمز التحقق لدخول منصة اسبقهم", f"رمز التحقق الخاص بك هو: {code}"):
            return jsonify({'success': True, 'message': 'تم إرسال كود التحقق بنجاح'})
        return jsonify({'success': False, 'message': 'فشل إرسال الإيميل'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ'})

@app.route('/api/verify-otp', methods=['POST'])
def api_verify_otp():
    try:
        data = request.get_json() or {}
        email, code = data.get('email'), data.get('code')
        if email in otp_storage and otp_storage[email] == code:
            del otp_storage[email]
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            
            if user:
                user_id = user[0]
                session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
                cursor.execute('INSERT OR REPLACE INTO user_sessions (session_token, user_id) VALUES (?, ?)', (session_token, user_id))
                conn.commit()
                session['session_token'] = session_token
            
            conn.close()
            return jsonify({'success': True, 'message': 'تم التحقق بنجاح'})
        return jsonify({'success': False, 'message': 'كود التحقق غير صحيح'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ'})

@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    try:
        data = request.get_json() or {}
        email = data.get('email')
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()
        if not user: return jsonify({'success': False, 'message': 'البريد الإلكتروني غير مسجل'})
        code = ''.join(random.choices(string.digits, k=6))
        otp_storage[email] = code
        send_email_message(email, "استعادة كلمة المرور", f"رمز التحقق الخاص بك: {code}")
        return jsonify({'success': True, 'message': 'تم إرسال الكود'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ'})

@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    try:
        data = request.get_json() or {}
        email, code, new_password = data.get('email'), data.get('code'), data.get('newPassword')
        if email in otp_storage and otp_storage[email] == code:
            conn = sqlite3.connect('database.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET password = ? WHERE email = ?', (new_password, email))
            conn.commit()
            conn.close()
            del otp_storage[email]
            return jsonify({'success': True, 'message': 'تم تحديث كلمة المرور بنجاح'})
        return jsonify({'success': False, 'message': 'رمز التحقق غير صحيح'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'حدث خطأ'})

@app.route('/api/send-email', methods=['POST'])
def send_email():
    try:
        data = request.get_json()
        name = data.get('name')
        sender_email = data.get('email')
        phone = data.get('phone')
        subject = data.get('subject')
        message = data.get('message')
        recipient = data.get('recipient', EMAIL)

        email_content = f"""
        - الاسـم : {name}
        - البريد الإلكتـروني : {sender_email}
        - رقـم الجـوال : {phone}
        - المـوضوع : {subject}
        
        الرسـالة :
        {message}
        """

        if send_email_message(recipient, f"{subject}", email_content):
            return jsonify({'success': True, 'message': 'تم إرسال الرسالة بنجاح'})
        else:
            return jsonify({'success': False, 'message': 'حدث خطأ أثناء الإرسال عبر السيرفر'})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء الإرسال'})

@app.route('/api/get-user-balance', methods=['GET'])
def get_user_balance():
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'status': 'success', 'balance': 0})
            
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        return jsonify({'status': 'success', 'balance': row[0] if row else 0})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/check-exempt-status', methods=['GET'])
def check_exempt_status():
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'status': 'success', 'is_exempt': False})
            
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT is_exempt FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return jsonify({'status': 'success', 'is_exempt': bool(row[0]) if row and row[0] is not None else False})
    except Exception as e:
        return jsonify({'status': 'error', 'is_exempt': False}), 500

# --- شحن الرصيد باستخدام السيشن المحفوظ بقاعدة البيانات ---
@app.route('/api/verify-and-add-package', methods=['POST'])
def verify_and_add_package():
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'status': 'error', 'message': 'عذراً، يجب تسجيل الدخول أولاً لتتمكن من شحن الرصيد!'})
            
        data = request.get_json() or {}
        code = data.get('code', '').strip().lower()
        
        if not code:
            return jsonify({'status': 'error', 'message': 'يرجى إدخال الكود'})
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        
        # 1. التحقق من الكود
        cursor.execute('SELECT id, package_value, max_uses, times_used, is_used FROM promo_codes WHERE LOWER(code) = ?', (code,))
        promo = cursor.fetchone()
        
        if not promo:
            conn.close()
            return jsonify({'status': 'error', 'message': 'الكود غير صحيح أو غير موجود في قاعدة البيانات.'})
            
        promo_id, pkg_val, max_uses, times_used, is_used = promo
        
        if times_used >= max_uses or is_used:
            conn.close()
            return jsonify({'status': 'error', 'message': 'هذا الكود مستخدم بالكامل أو انتهت صلاحيته!'})
        
        # 2. تحديث الكود وزيادة الرصيد حصراً للمستخدم الذي يمتلك هذا السيشن في قاعدة البيانات
        new_times_used = times_used + 1
        new_is_used = 1 if new_times_used >= max_uses else 0
        
        cursor.execute('UPDATE promo_codes SET times_used = ?, is_used = ? WHERE id = ?', (new_times_used, new_is_used, promo_id))
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (pkg_val, user_id))
        conn.commit()
        
        # جلب الرصيد الجديد للمستخدم لتأكيده
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        updated_balance = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'success', 
            'message': f'تمت إضافة الباقة بنجاح! تم شحن {pkg_val} برصيدك، وأصبح رصيدك الحالي ({updated_balance}).'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
