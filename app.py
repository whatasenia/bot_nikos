from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

DB_NAME = 'bd_nikos.sql'

def get_data(query, params=()):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute(query, params)
    data = cur.fetchall()
    conn.close()
    return data

def init_db():
    """
    Инициализирует базу данных и создает таблицу, если она еще не существует.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS user('
                    'id INTEGER PRIMARY KEY AUTOINCREMENT,'
                    'employee TEXT,'
                    'project TEXT,'
                    'time_stamp TEXT,'
                    'comment TEXT);')
        conn.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/report')
def report():
    date = request.args.get('date', '')
    if not date:
        return "Ошибка: укажите дату в параметрах (?date=YYYY-MM-DD)", 400

    records = get_data("SELECT time_stamp, employee, project, comment "
                       "FROM user WHERE date(time_stamp) = ?",
                       (date,))

    if not records:
        return "Записей на указанную дату не найдено", 404

    return render_template('report.html', records=records)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)