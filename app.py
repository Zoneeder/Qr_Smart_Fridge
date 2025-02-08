from flask import *
import sqlite3
from datetime import datetime
import io
import segno
import json


app = Flask(__name__)
app.secret_key = "secret"  # Замените на свой секретный ключ

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Функции для подключения к базе данных

#######################################

def get_db_connection_users():
    conn = sqlite3.connect("database/users.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection():
    conn = sqlite3.connect("database/fridge.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection_for_shopping_list():
    connsl = sqlite3.connect('database/shopping_list.db')
    connsl.row_factory = sqlite3.Row
    return connsl

#######################################

#######################################
# Регистрация пользователя
#######################################
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm = request.form['confirm']

        # Простая проверка заполненности полей
        if not username or not email or not password or not confirm:
            flash("Все поля обязательны для заполнения", "danger")
            return render_template('register.html')

        if password != confirm:
            flash("Пароли не совпадают", "danger")
            return render_template('register.html')

        conn = get_db_connection_users()
        user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
        if user:
            flash("Пользователь с таким именем или email уже существует", "danger")
            conn.close()
            return render_template('register.html')

        # Сохраняем пароль в открытом виде (небезопасно!)
        conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, password))
        conn.commit()
        conn.close()

        flash("Регистрация прошла успешно! Теперь вы можете войти.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

#######################################
# Вход пользователя
#######################################
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username_or_email'].strip()
        password = request.form['password']

        conn = get_db_connection_users()
        # Ищем пользователя по username или email и сверяем пароль
        user = conn.execute('SELECT * FROM users WHERE (username = ? OR email = ?) AND password = ?',
                            (username_or_email, username_or_email, password)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Вы успешно вошли в систему", "success")
            return redirect(url_for('home'))
        else:
            flash("Неверное имя пользователя/Email или пароль", "danger")
            return render_template('login.html')

    return render_template('login.html')

#######################################
# Выход пользователя
#######################################
@app.route('/logout')
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for('home'))

# Маршрут для главной страницы
@app.route('/')
def home():
    # Если пользователь не аутентифицирован, можно перенаправить на страницу входа
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')

    conn = get_db_connection()
    if search_query:
        # Выбираем продукты только для текущего пользователя, которые соответствуют запросу поиска
        products = conn.execute('SELECT * FROM products WHERE user_id = ? AND name LIKE ?', (session['user_id'], f'%{search_query}%')).fetchall()
    else:
        # Выбираем все продукты для текущего пользователя
        products = conn.execute('SELECT * FROM products WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('index.html', active_page='home', products=products, search_query=search_query)


# Маршрут для страницы "Отсканировать Qr-код"
@app.route('/Qr-code', methods=['GET', 'POST'])
def qr_code():
    if request.method == 'POST':
        try:
            data = request.get_json()
            print("Полученные данные:", data)  # Лог в консоль

            conn = get_db_connection()
            conn.execute('''
                INSERT INTO products (user_id, name, type, manufacture_date, expiration_date, quantity, unit, nutritional_value, allergens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.get('user_id', -1),  # Временно ставим 1, если нет сессии
                data["name"],
                data["type"],
                data["manufacture_date"],
                data["expiration_date"],
                data["quantity"],
                data["unit"],
                data["nutritional_value"],
                data.get("allergens", "-")  # Если нет аллергенов, ставим "-"
            ))
            conn.commit()
            conn.close()
            conn = get_db_connection()
            conn.execute('''INSERT INTO analytics (user_id, data_add) VALUES (?, ?)''', (session.get('user_id', -1), datetime.now().strftime('%Y-%m-%d')))
            conn.commit()
            conn.close()

            return jsonify({"success": True, "message": "QR-код сохранен"}), 200

        except Exception as e:
            print("Ошибка при обработке запроса:", e)
            return jsonify({"success": False, "error": str(e)}), 400

    return render_template('Qr-code.html', active_page='Qr-code')

# Маршрут для страницы "Список покупок"
@app.route('/shopping_list', methods=['GET', 'POST'])
def products():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    connsl = get_db_connection_for_shopping_list()
    shopping_list = connsl.execute('SELECT * FROM shopping_list ORDER BY id DESC').fetchall()  # Получаем все продукты из базы данных
    connsl.close()
    if request.method == 'POST':
        # Получаем данные из формы
        name = request.form['name']
        amount = float(request.form['amount'])
        amount_type = request.form['amount_type']

        # Подключаемся к базе данных и добавляем продукт
        connsl = get_db_connection_for_shopping_list()
        connsl.execute('''
        INSERT INTO shopping_list (name, amount, amount_type)
        VALUES (?, ?, ?)
        ''', (name, amount, amount_type))
        connsl.commit()
        connsl.close()
        
        return redirect(url_for('products'))
    
    return render_template('shopping_list.html', active_page='shopping_list', shopping_list=shopping_list)

@app.route('/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    connsl = get_db_connection_for_shopping_list()
    connsl.execute('''DELETE FROM shopping_list WHERE id = ?''', (product_id,))
    connsl.commit()
    connsl.close()
    return redirect(url_for('products'))


@app.route('/analytics_data')
def analytics_data():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    conn = get_db_connection()
    cursor = conn.cursor()

    if start_date and end_date:
        cursor.execute("SELECT data_add, COUNT(*) FROM analytics WHERE data_add IS NOT NULL AND data_add BETWEEN ? AND ? GROUP BY data_add", (start_date, end_date))
        added = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT data_delete, COUNT(*) FROM analytics WHERE data_delete IS NOT NULL AND data_delete BETWEEN ? AND ? GROUP BY data_delete", (start_date, end_date))
        deleted = {row[0]: row[1] for row in cursor.fetchall()}
    else:
        cursor.execute("SELECT data_add, COUNT(*) FROM analytics WHERE data_add IS NOT NULL GROUP BY data_add")
        added = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute("SELECT data_delete, COUNT(*) FROM analytics WHERE data_delete IS NOT NULL GROUP BY data_delete")
        deleted = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    analytics = {}
    for date in set(added.keys()) | set(deleted.keys()):
        analytics[date] = {
            "added": added.get(date, 0),
            "deleted": deleted.get(date, 0)
        }
    return jsonify(analytics)



@app.context_processor
def inject_notifications():
    # Если пользователь не авторизован, не отображаем уведомления
    if 'user_id' not in session:
        return dict(notifications=[], notifications_count=0)
        
    dismissed = session.get('dismissed_notifications', [])
    conn = get_db_connection()
    # Выбираем продукты для текущего пользователя
    products = conn.execute('SELECT id, name, expiration_date FROM products WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()

    notifications = []
    today = datetime.today().date()
    warning_days = 3
    for product in products:
        if product['id'] in dismissed:
            continue
        exp_date = datetime.strptime(product['expiration_date'], '%Y-%m-%d').date()
        days_left = (exp_date - today).days
        if days_left <= warning_days:
            notifications.append({
                'id': product['id'],
                'message': f"{product['name']} скоро испортится! Осталось {days_left} дн."
            })
    return dict(notifications=notifications, notifications_count=len(notifications))


@app.route('/dismiss_notification/<int:product_id>', methods=['POST'])
def dismiss_notification(product_id):
    dismissed = session.get('dismissed_notifications', [])
    if product_id not in dismissed:
        dismissed.append(product_id)
        session['dismissed_notifications'] = dismissed
    return '', 204

@app.route("/delete_product_from_index/<int:product_id>", methods=['POST'])
def delete_product_from_index(product_id):
    conn = get_db_connection()
    conn.execute('''DELETE FROM products WHERE id = ?''', (product_id,))
    conn.commit()
    conn.close()
    conn = get_db_connection()
    conn.execute('''INSERT INTO analytics (user_id, data_delete) VALUES (?, ?)''', (session.get('user_id', -1), datetime.now().strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.route('/qr_image/<int:product_id>')
def qr_image(product_id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    if product is None:
        return "Продукт не найден", 404

    product_dict = dict(product)
    data = json.dumps(product_dict, ensure_ascii=False)
    # Генерируем QR-код с помощью segno
    qr_code = segno.make(data)
    # Создаем BytesIO буфер для хранения изображения
    output = io.BytesIO()
    # Сохраняем QR-код в формате PNG в буфер
    qr_code.save(output, kind='svg', scale=20)
    output.seek(0)
    # Отправляем изображение в ответ
    return send_file(output, mimetype='image/svg+xml')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', active_page='analytics')

if __name__ == '__main__':
    app.run(debug=True)