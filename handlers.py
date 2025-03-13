import locale
import re
from datetime import datetime
import sqlite3

from telebot import TeleBot, types
locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')

from database import (add_log, get_daily_report, delete_record_by_id,
                      infer_year, format_report, send_report_internal,
                      get_unique_employees, get_nearest_date, get_logs)
from TOKEN import TOKEN

DB_NAME = 'bd_nikos.sql'
bot = TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, f'Привет! Я бот для управления записями в базе данных.')

@bot.message_handler(func=lambda message: not message.text.startswith('/'))
def add_record(message):
    """
    Добавление записи в БД + кнопки
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

            keyboard = types.InlineKeyboardMarkup()
            delete_button = types.InlineKeyboardButton('🗑 Удалить', callback_data=f'delete_{record_id}')
            edit_button = types.InlineKeyboardButton('✏️ Изменить', callback_data=f'edit_{record_id}')
            keyboard.add(delete_button, edit_button)

            bot.reply_to(message, f'Запись добавлена: '
                                  f'ID: {record_id}'
                                  f'\nСотрудник: {employee}'
                                  f'\nПроект: {project}'
                                  f'\nДата и время: {time_stamp}'
                                  f'\n\n{report_emp}',
                                  reply_markup=keyboard)

    except ValueError as ve:
        bot.reply_to(message, f'Ошибка в формате даты или времени: {ve}')
    except Exception as exc:
        bot.reply_to(message, f'Ошибка: {exc}')

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def delete_record_callback(call):
    """
    Обработчик кнопки для удаления записи по ID
    """
    record_id = int(call.data.split('_')[1])

    try:
        if delete_record_by_id(record_id):
            bot.answer_callback_query(call.id, text=f'Запись с ID={record_id} успешно удалена.')
            bot.edit_message_text(f'Запись с ID={record_id} была удалена.',
                                  call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, text=f'Запись с ID={record_id} не найдена.')

    except Exception as exc:
        bot.answer_callback_query(call.id, text=f'Произошла ошибка: {exc}')

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_'))
def callback_edit(call):
    """
    Обработчик кнопки для редактирования записи по ID

    """
    record_id = int(call.data.split('_')[1])

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT employee, project, time_stamp, comment FROM user WHERE id = ?", (record_id,))
        record = cursor.fetchone()

    if record:
        employee, project, time_stamp, comment = record

        date_part = time_stamp[8:10] + time_stamp[5:7]
        time_part = time_stamp[11:16].replace(":", "")
        original_message = f"{date_part} {time_part} {comment}\n{employee}\n{project}"

        bot.send_message(
            call.message.chat.id,
            f"✏️ Скопируйте сообщение, отредактируйте и отправьте снова:\n\n```{original_message}```",
            parse_mode="Markdown")
        delete_record_by_id(record_id)

    else:
        bot.answer_callback_query(call.id, '❌ Ошибка: оригинальное сообщение не найдено.')

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
    Формирует отчет по всем сотрудникам из базы за указанный период.
    """
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, f'Используйте: /periodAll <период в форме ДДММ-ДДММ>')
            return

        period = args[1].strip()
        print(period)

        if '-' not in period or len(period) != 9:
            bot.reply_to(message, 'Неверный формат периода. '
                                  'Используйте: ДДММ-ДДММ (например, 0101-0203)')
            return

        start_period, end_period = period.split('-')
        print(f"start_period: {start_period}, end_period: {end_period}")

        if len(start_period) != 4 or len(end_period) != 4:
            bot.reply_to(message, 'Неверный формат периода. '
                                  'Используйте: ДДММ-ДДММ (например, 0101-0203)')
            return


        try:
            start_date = get_nearest_date(start_period)
            end_date = get_nearest_date(end_period)
            print(f"start_date: {start_date}, end_date: {end_date}")

            if end_date < start_date:
                bot.reply_to(message, 'Дата окончания периода должна быть позже даты начала.')
                return
        except ValueError as e:
            bot.reply_to(message, f'Ошибка в дате. {str(e)}')
            return

        employees = get_unique_employees()
        if not employees:
            bot.reply_to(message, 'Список сотрудников пуст')
            return

        report = (f'Отчеты по сотрудникам за период с {start_date.strftime("%d.%m.%y")} '
                  f'по {end_date.strftime("%d.%m.%y")}:\n\n')
        print(report)

        for employee in employees:
            logs = get_logs(employee, start_date.strftime('%Y-%m-%d 00:00:00'),
                            end_date.strftime('%Y-%m-%d 23:59:59'))
            print(f"logs for {employee}: {logs}")

            if not logs:
                report += f'<b>Сотрудник "{employee}"</b>: Не работал\n\n'
                continue

            daily_totals = {}
            total_minutes = 0

            for i in range(len(logs)):
                if len(logs[i]) < 5:
                    continue

                if isinstance(logs[i][1], str):
                    try:
                        logs[i] = (
                            logs[i][0],
                            datetime.strptime(logs[i][1], '%Y-%m-%d %H:%M:%S'),
                            logs[i][2], logs[i][3],
                            logs[i][4]
                        )
                    except ValueError:
                        continue

                current_date = logs[i][1].date()
                start_time = logs[i][1]

                if i + 1 < len(logs):
                    end_time = logs[i + 1][1]
                else:
                    end_time = start_time

                duration = int((end_time - start_time).total_seconds() // 60)

                if logs[i][3].lower() not in ['стоп', 'ушел']:
                    total_minutes += duration
                    if current_date not in daily_totals:
                        daily_totals[current_date] = 0
                    daily_totals[current_date] += duration

            report += f'<b>Сотрудник "{employee}":</b>\n'
            report += f'Итого: {round(total_minutes / 60, 3)} ч ({total_minutes} мин):\n\n'

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
    Генерирует отчет по сотруднику за указанный период или по всем сотрудникам за один день.
    """
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, 'Используйте: /period <сотрудник> <период в формате ДДММ или ДДММ-ДДММ>')
            return

        employee = args[1].strip().lower()
        period = args[2].strip()

        current_year = datetime.now().year

        try:
            if '-' in period:
                start_period, end_period = period.split('-')
                start_day = int(start_period[:2])
                start_month = int(start_period[2:])
                end_day = int(end_period[:2])
                end_month = int(end_period[2:])

                start_date = datetime(current_year, start_month, start_day)
                end_date = datetime(current_year, end_month, end_day, 23, 59, 59)  # Учитываем целый день
            else:
                day = int(period[:2])
                month = int(period[2:])
                start_date = datetime(current_year, month, day)
                end_date = datetime(current_year, month, day, 23, 59, 59)

        except ValueError:
            bot.reply_to(message, 'Период должен быть в формате ДДММ или ДДММ-ДДММ (например, 1708 или 1708-2608)')
            return

        if '-' in period or employee != "все":
            logs = get_logs(employee, start_date.strftime('%Y-%m-%d %H:%M:%S'), end_date.strftime('%Y-%m-%d %H:%M:%S'))
        else:
            logs = get_logs(None, start_date.strftime('%Y-%m-%d %H:%M:%S'), end_date.strftime('%Y-%m-%d %H:%M:%S'))

        if not logs:
            bot.reply_to(message, f'Записей за {start_date.strftime("%d.%m.%y")} не найдено.')
            return

        daily_totals = {}
        total_minutes = 0
        employee_logs = {}

        for log in logs:
            log_employee = log[2].lower()
            if log_employee not in employee_logs:
                employee_logs[log_employee] = []
            employee_logs[log_employee].append(log)

        if '-' in period or employee != "все":
            for i in range(len(logs) - 1):
                current_date = logs[i][1].date()
                next_date = logs[i + 1][1].date()

                if current_date != next_date:
                    continue

                start_time = logs[i][1]
                end_time = logs[i + 1][1]

                if end_time > end_date:
                    end_time = end_date

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

        else:
            reports = []
            for emp, emp_logs in employee_logs.items():
                daily_totals = {}
                total_minutes = 0

                for i in range(len(emp_logs) - 1):
                    current_date = emp_logs[i][1].date()
                    next_date = emp_logs[i + 1][1].date()

                    if current_date != next_date:
                        continue

                    start_time = emp_logs[i][1]
                    end_time = emp_logs[i + 1][1]

                    duration = int((end_time - start_time).total_seconds() // 60)

                    if emp_logs[i][3].lower() not in ['стоп', 'ушел']:
                        total_minutes += duration
                        if current_date not in daily_totals:
                            daily_totals[current_date] = 0
                        daily_totals[current_date] += duration

                report = f'Часы работы "{emp}" за {start_date.strftime("%d.%m.%y")}:\n'
                report += f'Итого: {round(total_minutes / 60, 3)} ч ({total_minutes} мин):\n\n'

                for date, minutes in sorted(daily_totals.items()):
                    hours = round(minutes / 60, 3)
                    report += f'{date.strftime("%d.%m.%y")}: Всего: {hours} ч ({minutes} мин)\n'

                reports.append(report)

            for rep in reports:
                bot.reply_to(message, rep)

    except Exception as exc:
        bot.reply_to(message, f'Ошибка при формировании отчета за период: {exc}')

@bot.message_handler(commands=['projectsPeriod'])
def project_period(message):
    """
    Формирует список проектов и сотрудников за указанный период ДДММ-ДДММ или ДДММ.
    """
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Укажите период в формате ДДММ-ДДММ или ДДММ.")
            return

        period = args[1]
        current_date = datetime.now()
        dates = period.split('-')

        if len(dates) == 2:
            start_date = infer_year(dates[0], current_date).strftime('%Y-%m-%d')
            end_date = infer_year(dates[1], current_date).strftime('%Y-%m-%d')
        else:
            start_date = end_date = infer_year(dates[0], current_date).strftime('%Y-%m-%d')

        title = f'Проекты с {start_date} по {end_date}:\n' if start_date != end_date else f'Проекты за {start_date}:\n'

        logs = get_logs(None, f"{start_date} 00:00:00", f"{end_date} 23:59:59")
        if not logs:
            bot.reply_to(message, "За указанный период нет данных.")
            return

        projects = {}
        logs.sort(key=lambda x: x[1])

        for i in range(len(logs) - 1):
            log_id, time_stamp, employee, project, comment = logs[i]

            if not project or project.lower() in ["стоп", "ушел"]:
                continue

            project_key = project[0].lower() + project[1:]

            if project_key not in projects:
                projects[project_key] = {'employees': {}, 'total_minutes': 0}
            if employee not in projects[project_key]['employees']:
                projects[project_key]['employees'][employee] = 0

            next_time = None
            for j in range(i + 1, len(logs)):
                if logs[j][2] == employee:
                    next_time = logs[j][1]
                    break

            if not next_time or next_time.date() != time_stamp.date():
                continue

            duration = int((next_time - time_stamp).total_seconds() // 60)
            projects[project_key]['employees'][employee] += duration
            projects[project_key]['total_minutes'] += duration

        report = title
        sorted_projects = sorted(projects.items(), key=lambda x: x[1]['total_minutes'], reverse=True)

        for project, data in sorted_projects:
            total_hours = round(data['total_minutes'] / 60, 1)
            report += f'\n🔴 Проект "{project}" \n(всего: {data["total_minutes"]} мин / {total_hours} ч):\n\n'
            for employee, minutes in data['employees'].items():
                hours = round(minutes / 60, 1)
                report += f'- {employee}: {minutes} мин ({hours} ч)\n'

        MAX_MESSAGE_LENGTH = 4095
        if len(report) > MAX_MESSAGE_LENGTH:
            parts = [report[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(report), MAX_MESSAGE_LENGTH)]
            for part in parts:
                bot.reply_to(message, part)
        else:
            bot.reply_to(message, report.strip())

    except Exception as e:
        bot.reply_to(message, f"Ошибка при формировании отчета: {e}")

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
    
    /period <сотрудник> <ДДММ-ДДММ | ДДММ> - Общее количество часов работы 
    сотрудника за указанный период.
    
    /periodAll <ДДММ-ДДММ> - 
        1. Если указан период (ДДММ-ДДММ), выводит отчеты по всем сотрудникам за указанный период.
        
    /projectsPeriod ДДММ-ДДММ | ДДММ - отчет о времени, потраченном сотрудниками на проекты в указанном периоде
    
    /delete <ID> - Удаление записи по указанному ID.
    
    /add <сотрудник> <проект> <дата и время> [комментарий] - Добавление новой записи в базу данных.
    
    Чтобы добавить запись, отправьте сообщение в формате:
    
    1 строка: Дата (опц), время (обяз), комментарий (опц). Формат: ДДММГГ ЧЧММ текст.  
    2 строка: Имя сотрудника.  
    3 строка: Название проекта.
    """
    bot.reply_to(message, commands)
