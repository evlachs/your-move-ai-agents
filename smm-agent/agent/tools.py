"""
tools.py — инструменты агента
YandexGPT: выбор темы и генерация текста поста.
YandexART: генерация изображения к посту.
VK: загрузка изображения и создание отложенной записи на стене сообщества.
"""

import base64
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from configs.config import Config


logger = logging.getLogger(__name__)


# --- Инструмент 1: YandexGPT ---

class YandexGPTTool:
    """Инструмент для генерации темы и текста поста через YandexGPT."""

    MODEL_PRO = 'yandexgpt'

    def __init__(self, config: Config):
        self.config = config
        self.folder_id = config.yandex_folder_id

    def _chat(self, system: str, user: str, max_tokens: int = 800) -> str:
        try:
            response = requests.post(
                'https://llm.api.cloud.yandex.net/foundationModels/v1/completion',
                headers={
                    'Authorization': f'Api-Key {self.config.yandex_api_key}',
                    'x-folder-id': self.folder_id,
                },
                json={
                    'modelUri': f'gpt://{self.folder_id}/{self.MODEL_PRO}',
                    'completionOptions': {
                        'temperature': 0.7,
                        'maxTokens': max_tokens,
                    },
                    'messages': [
                        {'role': 'system', 'text': system},
                        {'role': 'user', 'text': user},
                    ],
                },
                timeout=60,
            )
            if not response.ok:
                logger.error(f'YandexGPT ответ: {response.text}')
                response.raise_for_status()
            return response.json()['result']['alternatives'][0]['message']['text'].strip()

        except Exception as e:
            logger.error(f'Ошибка YandexGPT: {e}')
            return ''

    def choose_topic(self, recent_topics: list[str]) -> str:
        """
        Выбирает новую тему для поста, избегая повторов.
        Лаборатория «ИИ-Синтез»: ИИ-агенты, отечественные технологии,
        конкурс «Твой Ход», обучение студентов.
        """
        system = (
            'Ты SMM-специалист лаборатории цифровых агентов «ИИ-Синтез» — '
            'образовательного проекта для студентов, где учат проектировать '
            'ИИ-агентов с использованием отечественных технологий (YandexGPT, '
            'Yandex Cloud). Проект участвует в конкурсе «Твой Ход». '
            'Придумай ОДНУ новую тему для поста в VK-сообщество лаборатории. '
            'Ответь только темой, одной короткой фразой, без пояснений.'
        )
        avoid_block = (
            f'Эти темы уже были — не повторяй их: {"; ".join(recent_topics)}\n\n'
            if recent_topics else ''
        )
        user = f'{avoid_block}Придумай новую тему для следующего поста.'
        topic = self._chat(system, user, max_tokens=100)
        return topic or 'ИИ-агенты в реальных задачах'

    def generate_post_text(self, topic: str) -> str:
        """Генерирует текст поста для VK по выбранной теме."""
        system = (
            'Ты SMM-специалист лаборатории цифровых агентов «ИИ-Синтез». '
            'Пишешь живой, дружелюбный пост для VK-сообщества студенческой '
            'лаборатории ИИ-агентов. Используй эмодзи в меру, добавь 2-3 '
            'релевантных хэштега в конце. Не используй markdown-разметку '
            '(VK её не отображает). Объём — 4-8 предложений.'
        )
        user = f'Тема поста: {topic}'
        return self._chat(system, user, max_tokens=800)


# --- Инструмент 2: YandexART ---

