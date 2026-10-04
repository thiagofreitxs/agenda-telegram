"""Ponto de entrada do bot: python -m app.main"""

from __future__ import annotations

import logging
from datetime import time as dtime

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import config, db, handlers
from .health import start_health_server
from .services.reminder_service import check_reminders, cleanup_job

logger = logging.getLogger(__name__)

COMMANDS = [
    ("novo", "Criar um evento (ex.: /novo Dentista amanhã 14h)"),
    ("hoje", "Agenda de hoje"),
    ("amanha", "Agenda de amanhã"),
    ("semana", "Próximos 7 dias"),
    ("proximos", "Próximos compromissos"),
    ("cancelar", "Cancelar um evento"),
    ("lembrete", "Minutos de antecedência do aviso"),
    ("diario", "Horário do aviso de eventos de dia inteiro"),
    ("status", "Configuração atual"),
    ("id", "Mostrar seu ID do Telegram"),
    ("ajuda", "Como usar o bot"),
]


async def _post_init(application: Application) -> None:
    db.init_db()
    await application.bot.set_my_commands(
        [BotCommand(command, description) for command, description in COMMANDS]
    )
    me = await application.bot.get_me()
    logger.info("Bot iniciado como @%s", me.username)


async def _on_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra qualquer erro no chat em vez de ficar em silêncio."""
    logger.error("Erro ao processar uma atualização.", exc_info=context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                f"❌ Erro inesperado: {type(context.error).__name__}: {context.error}"
            )
        except Exception:  # noqa: BLE001
            pass


def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("ajuda", handlers.cmd_help))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("id", handlers.cmd_id))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("novo", handlers.cmd_novo))
    app.add_handler(CommandHandler("hoje", handlers.cmd_hoje))
    app.add_handler(CommandHandler("amanha", handlers.cmd_amanha))
    app.add_handler(CommandHandler("semana", handlers.cmd_semana))
    app.add_handler(CommandHandler("proximos", handlers.cmd_proximos))
    app.add_handler(CommandHandler("cancelar", handlers.cmd_cancelar))
    app.add_handler(CommandHandler("lembrete", handlers.cmd_lembrete))
    app.add_handler(CommandHandler("diario", handlers.cmd_diario))
    # Texto livre (sem "/") vira um novo evento automaticamente.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    app.add_handler(MessageHandler(filters.COMMAND, handlers.cmd_erro))
    app.add_error_handler(_on_error)

    job_queue = app.job_queue
    if job_queue is not None:
        job_queue.run_repeating(
            check_reminders, interval=config.REMINDER_CHECK_INTERVAL_SECONDS, first=10
        )
        job_queue.run_daily(cleanup_job, time=dtime(3, 0))
    else:
        logger.warning("JobQueue indisponível: instale python-telegram-bot[job-queue].")

    return app


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    )
    # Evita vazar o token nas URLs de requisição nos logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    for aviso in config.validate():
        logger.warning(aviso)
    start_health_server()
    app = build_application()
    logger.info("Rodando em modo polling. Ctrl+C para parar.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
