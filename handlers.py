import re
import sqlite3
from calendar import day_abbr
from datetime import datetime

from telebot import TeleBot
from database import (add_log, get_daily_report, delete_record_by_id,
                      get_period_report, infer_year, format_report,
                      send_report_internal, get_unique_employees, get_nearest_date)
from TOKEN import TOKEN

bot = TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, f'Привет! Я бот для управления записями в базе данных.')

@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def add_record(message):
    """
    The handler for adding a record
    If no date is specified, the current date is used
    """

    lines = message.text.strip().split('\n')
    if len(lines) < 3:
        bot.reply_to(message, 'Сообщение должно состоять минимум из 3х строк: '
                              'дата/время(формат ДДММ ЧЧММ комментарий или ЧЧММ комментарий), '
                              'сотрудник, проект')
        return

    try:
        date_time_str = lines[0].strip()
        employees = lines[1].strip().lower().split()
        project = lines[2].strip()

        match = re.match(r'(\d{4,6})? ?(\d{4})(?: (.+))?', date_time_str)
        if not match:
            bot.reply_to(message, 'Неверный формат строки времени. '
                                  'Используйте "ДДММ ЧЧММ комментарий" или "ЧЧММ комментарий"')
            return

        date_part = match.group(1) if match.group(1) else datetime.now().strftime('%d%m')
        time_part = match.group(2)
        comment = match.group(3).strip() if match.group(3) else ''

        date_with_year = get_nearest_date(date_part)
        full_date_time = datetime.strptime(f'{date_with_year.strftime("%d%m%Y")} {time_part}', "%d%m%Y %H%M")
        time_stamp = full_date_time.strftime('%Y-%m-%d %H:%M:%S')

        for employee in employees:
            record_id = add_log(employee, project, time_stamp, comment)
            report_emp = send_report_internal(employee, date_part)
            bot.reply_to(message, f'Запись добавлена: '
                                  f'ID: {record_id}'
                                  f'\nСотрудник: {employee}'
                                  f'\nПроект: {project}'
                                  f'\nДата и время: {time_stamp}'
                                  f'\n\n{report_emp}'
                         )

    except ValueError as ve:
        bot.reply_to(message, f'Ошибка в формате даты или времени: {ve}')
    except Exception as exc:
        bot.reply_to(message, f'Ошибка: {exc}')

@bot.message_handler(commands=['get'])
def get_records_by_date(message):
    """
    processes the /get command and returns a list of
    records from the database for the specified date.
    """

    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, 'Используйте формат: /get <ДДММГГ>')
            return

        date_str = args[1].strip()
        try:
            query_date = datetime.strptime(date_str, '%d%m%y').strftime('%Y-%m-%d')
        except ValueError:
            bot.reply_to(message, 'Формат даты должен быть ДДММГГ')
            return

        records = get_daily_report(None, query_date)

        if not records:
            bot.reply_to(message, f'Записи за {query_date} не найдены')
            return

        report = f'Записи за {date_str[:2]}.{date_str[2:4]}.{date_str[4:6]}:\n\n'
        for record in records:
            r_id, time_stamp, employee, project, comment = record
            report += (
                f'ID: {r_id}\n'
                f'Время: {time_stamp}\n'
                f'Сотрудник: {employee}\n'
                f'Проект: {project}\n'
                f'Комментарий: {comment}\n\n'
            )

        MAX_MESSAGE_LENGTH = 4095
        if len(report) > MAX_MESSAGE_LENGTH:
            parts = [report[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(report), MAX_MESSAGE_LENGTH)]
            for part in parts:
                bot.reply_to(message, part)
        else:
            bot.reply_to(message, report)

    except Exception as exc:
        bot.reply_to(message, f'Произошла ошибка: {exc}')

@bot.message_handler(commands=['report'])
def send_report(message):
    """
    обработчик команды репорт, отправляет отчет по сотруднику за указанную дату
    если дата не указана - используется текущая
    формат команды:
    /report ДДММ(ГГ) сотрудник
    /report сотрудник
    """
    try:
        args = message.text.split()

        if len(args) < 2:
            bot.reply_to(message, 'Укажите сотрудника: /report <сотрудник> <дата в формате ДДММ(ГГ)>'
                                  'либо /report сотрудник')
            return

        if args[-1].isdigit():
            date_input = args[-1]
            if len(date_input) == 6:
                full_date = datetime.strptime(date_input, '%d%m%y')
            elif len(date_input) == 4:
                current_year = datetime.now().strftime('%y')
                full_date = datetime.strptime(date_input + current_year, '%d%m%y')
            else:
                bot.reply_to(message, 'Неверный формат даты. Используйте ДДММГГ или ДДММ')
                return

            employee = ' '.join(args[1:-1]).strip().lower()
        else:
            full_date = datetime.now()
            employee = ' '.join(args[1:]).strip().lower()

        if not employee:
            bot.reply_to(message, 'Укажите имя сотрудника')
            return

        report_date_str = full_date.strftime('%Y-%m-%d')

        logs = get_daily_report(employee, report_date_str)
        if not logs:
            bot.reply_to(message, f'Записей за {report_date_str} для сотрудника "{employee}" не найдено')
            return

        report = format_report(logs, employee, full_date)

        MAX_MESSAGE_LENGTH = 4096
        if len(report) > MAX_MESSAGE_LENGTH:
            for chunk in [report[i:i + MAX_MESSAGE_LENGTH] for i
                          in range(0, len(report), MAX_MESSAGE_LENGTH)
                          ]:
                bot.reply_to(message, chunk)
        else:
            bot.reply_to(message, report)

    except ValueError as ve:
        bot.reply_to(message, f'Ошибка в формате даты: {ve}')
    except Exception as exc:
        bot.reply_to(message, f'Ошибка при формировании отчета: {exc}')
        print(f'Exception occurred: {exc}')

