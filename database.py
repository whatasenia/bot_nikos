import sqlite3
from datetime import datetime
from logging import lastResort


DB_NAME = 'bd_nikos.sql'

def init_db():
    """
    инициализирует БД
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
    функция для добавления записи в БД
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO user(employee, project, time_stamp, comment) '
            'VALUES  (?, ?, ?, ?)', (employee, project, time_stamp, comment)
        )
        conn.commit()
        return cursor.lastrowid

def infer_year(date_input, current_date):
    """
    определяет год
    """
    if len(date_input) == 6:
        return datetime.strptime(date_input, '%d%m%y')
    else:
        month_day = datetime.strptime(date_input, '%d%m').replace(year=current_date.year)
        if month_day > current_date:
            month_day = month_day.replace(year=current_date.year - 1)
        return month_day

def format_report(logs, employee, report_date):
    """
    шаблон отчета по сотруднику за конкретный день
    """
    report = f'Сотрудник "{employee}" за {report_date.strftime("%d.%m.%y")}:\n\n'
    total_minutes = 0

    for i in range(len(logs)):
        start_time = datetime.strptime(str(logs[i][1]), '%Y-%m-%d %H:%M:%S')

        if i < len(logs) - 1:
            end_time = datetime.strptime(str(logs[i + 1][1]), '%Y-%m-%d %H:%M:%S')
            end_time_str = end_time.strftime('%H:%M')
            duration = int((end_time - start_time).total_seconds() // 60)
        else:
            end_time = datetime.now()
            end_time_str = 'НВ'
            duration = int((end_time - start_time).total_seconds() // 60)

        if logs[i][3].lower() in ['стоп', 'ушел']:
            continue

        total_minutes += duration
        report += f'{start_time.strftime("%H:%M")}-{end_time_str} - {logs[i][3]}'
        if logs[i][4]:
            report += f'\n({logs[i][4]})'
        report += '\n\n'

    total_hours = round(total_minutes / 60, 3)
    report += f'\n\nВсего: {total_hours} часов ({total_minutes} минут)'
    return report

def get_daily_report(employee, date):
    """
    формирует отчет из всех записей за текущий день
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

def get_unique_employees():
    """
    получает список сотрудников
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT employee FROM user')
        rows = cursor.fetchall()
        return [row[0] for row in rows]

def get_period_report(employee, start_date, end_date):
    """
    формирует отчет по сотруднику за указанный период
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
    """
    удаляет запись из БД по ИД
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user WHERE id = ?', (record_id,))
        conn.commit()
        return cursor.rowcount > 0

def send_report_internal(employee, date_part):
    """
    Внутренняя функция для формирования отчета
    """
    try:
        current_date = datetime.now()
        report_date = infer_year(date_part, current_date)

        report_date_str = report_date.strftime('%Y-%m-%d')
        logs = get_daily_report(employee, report_date_str)

        if not logs:
            return f'Записей за {date_part} для сотрудника "{employee}" не найдено'

        return format_report(logs, employee, report_date)

    except Exception as exc:
        return f'Ошибка при формировании отчета: {exc}'
