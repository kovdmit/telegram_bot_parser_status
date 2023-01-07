import os
import sys
import time
import logging
from typing import Union, Final, NoReturn
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
ENDPOINT: str = ('https://practicum.yandex.ru/api/user_api/homework_statuses/')
HEADERS: dict[str, str] = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: dict[str, str] = {
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


def check_tokens() -> NoReturn:
    """Проверяет доступность необходимых переменных окружения."""
    if not PRACTICUM_TOKEN or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        error: str = 'Недостаточно переменных окружения для запуска программы.'
        logger.critical(error)
        raise exceptions.MissingEnviromentsVariable(error)
    else:
        logger.debug('Переменные окружения найдены и подключены.')


def get_api_answer(timestamp: int) -> dict[str, Union[int, list[dict]]]:
    """Делает запрос к эндпоинту API-сервиса."""
    try:
        response = requests.get(ENDPOINT,
                                headers=HEADERS,
                                params={'from_date': timestamp})
        if response.status_code == HTTPStatus.OK:
            logger.debug('Успешное подключение к API.')
            return response.json()
        else:
            status: int = response.status_code
            msg: str = f'Неудачный запрос к API. Статус {status}.'
            logger.error(msg)
            raise exceptions.BadConnection(msg)
    except requests.RequestException:
        logger.error('Не удалось подключиться к API.')


def check_response(response: dict[str, Union[int, list[dict]]]) -> NoReturn:
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        msg: str = 'Структура ответа API не соответствует ожиданиям.'
        logger.error(msg)
        raise TypeError(msg)
    elif response.get('homeworks') is None or response.get('current_date'
                                                           ) is None:
        msg: str = 'В ответе API нет необходимых данных.'
        logger.error(msg)
        raise exceptions.IncorrectResponse(msg)
    elif not isinstance(response.get('homeworks'), list):
        msg: str = ('В ответе API домашней работы под ключом `homeworks` '
                    'данные приходят не в виде списка.')
        logger.error(msg)
        raise TypeError(msg)
    else:
        logger.debug('Ответ API успешно обработан.')


def parse_status(homework: dict[str, Union[str, int]]) -> str:
    """Извлекает из информации о конкретной домашней работе её статус."""
    status: str = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        msg: str = f'Получен неизвестный статус домашней работы: {status}.'
        logger.error(msg)
        raise exceptions.UnknownStatus(msg)
    homework_name: str = homework.get('homework_name')
    if not homework_name:
        msg: str = 'Не передано название домашней работы.'
        logger.error(msg)
        raise exceptions.MissingHomeworkName(msg)
    verdict: str = HOMEWORK_VERDICTS.get(status)
    message = f'Изменился статус проверки работы "{homework_name}". {verdict}'
    logger.info(message)
    return message


def send_message(bot: telegram.Bot, message: str) -> NoReturn:
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение  отправлено: {message}')
    except Exception as error:
        logger.error(f'Не удалось отправить сообщение в Telegram чат {error}')


def main() -> NoReturn:
    """Основная логика работы бота."""
    logger.debug(f'Запуск программы. Данные обновляются каждые {RETRY_PERIOD}'
                 ' секунд.')
    check_tokens()

    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
        logger.debug('Telegram бот успешно подключен.')
    except Exception as error:
        info: str = f'Не удалось подключиться к Telegram боту: {error}.'
        logger.error(info)
        raise exceptions.BadConnection(info)

    timestamp: int = int(time.time())
    logger.debug(f'Зафиксировано время запроса: {timestamp}.')

    sent_get_api: bool = False
    response: dict[str, Union[int, list[dict]]] = get_api_answer(timestamp)
    if not response:
        send_message(bot, 'Ошибка при запросе к API')
        logger.debug('Отправка сообщения об ошибке в Telegram.')
        sent_get_api = True
    check_response(response)

    while True:
        try:
            if len(response.get('homeworks')) == 0:
                logger.debug(f'Ожидание {RETRY_PERIOD} секунд.')
                time.sleep(RETRY_PERIOD)
                logger.info('Статус домашней работы работы не изменён.')
            else:
                logger.debug('Изменение статуса домашней работы. '
                             'Просмотр последней записи.')
                homework = response.get('homeworks')[0]
                logger.debug('Получена первая запись. Чтение информации.')
                message = parse_status(homework)
                logger.debug('Сформировано сообщение для отправки в Telegram.'
                             ' Попытка отправки.')
                send_message(bot, message)
                logger.debug(f'Ожидание {RETRY_PERIOD} секунд.')
                time.sleep(RETRY_PERIOD)
        except Exception as error:
            message: str = f'Сбой в работе программы: {error}'
            logger.error(message)
            send_message(bot, message)
        finally:
            timestamp: int = response.get('current_date')
            logger.debug(f'Зафиксировано время запроса: {timestamp}.')
            response: dict = get_api_answer(timestamp)
            if not response and not sent_get_api:
                send_message(bot, 'Ошибка при запросе к API')
                logger.debug('Отправка сообщения об ошибке в Telegram.')
                sent_get_api = True
            check_response(response)


if __name__ == '__main__':
    main()
