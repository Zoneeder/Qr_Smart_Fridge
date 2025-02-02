from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from datetime import datetime

app = Flask(__name__)

# Функции для подключения к базе данных

#######################################

def get_db_connection():
    conn = sqlite3.connect("database/fridge.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection_for_shopping_list():
    connsl = sqlite3.connect('database/shopping_list.db')
    connsl.row_factory = sqlite3.Row
    return connsl

#######################################

# Маршрут для главной страницы
@app.route('/')
def home():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM products').fetchall()  # Получаем все продукты из базы данных
    conn.close()
    return render_template('index.html', active_page='home', products=products)

# Маршрут для страницы "Отсканировать Qr-код"
@app.route('/Qr-code')
def Qr_code():
    return render_template('base.html', active_page='Qr-code')

# Маршрут для страницы "Список покупок"
@app.route('/shopping_list', methods=['GET', 'POST'])
def products():
    connsl = get_db_connection_for_shopping_list()
    shopping_list = connsl.execute('SELECT * FROM shopping_list').fetchall()  # Получаем все продукты из базы данных
    connsl.close()
    return render_template('shopping_list.html', active_page='shopping_list', shopping_list=shopping_list)

# Маршрут для добавления продукта
@app.route('/add', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        # Получаем данные из формы
        name = request.form['name']
        product_type = request.form['type']
        manufacture_date = request.form['manufacture_date']
        expiration_date = request.form['expiration_date']
        quantity = float(request.form['quantity'])
        unit = request.form['unit']
        nutritional_value = request.form.get('nutritional_value', '')
        allergens = request.form.get('allergens', '')

        # Подключаемся к базе данных и добавляем продукт
        conn = get_db_connection()
        conn.execute('''
        INSERT INTO products (name, type, manufacture_date, expiration_date, quantity, unit, nutritional_value, allergens)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, product_type, manufacture_date, expiration_date, quantity, unit, nutritional_value, allergens))
        conn.commit()
        conn.close()

        # Перенаправляем на главную страницу
        return redirect(url_for('home'))

    # Если метод GET, отображаем форму добавления продукта
    return render_template('add_product.html', active_page='add')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', active_page='analytics')

if __name__ == '__main__':
    app.run(debug=True)