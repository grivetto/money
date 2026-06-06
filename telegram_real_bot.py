#!/usr/bin/env python3
import os
import asyncio
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv('/home/sergio/.openclaw/workspace/denaro/.env')

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


def read_nuvola_status():
    try:
        with open('/home/sergio/.openclaw/workspace/denaro/REALISTIC_GRID.log', 'r') as f:
            lines = f.readlines()[-30:]

        investment = 35
        orders = '3'
        range_price = 'N/A'

        for line in reversed(lines):
            if 'Investimento:' in line:
                try:
                    investment = float(line.split('\u20ac')[1].split()[0])
                except Exception:
                    pass
                break

        for line in reversed(lines):
            if 'Grid piazzato:' in line:
                try:
                    parts = line.split('Grid piazzato:')[1].split('|')
                    orders = parts[0].strip()
                    if 'Range:' in line:
                        range_price = line.split('Range:')[1].strip()
                except Exception:
                    pass
                break

        return {
            'investment': investment,
            'orders': orders,
            'range': range_price,
            'status': '\u2705 Running'
        }
    except Exception as e:
        return {
            'investment': 35,
            'orders': '?',
            'range': 'N/A',
            'status': f'\u26a0\ufe0f Error: {str(e)[:20]}'
        }


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nuvola = read_nuvola_status()
    message = (
        f"\U0001f680 *DENARO SYSTEM \u2014 REAL DATA*\n\n"
        f"\U0001f4b0 *Capitale Allocato*\n"
        f"\u2022 NUVOLA (Grid): \u20ac{nuvola['investment']}\n"
        f"\u2022 MC2 (Rebound): Risk 0.2% BTC/trade\n\n"
        f"\U0001f4ca *NUVOLA \u2014 Grid BTC/EUR*\n"
        f"Status: {nuvola['status']}\n"
        f"Ordini aperti: {nuvola['orders']} BUY\n"
        f"Attesa: BTC scenda a ~\u20ac57k\n\n"
        f"\U0001f3af *MC2 \u2014 Rebound Sniper*\n"
        f"Status: {nuvola['status']}\n"
        f"Posizioni attive: -\n"
        f"In chiusura: -\n"
        f"Ultimo: -\n\n"
        f"\u23f0 Aggiornato: {datetime.now().strftime('%H:%M:%S')}"
    )
    keyboard = [
        [InlineKeyboardButton('\U0001f504 Aggiorna', callback_data='refresh')],
        [InlineKeyboardButton('\U0001f4c8 MC2 Log', callback_data='mc2_log'),
         InlineKeyboardButton('\U0001f4ca NUVOLA Log', callback_data='nuvola_log')]
    ]
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'refresh':
        await status_cmd(update, context)
    elif query.data == 'mc2_log':
        try:
            with open('/home/sergio/denaro/logs/rebound_real.log', 'r') as f:
                lines = f.readlines()[-15:]
            log_text = ''.join(lines)[-3500:]
            await query.edit_message_text(
                f'*\u2b50 MC2 Log (ultime righe):*\n\n{log_text}',
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text(f'Errore lettura log: {e}')
    elif query.data == 'nuvola_log':
        try:
            with open('/home/sergio/.openclaw/workspace/denaro/REALISTIC_GRID.log', 'r') as f:
                lines = f.readlines()[-15:]
            log_text = ''.join(lines)[-3500:]
            await query.edit_message_text(
                f'*\u2b50 NUVOLA Log (ultime righe):*\n\n{log_text}',
                parse_mode='Markdown'
            )
        except Exception as e:
            await query.edit_message_text(f'Errore lettura log: {e}')


async def profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /profit - calcola P&L"""
    try:
        with open('/home/sergio/denaro/status/positions_real.json', 'r') as f:
            positions = json.load(f)
        total_pnl = 0.0
        closed = [p for p in positions.values() if p.get('status') == 'closed']
        for p in closed:
            pnl = p.get('pnl', 0)
            if isinstance(pnl, (int, float)):
                total_pnl += pnl
        active = len([p for p in positions.values() if p.get('status') in ['hold', 'pending_buy']])
        try:
            with open('/home/sergio/denaro/drawdown.json', 'r') as f:
                dd = json.load(f)
            peak = dd.get('peak', 500.0)
            current = dd.get('current', 500.0)
            max_dd = dd.get('max_drawdown', 0.0)
        except Exception:
            peak = current = 500.0
            max_dd = 0.0
        message = (
            f"\U0001f4ca *PROFIT REPORT*\n\n"
            f"Posizioni chiuse: {len(closed)}\n"
            f"Posizioni attive: {active}\n"
            f"P&L totale: {total_pnl:+.2f} EUR\n\n"
            f"Picco: \u20ac{peak:.2f}\n"
            f"Attuale: \u20ac{current:.2f}\n"
            f"Max Drawdown: {max_dd:.2f}%"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f'Errore: {e}')


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('status', status_cmd))
    app.add_handler(CommandHandler('profit', profit))
    app.add_handler(CallbackQueryHandler(button))
    print('\U0001f680 Telegram Bot avviato')
    app.run_polling()


if __name__ == '__main__':
    main()