@bot.message_handler(commands=['reportAll'])
def report_all(message):
    """
    Обрабатывает команду /reportAll для генерации отчета за день по всем сотрудникам.
    Если сотрудник не работал в указанный день, это будет отображено в отчете.
    """
    try:
        args = message.text.split()

        if len(args) < 2:
            date_input = datetime.now().strftime('%d%m')
        else:
            date_input = args[1].strip()

        try:
            report_date = get_nearest_date(date_input)
        except ValueError:
            bot.reply_to(message, 'Формат даты должен быть ДДММ')
            return

        report_date_str = report_date.strftime('%Y-%m-%d')

        employees = get_unique_employees()
        if not employees:
            bot.reply_to(message, 'Список сотрудников пуст')
            return

        report = f'Отчет за {report_date.strftime("%d.%m.%y")}:\n\n'

        for employee in employees:
            logs = get_daily_report(employee, report_date_str)
            if not logs:
                report += (f'<b>🔴 Сотрудник "{employee}":</b> Не работал\n'
                           f'➖➖➖➖➖➖➖➖➖➖\n')
                continue

            employee_report = format_report(logs, employee, report_date)
            report += (f'<b>🔴 {employee_report}</b>\n'
                       f'➖➖➖➖➖➖➖➖➖➖\n')

        MAX_MESSAGE_LENGTH = 4095
        if len(report) > MAX_MESSAGE_LENGTH:
            for chunk in [report[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(report), MAX_MESSAGE_LENGTH)]:
                bot.reply_to(message, chunk)
        else:
            bot.reply_to(message, report, parse_mode='HTML')

    except Exception as exc:
        bot.reply_to(message, f'Ошибка при формировании общего отчета: {exc}')

