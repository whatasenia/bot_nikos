import sqlite3
from datetime import datetime, timedelta
from logging import lastResort, currentframe
import logging
from dateutil import parser
import re

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
    Функция для добавления записи в БД
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
    report += f'\nВсего: {total_hours} часов ({total_minutes} минут)'
    return report

def get_daily_report(employee, date):
    """
    Формирует отчет из всех записей за текущий день
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
                if not row[2]:
                    raise ValueError(f"Имя сотрудника отсутствует для записи с ID: {row[0]}")

                clean_time_stamp = re.sub(r'\s\([^)]+\)', '', row[1])

                time_stamp = datetime.strptime(clean_time_stamp, '%Y-%m-%d %H:%M:%S')
            except ValueError as ve:
                continue
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
    Формирует отчет по сотруднику за указанный период
    """
    logs = get_logs(employee, f'{start_date} 00:00:00', f'{end_date} 23:59:59')

    if not logs:
        return f'Записей за период с {start_date} по {end_date} для сотрудника "{employee}" не найдено'


    return format_report(logs, employee, datetime.strptime(start_date, '%Y-%m-%d'))

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

def get_nearest_date(date_input):
    """
    Возвращает ближайшую дату на основе текущей даты и введенного ДДММ.
    Если дата в текущем году уже прошла, возвращаем дату за следующий год.
    """
    current_date = datetime.now()
    day, month = int(date_input[:2]), int(date_input[2:])

    # Проверка на допустимость дня и месяца
    try:
        datetime(current_date.year, month, day)
    except ValueError:
        raise ValueError(f"Неверная дата: {date_input}")

    date_this_year = datetime(current_date.year, month, day)
    date_last_year = datetime(current_date.year - 1, month, day)

    delta_this_year = abs((date_this_year - current_date).days)
    delta_last_year = abs((date_last_year - current_date).days)

    if delta_this_year <= delta_last_year:
        nearest_date = date_this_year
    else:
        nearest_date = date_last_year

    return nearest_date.replace(hour=0, minute=0, second=0, microsecond=0)

def get_logs(employee, start_date, end_date):
    """
    Общая функция для получения логов из базы данных за указанный период и фильтрации по сотруднику
    """
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
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
                time_stamp = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                continue
            result.append((row[0], time_stamp, row[2], row[3], row[4]))
        return result

def safe_parse_date(date_string):
    """
    Универсальный разбор даты. Автоматически определяет формат и убирает лишние данные.
    """
    logging.debug(f"Полученная строка даты: {date_string}")

    try:
        parsed_date = parser.parse(date_string, dayfirst=True).date()
        logging.debug(f"Дата успешно распознана: {parsed_date}")
        return parsed_date
    except ValueError as e:
        logging.error(f"Ошибка при разборе даты {date_string}: {e}")
        return None