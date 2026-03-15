"""
Бот копирует посты из канала-источника в канал-назначение как текст (не пересылка).
Через 2 часа после публикации текст меняется на сообщение о закрытии задания.
Использует Webhook (работает на Railway, Render и других хостингах).

НАСТРОЙКА (Railway):
  Переменные окружения:
    TOKEN             — токен бота
    SOURCE_CHANNEL_ID — ID канала-источника (напр. -1001234567890)
    DEST_CHANNEL_ID   — ID канала-назначения (напр. -1009876543210)
    WEBHOOK_URL       — URL вашего Railway сервиса (напр. https://my-bot.up.railway.app)
"""

import os
import logging
from datetime import timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest

# ─── НАСТРОЙКИ ────────────────────────────────────────────────────────────────
TOKEN             = os.environ.get("TOKEN", "8696143142:AAGmtXacwCLm9UM7msOhcdb8yFKk0Wn-qkA")
SOURCE_CHANNEL_ID = int(os.environ["SOURCE_CHANNEL_ID"]) if os.environ.get("SOURCE_CHANNEL_ID") else None
DEST_CHANNEL_ID   = int(os.environ["DEST_CHANNEL_ID"])   if os.environ.get("DEST_CHANNEL_ID")   else None
WEBHOOK_URL       = os.environ.get("WEBHOOK_URL", "")
PORT              = int(os.environ.get("PORT", 8080))

CLOSE_AFTER_SECONDS = 2 * 60 * 60  # 2 часа

CLOSED_TEXT = (
    "🔒Задание закончилось!\n"
    "Дождитесь нового поста, чтобы откликнуться \n\n"
    "Не успеваете брать задания? Включите уведомления и получайте их первыми!"
)
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


async def close_message(context: ContextTypes.DEFAULT_TYPE):
    chat_id    = context.job.data["chat_id"]
    message_id = context.job.data["message_id"]
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=CLOSED_TEXT,
        )
        logger.info(f"Сообщение {message_id} закрыто.")
    except Exception as e:
        logger.error(f"Не удалось закрыть сообщение {message_id}: {e}")


async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if msg is None:
        return

    logger.info(f"Пост из канала {msg.chat_id} ({getattr(msg.chat, 'title', '-')})")

    if SOURCE_CHANNEL_ID is not None and msg.chat_id != SOURCE_CHANNEL_ID:
        return

    if DEST_CHANNEL_ID is None:
        logger.warning("DEST_CHANNEL_ID не задан!")
        return

    text    = msg.text or msg.caption or ""
    caption = text or None

    try:
        if msg.text:
            sent = await context.bot.send_message(
                chat_id=DEST_CHANNEL_ID,
                text=text,
            )
        elif msg.photo:
            sent = await context.bot.send_photo(
                chat_id=DEST_CHANNEL_ID,
                photo=msg.photo[-1].file_id,
                caption=caption,
            )
        elif msg.video:
            sent = await context.bot.send_video(
                chat_id=DEST_CHANNEL_ID,
                video=msg.video.file_id,
                caption=caption,
            )
        elif msg.document:
            sent = await context.bot.send_document(
                chat_id=DEST_CHANNEL_ID,
                document=msg.document.file_id,
                caption=caption,
            )
        else:
            sent = await context.bot.copy_message(
                chat_id=DEST_CHANNEL_ID,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )

        logger.info(f"Скопировано в {DEST_CHANNEL_ID}, message_id={sent.message_id}")

        context.job_queue.run_once(
            close_message,
            when=timedelta(seconds=CLOSE_AFTER_SECONDS),
            data={"chat_id": DEST_CHANNEL_ID, "message_id": sent.message_id},
            name=f"close_{sent.message_id}",
        )

    except Exception as e:
        logger.error(f"Ошибка: {e}")


def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30)
    app = ApplicationBuilder().token(TOKEN).request(request).build()
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS, handle_post))

    if WEBHOOK_URL:
        # Webhook режим — для хостингов
        logger.info(f"Запуск в режиме Webhook: {WEBHOOK_URL}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL.rstrip('/')}/webhook",
            url_path="/webhook",
        )
    else:
        # Polling режим — для локального запуска
        logger.info("Запуск в режиме Polling (локально)…")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