@bot.message_handler(commands=['periodAll'])
def send_period_all(message):
    """
    формирует отчет по всем сотрудникам из базы за указанный период
    """

    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, f'Используйте: /periodAll <период в форме ДДММ-ДДММ>')
            return

        period = args[1].strip()

        try:
            start_period, end_period = period.split('-')
            start_day = int(start_period[:2])
            start_month = int(start_period[2:])
            end_day = int(end_period[:2])
            end_month = int(end_period[2:])
            current_year = datetime.now().year

            start_date = datetime(current_year, start_month, start_day)
            end_date = datetime(current_year, end_month, end_day)

            if end_date < start_date:
                bot.reply_to(message, 'Дата окончания периода должна быть позже даты начала.')
                return
        except ValueError:
            bot.reply_to(message, 'Период должен быть в формате ДДММ-ДДММ (например, 1708-2608)')
            return

        employees = get_unique_employees()
        if not employees:
            bot.reply_to(message, 'Список сотрудников пуст')
            return

        report = (f'Отчеты по сотрудникам за период с {start_date.strftime("%d.%m.%y")} '
                  f'по {end_date.strftime("%d.%m.%y")}:\n\n')

        for employee in employees:
            logs = get_period_report(employee, start_date.strftime('%Y-%m-%d'),
                                     end_date.strftime('%Y-%m-%d'))
            if not logs:
                report += f'<b>Сотрудник "{employee}"</b>: Не работал\n\n'
                continue

            daily_totals = {}
            total_minutes = 0

            for i in range(len(logs) - 1):
                current_date = logs[i][1].date()
                next_date = logs[i + 1][1].date()

                if current_date != next_date:
                    continue

                start_time = logs[i][1]
                end_time = logs[i + 1][1]
                duration = int((end_time - start_time).total_seconds() // 60)

                if logs[i][3].lower() not in ['стоп', 'ушел']:
                    total_minutes += duration
                    if current_date not in daily_totals:
                        daily_totals[current_date] = 0
                    daily_totals[current_date] += duration

            report += f'<b>Сотрудник "{employee}":</b>\n'
            report += f'Итого: {round(total_minutes / 60, 3)} ч ({total_minutes} мин):\n\n'

            # расписать по дням и кол-во часов:
            for date, minutes in sorted(daily_totals.items()):
                hours = round(minutes / 60, 3)
                report += f'<i>{date.strftime("%d.%m.%y")}: {hours} ч ({minutes} мин)</i>\n'
            report += '\n'

        MAX_MESSAGE_LENGTH = 4095
        if len(report) > MAX_MESSAGE_LENGTH:
            for chunk in [report[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(report), MAX_MESSAGE_LENGTH)]:
                bot.reply_to(message, chunk)
        else:
            bot.reply_to(message, report, parse_mode='HTML')

    except Exception as exc:
        bot.reply_to(message, f'Ошибка при формировании отчета за период: {exc}')

@bot.message_handler(commands=['period'])
def send_period_summary(message):
    """
    Generates a summary report for the specified employee over a date range
    """
    try:
        args = message.text.split()
        if len(args) < 3:
            bot.reply_to(message, f'Используйте: /report <сотрудник> <период в форме ДДММ-ДДММ>')
            return

        employee = args[1].strip().lower()
        period = args[2].strip()

        try:
            start_period, end_period = period.split('-')
            start_day = int(start_period[:2])
            start_month = int(start_period[2:])
            end_day= int(end_period[:2])
            end_month = int(end_period[2:])
            current_year = datetime.now().year

            start_date = datetime(current_year, start_month, start_day)
            end_date = datetime(current_year, end_month, end_day)
            if end_date < start_date:
                bot.reply_to(message, 'Дата окончания периода должна быть позже даты начала.')
                return
        except ValueError:
            bot.reply_to(message, 'Период должен быть в формате ДДММ-ДДММ (например, 1708-2608)')
            return

        logs = get_period_report(employee, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        if not logs:
            bot.reply_to(message, f'Записей для сотрудника {employee} '
                                  f'в период с {start_date.strftime("%d.%m.%y")} '
                                  f'по {end_date.strftime("%d.%m.%y")} не найдено')
            return

        daily_totals = {}
        total_minutes = 0

        for i in range(len(logs) - 1):
            current_date = logs[i][1].date()
            next_date = logs[i + 1][1].date()

            if current_date != next_date:
                continue

            start_time = logs[i][1]
            end_time = logs[i + 1][1]
            duration = int((end_time - start_time).total_seconds() // 60)

            if logs[i][3].lower() not in ['стоп', 'ушел']:
                total_minutes += duration
                if current_date not in daily_totals:
                    daily_totals[current_date] = 0
                daily_totals[current_date] += duration

        report = (f'Часы работы "{employee}" за период '
                  f'с {start_date.strftime("%d.%m.%y")} '
                  f'по {end_date.strftime("%d.%m.%y")}:\n\n')
        report += f'Итого: {round(total_minutes / 60, 3)} ч ({total_minutes} мин):\n\n'

        for date, minutes in sorted(daily_totals.items()):
            hours = round(minutes / 60, 3)
            report += f'{date.strftime("%d.%m.%y")}: Всего: {hours} ч ({minutes} мин)\n'
        bot.reply_to(message, report)

    except Exception as exc:
        bot.reply_to(message, f'Ошибка при формировании отчета за период: {exc}')

@bot.message_handler(commands=['delete'])
def delete_record(message):
    """
    deletes an entry from the DB by the specified ID
    """
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, 'Используйте: /delete <ID записи>')
        return

    try:
        record_id = int(args[1])
        if delete_record_by_id(record_id):
            bot.reply_to(message, f'Запись с ID={record_id} успешно удалена.')
        else:
            bot.reply_to(message, f'Запись с ID = {record_id} не найдена')

    except ValueError:
        bot.reply_to(message, f'ID должен быть числом.')
    except Exception as exc:
        bot.reply_to(message, f'Произошла ошибка: {exc}')

@bot.message_handler(commands=['help'])
def help_command(message):
    """
    commands with a description
    """

    commands = """
    
    /start - Приветственное сообщение.
    
    /help - Список доступных команд.
    
    /report <сотрудник> <ДДММ(ГГ)> - Отчет по сотруднику за указанный день. 
    Если дата не указана, используется текущий день.
    
    /reportAll <ДДММ> - генерация отчетов за день по всем сотрудникам.
    Если дата не указана, подставляется сегодняшняя дата.
    
    /get <ДДММГГ> - Получение всех записей за конкретный день с ID.
    
    /period <сотрудник> <ДДММ-ДДММ> - Общее количество часов работы 
    сотрудника за указанный период.
    
    /periodAll <ДДММ-ДДММ | ДДММ> - 
        1. Если указан период (ДДММ-ДДММ), выводит отчеты по всем сотрудникам за указанный период.
        2. Если указана одна дата (ДДММ), выводит отчеты для всех сотрудников, которые работали в этот день, в формате команды /report.
    
    /delete <ID> - Удаление записи по указанному ID.
    
    /add <сотрудник> <проект> <дата и время> [комментарий] - Добавление новой записи в базу данных.
    
    Чтобы добавить запись, отправьте сообщение в формате:
    
    1 строка: Дата (опц), время (обяз), комментарий (опц). Формат: ДДММГГ ЧЧММ текст.  
    2 строка: Имя сотрудника.  
    3 строка: Название проекта.
    """
    bot.reply_to(message, commands)
