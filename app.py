from flask import *
import sqlite3
from datetime import datetime
import io
import segno
import json
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret"


# Фильтр шаблона для определения статуса срока годности продукта
@app.template_filter('expiration_status')
def expiration_status(exp_date_str):
    exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
    today = datetime.today().date()
    if exp_date < today:
        return "просрочен"
    elif (exp_date - today).days <= 3:
        return "истекает срок"
    else:
        return "годен"


# Добавление заголовков для запрета кэша у браузера
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# Функция для получения соединения с базой данных
def get_db_connection():
    conn = sqlite3.connect("database/fridge.db")
    conn.row_factory = sqlite3.Row
    return conn


# Регистрация нового пользователя
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm = request.form['confirm']

        # Проверка заполненности всех полей
        if not username or not email or not password or not confirm:
            flash("Все поля обязательны для заполнения", "danger")
            return render_template('register.html')

        # Проверка совпадения паролей
        if password != confirm:
            flash("Пароли не совпадают", "danger")
            return render_template('register.html')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()
        if user:
            flash("Пользователь с таким именем или email уже существует", "danger")
            conn.close()
            return render_template('register.html')

        hashed_password = generate_password_hash(password)

        conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, hashed_password))
        conn.commit()
        conn.close()

        flash("Регистрация прошла успешно! Теперь вы можете войти.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


# Авторизация пользователя
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username_or_email'].strip()
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', 
                            (username_or_email, username_or_email)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Вы успешно вошли в систему", "success")
            return redirect(url_for('home'))
        else:
            flash("Неверное имя пользователя/Email или пароль", "danger")
            return render_template('login.html')

    return render_template('login.html')


# Выход пользователя из системы
@app.route('/logout')
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for('home'))


