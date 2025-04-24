from flask import *
import os
from datetime import datetime
import io
import segno
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super-secret")

# PostgreSQL connection (Render)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ========== MODELS ==========

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    manufacture_date = db.Column(db.String(20))
    expiration_date = db.Column(db.String(20))
    quantity = db.Column(db.Float)
    unit = db.Column(db.String(20))
    nutritional_value = db.Column(db.String(200))
    allergens = db.Column(db.String(200))

class ShoppingItem(db.Model):
    __tablename__ = 'shopping_list'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    amount_type = db.Column(db.String(50), nullable=False)

class Analytics(db.Model):
    __tablename__ = 'analytics'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_add = db.Column(db.String(20), nullable=True)
    data_delete = db.Column(db.String(20), nullable=True)

with app.app_context():
    db.create_all()

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

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm = request.form['confirm']

        if not username or not email or not password or not confirm:
            flash("Все поля обязательны", "danger")
            return render_template('register.html')

        if password != confirm:
            flash("Пароли не совпадают", "danger")
            return render_template('register.html')

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash("Пользователь уже существует", "danger")
            return render_template('register.html')

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash("Регистрация успешна!", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username_or_email'].strip()
        password = request.form['password']

        user = User.query.filter((User.username == username_or_email) | (User.email == username_or_email)).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash("Вы вошли в систему", "success")
            return redirect(url_for('home'))
        else:
            flash("Неверные данные", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for('login'))

@app.route('/')
def home():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')
    if search_query:
        products = Product.query.filter(Product.user_id == session['user_id'],
                                        (Product.name.ilike(f'%{search_query}%') | Product.type.ilike(f'%{search_query}%'))).all()
    else:
        products = Product.query.filter_by(user_id=session['user_id']).all()

    return render_template('index.html', active_page='home', products=products, search_query=search_query)

@app.route('/Qr-code', methods=['GET', 'POST'])
def qr_code():
    if request.method == 'POST':
        try:
            data = request.get_json()
            new_product = Product(
                user_id=session.get('user_id', -1),
                name=data["name"],
                type=data["type"],
                manufacture_date=data["manufacture_date"],
                expiration_date=data["expiration_date"],
                quantity=data["quantity"],
                unit=data["unit"],
                nutritional_value=data["nutritional_value"],
                allergens=data.get("allergens", "-")
            )
            db.session.add(new_product)
            db.session.commit()

            db.session.add(Analytics(user_id=session.get('user_id', -1), data_add=datetime.now().strftime('%Y-%m-%d')))
            db.session.commit()

            return jsonify({"success": True, "message": "QR-код сохранен"}), 200

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400

    return render_template('Qr-code.html', active_page='Qr-code')

@app.route('/shopping_list', methods=['GET', 'POST'])
def shopping_list():
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    if request.method == 'GET':
        shopping_list = ShoppingItem.query.filter_by(user_id=session['user_id']).order_by(ShoppingItem.id.desc()).all()
        return render_template('shopping_list.html', active_page='shopping_list', shopping_list=shopping_list)

    if request.method == 'POST':
        name = request.form['name']
        amount = float(request.form['amount'])
        amount_type = request.form['amount_type']
        new_item = ShoppingItem(user_id=session['user_id'], name=name, amount=amount, amount_type=amount_type)
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('shopping_list'))

@app.route('/delete/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    item = ShoppingItem.query.filter_by(id=product_id, user_id=session['user_id']).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('shopping_list'))

@app.route('/analytics')
def analytics():
    return render_template('analytics.html', active_page='analytics')

@app.route('/analytics_data')
def analytics_data():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = session['user_id']
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date and end_date:
        added = Analytics.query.filter_by(user_id=user_id).filter(Analytics.data_add != None,
            Analytics.data_add.between(start_date, end_date)).with_entities(Analytics.data_add, db.func.count()).group_by(Analytics.data_add).all()
        deleted = Analytics.query.filter_by(user_id=user_id).filter(Analytics.data_delete != None,
            Analytics.data_delete.between(start_date, end_date)).with_entities(Analytics.data_delete, db.func.count()).group_by(Analytics.data_delete).all()
    else:
        added = Analytics.query.filter_by(user_id=user_id).filter(Analytics.data_add != None).with_entities(Analytics.data_add, db.func.count()).group_by(Analytics.data_add).all()
        deleted = Analytics.query.filter_by(user_id=user_id).filter(Analytics.data_delete != None).with_entities(Analytics.data_delete, db.func.count()).group_by(Analytics.data_delete).all()

    analytics = {}
    for row in added:
        analytics[row[0]] = {"added": row[1], "deleted": 0}
    for row in deleted:
        if row[0] in analytics:
            analytics[row[0]]["deleted"] = row[1]
        else:
            analytics[row[0]] = {"added": 0, "deleted": row[1]}

    return jsonify(analytics)

@app.context_processor
def inject_notifications():
    if 'user_id' not in session:
        return dict(notifications=[], notifications_count=0)

    dismissed = session.get('dismissed_notifications', [])
    products = Product.query.filter_by(user_id=session['user_id']).all()

    notifications = []
    today = datetime.today().date()
    warning_days = 3
    for product in products:
        if product.id in dismissed:
            continue
        exp_date = datetime.strptime(product.expiration_date, '%Y-%m-%d').date()
        days_left = (exp_date - today).days
        if days_left < 0:
            notifications.append({
                'id': product.id,
                'message': f"{product.name.capitalize()} - истек срок годности!"
            })
        elif days_left <= warning_days:
            notifications.append({
                'id': product.id,
                'message': f"{product.name.capitalize()} скоро испортится! Осталось {days_left} дн."
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
    if 'user_id' not in session:
        flash("Пожалуйста, войдите в систему", "danger")
        return redirect(url_for('login'))

    product = Product.query.get(product_id)
    if product:
        db.session.delete(product)
        db.session.commit()
        db.session.add(Analytics(user_id=session.get('user_id', -1), data_delete=datetime.now().strftime('%Y-%m-%d')))
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/qr_image/<int:product_id>')
def qr_image(product_id):
    product = Product.query.get(product_id)
    if not product:
        return "Продукт не найден", 404

    product_dict = {
        "name": product.name,
        "type": product.type,
        "manufacture_date": product.manufacture_date,
        "expiration_date": product.expiration_date,
        "quantity": product.quantity,
        "unit": product.unit,
        "nutritional_value": product.nutritional_value,
        "allergens": product.allergens
    }
    data = json.dumps(product_dict, ensure_ascii=False)
    qr_code = segno.make(data)
    output = io.BytesIO()
    qr_code.save(output, kind='svg', scale=20)
    output.seek(0)
    return send_file(output, mimetype='image/svg+xml')

if __name__ == '__main__':
    app.run(debug=True)
