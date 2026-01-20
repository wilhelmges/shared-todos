from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
DATABASE = 'todos.db'

def init_db():
    """Ініціалізація бази даних"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # Таблиця списків задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблиця задач
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            position REAL NOT NULL,
            completed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (list_id) REFERENCES lists(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()    

def get_db_connection():
    """Отримання з'єднання з БД"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Головна сторінка редагування"""
    return render_template('index.html')

@app.route('/view/<int:list_id>')
def view_list(list_id):
    """Сторінка перегляду списку задач"""
    conn = get_db_connection()
    list_data = conn.execute('SELECT * FROM lists WHERE id = ?', (list_id,)).fetchone()
    conn.close()
    
    if not list_data:
        return "Список не знайдено", 404
    
    return render_template('view.html', list_id=list_id, list_name=dict(list_data)['name'])

# API endpoints

@app.route('/api/lists', methods=['GET'])
def get_lists():
    """Отримати всі списки задач"""
    conn = get_db_connection()
    lists = conn.execute('SELECT * FROM lists ORDER BY id DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in lists])

@app.route('/api/lists', methods=['POST'])
def create_list():
    """Створити новий список задач"""
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': 'Назва списку не може бути порожньою'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO lists (name) VALUES (?)', (name,))
    list_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({'id': list_id, 'name': name}), 201

@app.route('/api/lists/<int:list_id>', methods=['PUT'])
def update_list(list_id):
    """Оновити назву списку"""
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': 'Назва списку не може бути порожньою'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE lists SET name = ? WHERE id = ?', (name, list_id))
    conn.commit()
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Список не знайдено'}), 404
    
    conn.close()
    return jsonify({'id': list_id, 'name': name})

@app.route('/api/lists/<int:list_id>', methods=['DELETE'])
def delete_list(list_id):
    """Видалити список задач"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM lists WHERE id = ?', (list_id,))
    conn.commit()
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Список не знайдено'}), 404
    
    conn.close()
    return jsonify({'success': True})

@app.route('/api/lists/<int:list_id>/tasks', methods=['GET'])
def get_tasks(list_id):
    """Отримати всі невиконані задачі списку"""
    include_completed = request.args.get('include_completed', 'false').lower() == 'true'
    
    conn = get_db_connection()
    if include_completed:
        tasks = conn.execute(
            'SELECT * FROM tasks WHERE list_id = ? ORDER BY position ASC, id ASC',
            (list_id,)
        ).fetchall()
    else:
        tasks = conn.execute(
            'SELECT * FROM tasks WHERE list_id = ? AND completed = 0 ORDER BY position ASC, id ASC',
            (list_id,)
        ).fetchall()
    conn.close()
    
    return jsonify([dict(row) for row in tasks])

@app.route('/api/lists/<int:list_id>/tasks', methods=['POST'])
def create_task(list_id):
    """Створити нову задачу"""
    data = request.get_json()
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({'error': 'Текст задачі не може бути порожнім'}), 400
    
    # Знаходимо максимальну позицію для цього списку
    conn = get_db_connection()
    cursor = conn.cursor()
    max_pos = conn.execute(
        'SELECT MAX(position) FROM tasks WHERE list_id = ?',
        (list_id,)
    ).fetchone()[0] or 0
    
    position = max_pos + 1.0
    
    cursor.execute(
        'INSERT INTO tasks (list_id, text, position) VALUES (?, ?, ?)',
        (list_id, text, position)
    )
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'id': task_id,
        'list_id': list_id,
        'text': text,
        'position': position,
        'completed': False
    }), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    """Оновити задачу (текст або позицію)"""
    data = request.get_json()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Отримуємо поточну задачу
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task:
        conn.close()
        return jsonify({'error': 'Задачу не знайдено'}), 404
    
    task_dict = dict(task)
    updates = []
    params = []
    
    if 'text' in data:
        text = data['text'].strip()
        if not text:
            conn.close()
            return jsonify({'error': 'Текст задачі не може бути порожнім'}), 400
        updates.append('text = ?')
        params.append(text)
    
    if 'position' in data:
        updates.append('position = ?')
        params.append(float(data['position']))
    
    if 'completed' in data:
        updates.append('completed = ?')
        params.append(1 if data['completed'] else 0)
    
    if not updates:
        conn.close()
        return jsonify(task_dict)
    
    params.append(task_id)
    query = f'UPDATE tasks SET {", ".join(updates)} WHERE id = ?'
    cursor.execute(query, params)
    conn.commit()
    conn.close()
    
    # Повертаємо оновлену задачу
    conn = get_db_connection()
    updated_task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    conn.close()
    
    return jsonify(dict(updated_task))

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Видалити задачу"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    
    if cursor.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Задачу не знайдено'}), 404
    
    conn.close()
    return jsonify({'success': True})

@app.route('/api/tasks/reorder', methods=['POST'])
def reorder_tasks():
    """Переупорядкувати задачі в списку"""
    data = request.get_json()
    task_positions = data.get('positions', [])  # [{id: 1, position: 1.0}, ...]
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    for item in task_positions:
        cursor.execute(
            'UPDATE tasks SET position = ? WHERE id = ?',
            (float(item['position']), item['id'])
        )
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

# if __name__ == '__main__':
#     init_db()
#     app.run(debug=True)
