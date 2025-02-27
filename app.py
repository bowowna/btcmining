from flask import Flask, request, jsonify, session
from flask_cors import CORS
import sqlite3
import hashlib
import os
from datetime import datetime
import uuid

app = Flask(__name__)
# Разрешаем CORS для GitHub Pages
CORS(app, supports_credentials=True, origins=['https://ваш-username.github.io'])
app.secret_key = os.urandom(24)

# Путь к базе данных (для Python Anywhere)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')

# Пересоздание базы данных
def recreate_db():
    # Удаляем старую базу данных, если она существует
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Создаем таблицу пользователей
    c.execute('''CREATE TABLE users
                 (id TEXT PRIMARY KEY,
                  username TEXT,
                  email TEXT,
                  password TEXT,
                  balance REAL DEFAULT 0.0,
                  is_anonymous BOOLEAN DEFAULT 1)''')
    
    # Создаем таблицу выводов
    c.execute('''CREATE TABLE withdrawals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT,
                  amount REAL,
                  btc_address TEXT,
                  status TEXT,
                  timestamp DATETIME,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')
    
    conn.commit()
    conn.close()
    print("База данных успешно пересоздана")

# Функция для подключения к базе данных
def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn

# Инициализация базы данных при запуске
if not os.path.exists(DB_PATH):
    recreate_db()

# Создание анонимного пользователя
@app.route('/create_anonymous', methods=['POST'])
def create_anonymous():
    try:
        user_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO users (id, balance, is_anonymous) VALUES (?, 0.0, 1)',
                 (user_id,))
        conn.commit()
        
        session['user_id'] = user_id
        return jsonify({
            'user_id': user_id,
            'message': 'Анонимный пользователь создан'
        }), 201
    except Exception as e:
        print(f"Ошибка при создании анонимного пользователя: {str(e)}")
        return jsonify({'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals():
            conn.close()

# Регистрация существующего анонимного пользователя
@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Нет данных'}), 400
            
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        user_id = data.get('user_id')  # ID анонимного пользователя
        
        if not all([username, password, email, user_id]):
            return jsonify({'error': 'Все поля обязательны'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Пароль должен быть не менее 6 символов'}), 400
            
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем существование пользователя или email
        c.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
        if c.fetchone():
            return jsonify({'error': 'Пользователь или email уже существует'}), 400
        
        # Обновляем анонимного пользователя
        c.execute('''UPDATE users 
                    SET username = ?, email = ?, password = ?, is_anonymous = 0
                    WHERE id = ?''',
                 (username, email, hashed_password, user_id))
        
        if c.rowcount == 0:
            return jsonify({'error': 'Пользователь не найден'}), 404
            
        conn.commit()
        return jsonify({'message': 'Регистрация успешна'}), 200
    except Exception as e:
        print(f"Ошибка при регистрации: {str(e)}")
        return jsonify({'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals():
            conn.close()

# Вход
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Нет данных'}), 400
            
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Необходимо указать имя пользователя и пароль'}), 400
            
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT id, username FROM users WHERE username = ? AND password = ? AND is_anonymous = 0',
                 (username, hashed_password))
        user = c.fetchone()
        
        if user:
            session['user_id'] = user[0]
            return jsonify({
                'user_id': user[0],
                'username': user[1],
                'message': 'Вход выполнен успешно'
            }), 200
        return jsonify({'error': 'Неверные учетные данные'}), 401
    except Exception as e:
        print(f"Ошибка при входе: {str(e)}")
        return jsonify({'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals():
            conn.close()

# Получение баланса
@app.route('/balance/<user_id>', methods=['GET'])
def get_balance(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({'balance': result[0]}), 200
    return jsonify({'error': 'Пользователь не найден'}), 404

# Увеличение награды за просмотр рекламы
@app.route('/increase_reward/<user_id>', methods=['POST'])
def increase_reward(user_id):
    reward_amount = 0.000000001  # 1 сатоши за просмотр
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + ? WHERE id = ?',
             (reward_amount, user_id))
    conn.commit()
    conn.close()
    
    return jsonify({'message': 'Награда начислена'}), 200

# Запрос на вывод средств
@app.route('/withdraw/<user_id>', methods=['POST'])
def withdraw(user_id):
    try:
        data = request.get_json()
        amount = data.get('amount')
        btc_address = data.get('btc_address')
        
        if not all([amount, btc_address]):
            return jsonify({'error': 'Не указана сумма или адрес'}), 400
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Проверяем баланс
        c.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        result = c.fetchone()
        
        if not result:
            return jsonify({'error': 'Пользователь не найден'}), 404
            
        current_balance = result[0]
        
        if current_balance < float(amount):
            return jsonify({'error': 'Недостаточно средств'}), 400
        
        # Создаем запрос на вывод
        c.execute('''INSERT INTO withdrawals (user_id, amount, btc_address, status, timestamp)
                     VALUES (?, ?, ?, ?, ?)''',
                 (user_id, amount, btc_address, 'pending', datetime.now()))
        
        # Уменьшаем баланс пользователя
        c.execute('UPDATE users SET balance = balance - ? WHERE id = ?',
                 (amount, user_id))
        
        conn.commit()
        return jsonify({'message': 'Запрос на вывод создан'}), 200
    except Exception as e:
        print(f"Ошибка при выводе средств: {str(e)}")
        return jsonify({'error': 'Ошибка сервера'}), 500
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == '__main__':
    # Локальный запуск для разработки
    app.run(debug=True)
else:
    # Продакшн настройки
    app.debug = False 