# Главная страница с отображением продуктов конкретного пользователя
@app.route('/')
def home():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')
    conn = get_db_connection()
    if search_query:
        # Поиск продуктов по имени или типу с учетом user_id
        products = conn.execute('''
            SELECT * FROM products 
            WHERE user_id = ? AND (name LIKE ? OR type LIKE ?)
        ''', (session['user_id'], f'%{search_query.lower()}%', f'%{search_query.lower()}%')).fetchall()
    else:
        products = conn.execute('SELECT * FROM products WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('index.html', active_page='home', products=products, search_query=search_query)


# Обработка QR-кода: добавление продукта и запись в аналитику
@app.route('/Qr-code', methods=['GET', 'POST'])
def qr_code():
    if request.method == 'POST':
        try:
            data = request.get_json()
            print("Полученные данные:", data)

            conn = get_db_connection()
            # Вставка нового продукта с привязкой к user_id
            conn.execute('''
                INSERT INTO products (user_id, name, type, manufacture_date, expiration_date, quantity, unit, nutritional_value, allergens)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.get('user_id', -1),
                data["name"],
                data["type"],
                data["manufacture_date"],
                data["expiration_date"],
                data["quantity"],
                data["unit"],
                data["nutritional_value"],
                data.get("allergens", "-")
            ))
            conn.commit()
            conn.close()
            
            conn = get_db_connection()
            # Запись события добавления в аналитику
            conn.execute('''INSERT INTO analytics (user_id, data_add) VALUES (?, ?)''', (session.get('user_id', -1), datetime.now().strftime('%Y-%m-%d')))
            conn.commit()
            conn.close()

            return jsonify({"success": True, "message": "QR-код сохранен"}), 200

        except Exception as e:
            print("Ошибка при обработке запроса:", e)
            return jsonify({"success": False, "error": str(e)}), 400

    return render_template('Qr-code.html', active_page='Qr-code')


# Страница со списком покупок
@app.route('/shopping_list', methods=['GET', 'POST'])
def shopping_list():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    
    if request.method == 'GET':
        shopping_list = conn.execute(
            'SELECT * FROM shopping_list WHERE user_id = ? ORDER BY id DESC',
            (session['user_id'],)
        ).fetchall()
        conn.close()
        return render_template('shopping_list.html', active_page='shopping_list', shopping_list=shopping_list)

    if request.method == 'POST':
        name = request.form['name']
        amount = float(request.form['amount'])
        amount_type = request.form['amount_type']

        conn.execute('''
            INSERT INTO shopping_list (user_id, name, amount, amount_type)
            VALUES (?, ?, ?, ?)
        ''', (session['user_id'], name, amount, amount_type))
        conn.commit()
        conn.close()
        
        return redirect(url_for('shopping_list'))


# Удаление продукта из списка покупок (проверка по user_id)
@app.route('/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    conn.execute('''
        DELETE FROM shopping_list WHERE id = ? AND user_id = ?
    ''', (product_id, session['user_id']))
    conn.commit()
    conn.close()
    return redirect(url_for('shopping_list'))


# Отображение страницы аналитики
@app.route('/analytics')
def analytics():
    return render_template('analytics.html', active_page='analytics')


# Получение данных аналитики для текущего пользователя
@app.route('/analytics_data')
def analytics_data():
    # Проверка авторизации
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    conn = get_db_connection()
    cursor = conn.cursor()

    if start_date and end_date:
        cursor.execute(
            "SELECT data_add, COUNT(*) FROM analytics WHERE user_id = ? AND data_add IS NOT NULL AND data_add BETWEEN ? AND ? GROUP BY data_add",
            (user_id, start_date, end_date)
        )
        added = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT data_delete, COUNT(*) FROM analytics WHERE user_id = ? AND data_delete IS NOT NULL AND data_delete BETWEEN ? AND ? GROUP BY data_delete",
            (user_id, start_date, end_date)
        )
        deleted = {row[0]: row[1] for row in cursor.fetchall()}
    else:
        cursor.execute(
            "SELECT data_add, COUNT(*) FROM analytics WHERE user_id = ? AND data_add IS NOT NULL GROUP BY data_add",
            (user_id,)
        )
        added = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.execute(
            "SELECT data_delete, COUNT(*) FROM analytics WHERE user_id = ? AND data_delete IS NOT NULL GROUP BY data_delete",
            (user_id,)
        )
        deleted = {row[0]: row[1] for row in cursor.fetchall()}

    conn.close()

    # Формирование итогового словаря аналитики по датам
    analytics = {}
    for date in set(added.keys()) | set(deleted.keys()):
        analytics[date] = {
            "added": added.get(date, 0),
            "deleted": deleted.get(date, 0)
        }
    return jsonify(analytics)


# Контекстный процессор для уведомлений о продуктах с приближающимся сроком годности
@app.context_processor
def inject_notifications():
    # Если пользователь не авторизован, возвращаем пустой список уведомлений
    if 'user_id' not in session:
        return dict(notifications=[], notifications_count=0)
        
    dismissed = session.get('dismissed_notifications', [])
    conn = get_db_connection()
    products = conn.execute('SELECT id, name, expiration_date FROM products WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()

    notifications = []
    today = datetime.today().date()
    warning_days = 3
    # Формирование уведомлений для каждого продукта
    for product in products:
        if product['id'] in dismissed:
            continue
        exp_date = datetime.strptime(product['expiration_date'], '%Y-%m-%d').date()
        days_left = (exp_date - today).days
        if days_left < 0:
            notifications.append({
                'id': product['id'],
                'message': f"{product['name'].capitalize()} - истек срок годности!"
            })
        elif days_left <= warning_days:
            notifications.append({
                'id': product['id'],
                'message': f"{product['name'].capitalize()} скоро испортится! Осталось {days_left} дн."
            })
    return dict(notifications=notifications, notifications_count=len(notifications))


# Отклонение (удаление) уведомления по product_id
@app.route('/dismiss_notification/<int:product_id>', methods=['POST'])
def dismiss_notification(product_id):
    dismissed = session.get('dismissed_notifications', [])
    if product_id not in dismissed:
        dismissed.append(product_id)
        session['dismissed_notifications'] = dismissed
    return '', 204


# Удаление продукта с главного хранилища и запись в аналитику удаления
@app.route("/delete_product_from_index/<int:product_id>", methods=['POST'])
def delete_product_from_index(product_id):
    if request.method == 'POST':
        conn = get_db_connection()
        conn.execute('''DELETE FROM products WHERE id = ?''', (product_id,))
        conn.commit()
        conn.close()
        conn = get_db_connection()
        conn.execute('''INSERT INTO analytics (user_id, data_delete) VALUES (?, ?)''', (session.get('user_id', -1), datetime.now().strftime('%Y-%m-%d')))
        conn.commit()
        conn.close()
        return redirect(url_for('home'))


# Генерация QR-кода для продукта по его id
@app.route('/qr_image/<int:product_id>')
def qr_image(product_id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    if product is None:
        return "Продукт не найден", 404

    product_dict = dict(product)
    data = json.dumps(product_dict, ensure_ascii=False)
    qr_code = segno.make(data)
    output = io.BytesIO()
    qr_code.save(output, kind='svg', scale=20)
    output.seek(0)
    return send_file(output, mimetype='image/svg+xml')


if __name__ == '__main__':
    app.run(debug=True)