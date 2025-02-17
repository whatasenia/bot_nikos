from flask import Flask, render_template, request
import sqlite3

app = Flask(__name__)

def get_data(query, params=()):
    conn = sqlite3.connect('bd_nikos.sql')
    cur = conn.cursor()
    cur.execute(query, params)
    data = cur.fetchall()
    conn.close()
    return data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/report')
def report():
    date = request.args.get('date', '')
    records = get_data("SELECT * FROM employee_records WHERE time_stamp LIKE ?", (f'{date}%',))
    return render_template('report.html', records=records)

if __name__ == '__main__':
    app.run(debug=True)
