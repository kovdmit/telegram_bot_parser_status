import os
import sys
import time
import logging
from typing import Union, NoReturn, List, Dict
from http import HTTPStatus

import requests
from dotenv import load_dotenv
import telegram

import exceptions

load_dotenv()

PRACTICUM_TOKEN: str = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID: Union[int, str] = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: Dict[str, str] = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: Dict[str, str] = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

sent_error_tg: Dict[str, bool] = {
    'connect_api': False,
    'response_is_dict': False,
    'response_has_keys': False,
    'unknown_status': False,
    'missing_homework_name': False,
    'other': False,
}


def check_tokens() -> bool:
    """Проверяет доступность необходимых переменных окружения."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def get_api_answer(timestamp: int) -> Dict[str, Union[int, List]]:
    """Делает запрос к эндпоинту API-сервиса."""
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params={'from_date': timestamp})
        if response.status_code == HTTPStatus.OK:
            return response.json()
        else:
            raise exceptions.BadConnection('Не удалось подключиться к API.')
    except requests.RequestException:
        raise exceptions.BadConnection('Не удалось подключиться к API.')


def check_response(response: Dict[str, Union[int, List]]) -> NoReturn:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, Dict):
        raise TypeError('Структура ответа API не соответствует ожиданиям.')
    elif response.get('homeworks') is None or response.get('current_date'
                                                           ) is None:
        raise exceptions.NoExpendKeysResponse('В ответе API нет '
                                              'необходимых данных.')
    elif not isinstance(response.get('homeworks'), list):
        raise TypeError('В ответе API домашней работы под ключом "homeworks" '
                        'данные приходят не в виде списка.')


def parse_status(homework: Dict[str, Union[str, int]]) -> str:
    """Извлекает из информации о конкретной домашней работе её статус."""
    status: str = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        raise exceptions.UnknownStatus('Получен неизвестный статус '
                                       f'домашней работы: {status}.')
    homework_name: str = homework.get('homework_name')
    if not homework_name:
        raise exceptions.MissingHomeworkName('Не передано название домашки.')
    verdict: str = HOMEWORK_VERDICTS.get(status)
    message: str = (f'Изменился статус проверки работы "{homework_name}".'
                    f' {verdict}')
    return message


def send_message(bot: telegram.Bot, message: str) -> NoReturn:
    """Отправляет сообщение в Telegram чат."""
    logger.debug(f'Попытка отправить сообщение: {message}')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        logger.error(error)
        raise exceptions.DontSentMessage('Не удалось отправить сообщение '
                                         f'в Telegram чат {error}')
    else:
        logger.debug(f'Сообщение  отправлено: {message}')


def send_error_to_tg(bot: telegram.Bot,
                     key: str,
                     msg: str = None) -> NoReturn:
    """Отправляет сообщение об ошибке в телеграм один раз."""
    if not sent_error_tg.get(key):
        send_message(bot, msg)
        sent_error_tg[key] = True
        logger.debug(f'Попробуем ещё раз через {RETRY_PERIOD} секунд.')
        time.sleep(RETRY_PERIOD)


def main() -> NoReturn:
    """Основная логика работы бота."""
    logger.info(f'Запуск программы. Данные обновляются каждые {RETRY_PERIOD}'
                ' секунд. Поиск токенов авторизации.')

    if not check_tokens():
        error: str = 'Недостаточно переменных окружения для запуска программы.'
        logger.critical(error)
        sys.exit(error)
    logger.debug('Переменные окружения (токены) найдены и подключены. '
                 'Попытка подключения к Telegram боту.')

    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except Exception as error:
        msg: str = (f'Не удалось подключиться к Telegram боту: {error}. '
                    f'Программа остановлена.')
        logger.error(msg)
        sys.exit(msg)
    else:
        logger.debug('Telegram бот успешно подключен.')

    timestamp: int = int(time.time())
    logger.debug(f'Зафиксировано время запроса: {timestamp}.')

    while True:
        logger.debug('Узнаём статус домашней работы.')
        try:
            logger.debug('Попытка подключения к API.')
            response: Dict[str, Union[int, List]] = get_api_answer(timestamp)
            logger.debug('Проверка ответа API на соответствие документации.')
            check_response(response)
            if response and len(response.get('homeworks')) == 0:
                logger.info('Статус домашней работы работы не изменён.')
                logger.debug(f'Ожидание {RETRY_PERIOD} секунд.')
                time.sleep(RETRY_PERIOD)
            else:
                logger.debug('Изменение статуса домашней работы. '
                             'Просмотр последней записи.')
                homework = response.get('homeworks')[0]
                logger.debug('Получена последняя запись. Чтение информации.')
                try:
                    message = parse_status(homework)
                    logger.debug('Готово сообщение для отправки в Telegram.')
                    logger.info(message)
                    send_message(bot, message)
                except Exception as error:
                    logger.error(error)
                    send_error_to_tg(bot, 'unknown_status', error)
                    continue
                logger.debug(f'Ожидание {RETRY_PERIOD} секунд.')
                time.sleep(RETRY_PERIOD)
        except Exception as error:
            message: str = f'Сбой в работе программы: {error}'
            send_error_to_tg(bot, 'other', message)
            break
        else:
            logger.debug(f'Зафиксировано время запроса: {timestamp}.')
            timestamp: int = response.get('current_date')


if __name__ == '__main__':
    main()