class YandexARTTool:
    """Инструмент для генерации изображения к посту через YandexART."""

    def __init__(self, config: Config):
        self.config = config
        self.folder_id = config.yandex_folder_id

    def generate_image(self, prompt: str, timeout: int = 120, poll_interval: int = 5) -> bytes | None:
        """
        Запускает асинхронную генерацию изображения и дожидается результата.
        Возвращает байты картинки (JPEG) или None при ошибке/таймауте.
        """
        headers = {
            'Authorization': f'Api-Key {self.config.yandex_api_key}',
            'x-folder-id': self.folder_id,
        }

        try:
            start = requests.post(
                'https://llm.api.cloud.yandex.net/foundationModels/v1/imageGenerationAsync',
                headers=headers,
                json={
                    'modelUri': f'art://{self.folder_id}/yandex-art/latest',
                    'generationOptions': {'seed': 0},
                    'messages': [{'weight': 1, 'text': prompt}],
                },
                timeout=30,
            )
            if not start.ok:
                logger.error(f'YandexART запуск генерации: {start.text}')
                start.raise_for_status()
            operation_id = start.json()['id']

        except Exception as e:
            logger.error(f'Ошибка запуска генерации YandexART: {e}')
            return None

        elapsed = 0
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                status = requests.get(
                    f'https://llm.api.cloud.yandex.net/operations/{operation_id}',
                    headers=headers,
                    timeout=30,
                )
                status.raise_for_status()
                data = status.json()
            except Exception as e:
                logger.error(f'Ошибка опроса YandexART: {e}')
                return None

            if data.get('done'):
                if 'error' in data:
                    logger.error(f'YandexART вернул ошибку: {data["error"]}')
                    return None
                image_b64 = data['response']['image']
                return base64.b64decode(image_b64)

        logger.error('YandexART: превышен таймаут ожидания генерации изображения')
        return None


# --- Инструмент 3: VK ---

class VKTool:
    """
    Инструмент для публикации отложенных записей в сообществе VK.
    Запись с publish_date в будущем не публикуется сразу — попадает
    в «Отложенные записи» сообщества, где админ может её проверить.
    """

    API_VERSION = '5.199'
    BASE_URL = 'https://api.vk.com/method'

    def __init__(self, config: Config):
        self.config = config
        self.access_token = config.vk_access_token
        self.group_id = config.vk_group_id

    def _call(self, method: str, params: dict) -> dict:
        payload = {
            **params,
            'access_token': self.access_token,
            'v': self.API_VERSION,
        }
        response = requests.post(f'{self.BASE_URL}/{method}', data=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if 'error' in data:
            raise RuntimeError(f'VK API {method}: {data["error"]}')
        return data['response']

    def upload_and_attach_photo(self, image_bytes: bytes) -> str:
        """
        Полный цикл загрузки фото на стену: получить upload-сервер,
        загрузить байты, сохранить фото на стене сообщества.
        Возвращает строку attachment вида 'photo{owner_id}_{photo_id}'.
        """
        upload_server = self._call('photos.getWallUploadServer', {'group_id': self.group_id})
        upload_url = upload_server['upload_url']

        upload_response = requests.post(
            upload_url,
            files={'photo': ('post.jpg', image_bytes, 'image/jpeg')},
            timeout=60,
        )
        upload_response.raise_for_status()
        upload_data = upload_response.json()

        saved = self._call('photos.saveWallPhoto', {
            'group_id': self.group_id,
            'photo': upload_data['photo'],
            'server': upload_data['server'],
            'hash': upload_data['hash'],
        })
        photo = saved[0]
        return f'photo{photo["owner_id"]}_{photo["id"]}'

    def create_postponed_post(self, text: str, attachment: str, publish_at: datetime) -> str:
        """
        Создаёт отложенную запись на стене сообщества.
        Возвращает post_id.
        """
        result = self._call('wall.post', {
            'owner_id': f'-{self.group_id}',
            'from_group': 1,
            'message': text,
            'attachments': attachment,
            'publish_date': int(publish_at.timestamp()),
        })
        return str(result['post_id'])


def next_publish_datetime(publish_hour: int, timezone: str) -> datetime:
    """
    Завтра в указанный час — время, на которое ставится отложенная запись.
    Использует config.timezone явно: наивный datetime.now() брал бы системное
    время контейнера (обычно UTC), из-за чего PUBLISH_HOUR интерпретировался бы
    не как московский час, а как UTC-час — пост в VK публиковался бы на 3 часа
    позже задуманного.
    """
    tz = ZoneInfo(timezone)
    tomorrow = datetime.now(tz) + timedelta(days=1)
    return tomorrow.replace(hour=publish_hour, minute=0, second=0, microsecond=0)
