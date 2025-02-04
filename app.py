from flask import *
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "top_secret"  # Замените на свой секретный ключ

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

    conn = get_db_connection()
    # Выбираем продукты только для текущего пользователя
    products = conn.execute('SELECT * FROM products WHERE user_id = ?', (session['user_id'],)).fetchall()
    conn.close()
    return render_template('index.html', active_page='home', products=products)


# Маршрут для страницы "Отсканировать Qr-код"
@app.route('/Qr-code')
def Qr_code():
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
    return render_template('shopping_list.html', active_page='shopping_list', shopping_list=shopping_list)

@app.route('/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    connsl = get_db_connection_for_shopping_list()
    connsl.execute('DELETE FROM shopping_list WHERE id = ?', (product_id,))
    connsl.commit()
    connsl.close()
    return redirect(url_for('products'))

# Маршрут для добавления продукта
@app.route('/add', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        name = request.form['name']
        product_type = request.form['type']
        manufacture_date = request.form['manufacture_date']
        expiration_date = request.form['expiration_date']
        quantity = float(request.form['quantity'])
        unit = request.form['unit']
        nutritional_value = request.form.get('nutritional_value', '')
        allergens = request.form.get('allergens', '')

        conn = get_db_connection()
        # Добавляем также user_id для связывания продукта с пользователем
        conn.execute('''
        INSERT INTO products (user_id, name, type, manufacture_date, expiration_date, quantity, unit, nutritional_value, allergens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session['user_id'], name, product_type, manufacture_date, expiration_date, quantity, unit, nutritional_value, allergens))
        conn.commit()
        conn.close()
        return redirect(url_for('home'))

    return render_template('add_product.html', active_page='add')


@app.route('/analytics')
def analytics():
    return render_template('analytics.html', active_page='analytics')

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


if __name__ == '__main__':
    app.run(debug=True)