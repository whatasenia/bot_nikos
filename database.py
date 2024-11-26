import sqlite3
from datetime import datetime
from logging import lastResort

DB_NAME = 'bd_nikos.sql'

def init_db():
    """
    creating database and table
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

def add_log(employee, project, time_stamp, comment):
    """
    function for added data in database
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO user(employee, project, time_stamp, comment) '
            'VALUES  (?, ?, ?, ?)', (employee, project, time_stamp, comment)
        )
        conn.commit()
        return cursor.lastrowid

def get_daily_report(employee, date):
    """
    get a list of records from the database for the specified day.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        start_date = datetime.strptime(f'{date} 00:00:00', '%Y-%m-%d %H:%M:%S')
        end_date = datetime.strptime(f'{date} 23:59:00', '%Y-%m-%d %H:%M:%S')

        query = """
                    SELECT id, time_stamp, employee, project, comment 
                    FROM user 
                    WHERE time_stamp BETWEEN ? AND ?
                """
        params = [start_date, end_date]
        if employee:
            query += " AND LOWER(employee) = ?"
            params.append(employee.lower())

        query += " ORDER BY time_stamp ASC"
        cursor.execute(query, params)

        rows = cursor.fetchall()

        result = []
        for row in rows:
            try:
                time_stamp = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S')  # Преобразование строки в дату
            except ValueError:
                time_stamp = f"Некорректный формат времени: {row[1]}"
            result.append((row[0], time_stamp, row[2], row[3], row[4]))
        return result

def get_period_report(employee, start_date, end_date):
    """
    retrieves records for the specified employee for a specified period of time.
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        query = """
        SELECT id, time_stamp, employee, project, comment 
        FROM user 
        WHERE time_stamp BETWEEN ? AND ?
        """
        params = [f'{start_date} 00:00:00', f'{end_date} 23:59:59']

        if employee:
            query += " AND LOWER(employee) = ?"
            params.append(employee.lower())
        query += "ORDER BY time_stamp ASC"
        cursor.execute(query, params)

        rows = cursor.fetchall()
        result = []
        for row in rows:
            try:
                time_stamp = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                time_stamp = f'Некорректный формат времени: {row[1]}'
            result.append((row[0], time_stamp, row[2], row[3], row[4]))
        return result

def delete_record_by_id(record_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user WHERE id = ?', (record_id,))
        conn.commit()
        return cursor.rowcount > 0
